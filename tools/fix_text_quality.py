# -*- coding: utf-8 -*-
"""
題目文字品質修復工具 — 修正 PDF 解析造成的文字問題

主要修復:
1. 閱讀測驗段落文字滲入前一題選項（passage leak）
2. 英文字缺空格（missing spaces from OCR）
3. 選項文字中的缺空格問題

用法:
  python tools/fix_text_quality.py                    # 修復所有 JSON
  python tools/fix_text_quality.py --dry-run          # 只顯示會怎麼改
  python tools/fix_text_quality.py --category 行政警察學系 # 只處理特定類科
"""

import os
import re
import json
import argparse
from pathlib import Path


# ── Load word dictionary ──
_WORD_DICT = None

def _load_word_dict():
    global _WORD_DICT
    if _WORD_DICT is not None:
        return _WORD_DICT

    dict_path = Path(__file__).parent / 'english_words.json'
    if dict_path.exists():
        with open(dict_path, 'r') as f:
            _WORD_DICT = json.load(f)
    else:
        _WORD_DICT = {}

    # Ensure common small words are present
    for w in ['a', 'i', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he',
              'if', 'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or',
              'so', 'to', 'up', 'us', 'we', 'the', 'and', 'for', 'are',
              'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one',
              'our', 'out', 'has', 'his', 'how', 'its', 'may', 'new', 'now',
              'old', 'see', 'way', 'who', 'did', 'get', 'let', 'say', 'she',
              'too', 'use']:
        if w not in _WORD_DICT:
            _WORD_DICT[w] = 100

    return _WORD_DICT


# ── Pattern: 「請依下文回答第X題至第Y題」passage leak ──
PASSAGE_HEADER_RE = re.compile(
    r'請依下文回答第\s*(\d+)\s*題至第\s*(\d+)\s*題'
)

# ── Pattern for detecting long runs of English text without spaces ──
LONG_ENGLISH_RUN = re.compile(r'[a-zA-Z]{8,}')

# Detect camelCase boundaries
CAMEL_SPLIT_RE = re.compile(r'([a-z])([A-Z][a-z])')

# Detect number-word joins
NUMBER_WORD_JOIN = re.compile(r'(\d)([a-zA-Z])')
WORD_NUMBER_JOIN = re.compile(r'([a-zA-Z])(\d)')


# ── Stats tracking ──
stats = {
    'passage_leaks_fixed': 0,
    'passages_created': 0,
    'spaces_fixed_stems': 0,
    'spaces_fixed_options': 0,
    'spaces_fixed_passages': 0,
}


def word_segment(text):
    """
    使用動態規劃將缺空格的英文字串分段成單詞。
    例如: "thepolice" -> "the police"

    Scoring strategy:
    - Known words (3+ chars): wlen * 10 + freq_bonus - split_cost
    - Known 2-char words: fixed score of 5 - split_cost
    - Known 1-char ('a', 'i'): fixed score of 3 - split_cost
    - Unknown words (3+ chars with vowel): penalty of -20
    - split_cost = 8 for each word after the first (penalizes over-splitting)
    """
    import math
    word_dict = _load_word_dict()
    text_lower = text.lower()
    n = len(text_lower)

    if n == 0:
        return text
    if n <= 3:
        return text

    MAX_WORD = 25
    SPLIT_COST = 8  # penalty per word to discourage over-splitting

    # dp[i] = (best_score, word_lengths_list) for text[:i]
    dp = [None] * (n + 1)
    dp[0] = (0, [])

    for i in range(1, n + 1):
        best = None
        for j in range(max(0, i - MAX_WORD), i):
            if dp[j] is None:
                continue
            word = text_lower[j:i]
            wlen = i - j

            # Split cost: first word is free, subsequent words pay penalty
            split_penalty = SPLIT_COST if j > 0 else 0

            if word in word_dict:
                freq = word_dict[word]
                freq_bonus = min(math.log2(freq + 1), 8)

                if wlen == 1:
                    if word in ('a', 'i'):
                        score = dp[j][0] + 3 - split_penalty
                    else:
                        continue  # skip other 1-char
                elif wlen == 2:
                    score = dp[j][0] + 5 - split_penalty
                else:
                    score = dp[j][0] + wlen * 10 + freq_bonus - split_penalty

                if best is None or score > best[0]:
                    best = (score, dp[j][1] + [wlen])

            elif wlen >= 3:
                # Unknown word: give a moderate positive score based on length.
                # This prevents over-splitting of words not in our dictionary
                # (e.g., "congressional" → should NOT become "congress ional")
                # but still allows splits when known words score much higher.
                if re.search(r'[aeiouy]', word):
                    score = dp[j][0] + wlen * 5 - split_penalty
                    if best is None or score > best[0]:
                        best = (score, dp[j][1] + [wlen])

        dp[i] = best

    if dp[n] is None:
        return text

    # Reconstruct
    words = []
    pos = 0
    for wlen in dp[n][1]:
        words.append(text[pos:pos + wlen])  # preserve original case
        pos += wlen

    result = ' '.join(words)

    # Sanity check: if we introduced too many tiny fragments, return original
    avg_word_len = n / max(len(words), 1)
    if avg_word_len < 2.5 and n > 10:
        return text

    return result


def fix_missing_spaces(text):
    """修復英文文字中缺失的空格"""
    if not text:
        return text

    # Step 1: Handle number-word joins first
    text = NUMBER_WORD_JOIN.sub(r'\1 \2', text)
    text = WORD_NUMBER_JOIN.sub(r'\1 \2', text)

    # Step 2: Find long runs of English text and try to segment them
    def segment_match(m):
        run = m.group(0)
        word_dict = _load_word_dict()

        # First try camelCase split
        split_attempt = CAMEL_SPLIT_RE.sub(r'\1 \2', run)
        if ' ' in split_attempt:
            pieces = split_attempt.split(' ')
            result_pieces = []
            for piece in pieces:
                if len(piece) >= 6:
                    segmented = word_segment(piece)
                    result_pieces.append(segmented)
                else:
                    result_pieces.append(piece)
            return ' '.join(result_pieces)

        # For known words with high frequency (>= 20), trust as real words
        run_lower = run.lower()
        if run_lower in word_dict and word_dict[run_lower] >= 20:
            return run

        # For unknown or low-frequency words, try segmentation
        return word_segment(run)

    result = LONG_ENGLISH_RUN.sub(segment_match, text)

    # Clean up multiple spaces
    result = re.sub(r'  +', ' ', result)

    return result


def extract_passage_from_option(option_text):
    """
    從選項文字中提取閱讀測驗段落。

    Returns:
        tuple: (clean_option, passage_text, start_q, end_q) or (option_text, None, None, None)
    """
    match = PASSAGE_HEADER_RE.search(option_text)
    if not match:
        return option_text, None, None, None

    idx = match.start()
    if idx <= 0:
        return option_text, None, None, None

    clean_opt = option_text[:idx].strip()
    clean_opt = re.sub(r'\s*-\s*-?\s*$', '', clean_opt).strip()
    passage_full = option_text[idx:].strip()
    start_q = int(match.group(1))
    end_q = int(match.group(2))
    return clean_opt, passage_full, start_q, end_q


def fix_passage_leaks(questions):
    """
    修復閱讀測驗段落滲入選項的問題。
    """
    global stats
    modified = False

    q_by_num = {q['number']: q for q in questions}

    for q in questions:
        if q.get('type') != 'choice' or 'options' not in q:
            continue

        for label in list(q['options'].keys()):
            opt_text = q['options'][label]
            if '請依下文回答' not in opt_text:
                continue

            clean_opt, passage_text, start_q, end_q = extract_passage_from_option(opt_text)

            if passage_text is None:
                continue

            q['options'][label] = clean_opt
            stats['passage_leaks_fixed'] += 1
            modified = True

            if start_q is not None and end_q is not None:
                for qnum in range(start_q, end_q + 1):
                    if qnum in q_by_num:
                        q_by_num[qnum]['passage'] = passage_text
                        stats['passages_created'] += 1

    # Also check stems for passage text that should be in passage field
    for q in questions:
        if q.get('type') != 'choice':
            continue
        stem = q.get('stem', '')
        if '請依下文回答' not in stem:
            continue
        match = PASSAGE_HEADER_RE.search(stem)
        if match and match.start() > 15:
            clean_stem = stem[:match.start()].strip()
            passage_text = stem[match.start():].strip()
            start_q = int(match.group(1))
            end_q = int(match.group(2))

            q['stem'] = clean_stem
            for qnum in range(start_q, end_q + 1):
                if qnum in q_by_num:
                    q_by_num[qnum]['passage'] = passage_text
                    stats['passages_created'] += 1
            modified = True

    return modified


def fix_text_quality_in_questions(questions):
    """修復題目中的文字品質問題（缺空格等）"""
    global stats
    modified = False

    for q in questions:
        if q.get('type') != 'choice':
            continue

        # Fix missing spaces in stem
        stem = q.get('stem', '')
        if stem and LONG_ENGLISH_RUN.search(stem):
            fixed_stem = fix_missing_spaces(stem)
            if fixed_stem != stem:
                q['stem'] = fixed_stem
                stats['spaces_fixed_stems'] += 1
                modified = True

        # Fix missing spaces in options
        if 'options' in q:
            for label in list(q['options'].keys()):
                opt = q['options'][label]
                if LONG_ENGLISH_RUN.search(opt):
                    fixed_opt = fix_missing_spaces(opt)
                    if fixed_opt != opt:
                        q['options'][label] = fixed_opt
                        stats['spaces_fixed_options'] += 1
                        modified = True

        # Fix missing spaces in passage
        passage = q.get('passage', '')
        if passage and LONG_ENGLISH_RUN.search(passage):
            fixed_passage = fix_missing_spaces(passage)
            if fixed_passage != passage:
                q['passage'] = fixed_passage
                stats['spaces_fixed_passages'] += 1
                modified = True

    return modified


def process_json_file(json_path, dry_run=False):
    """處理單一 JSON 檔案"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [跳過] {json_path}: {e}")
        return False

    questions = data.get('questions', [])
    if not questions:
        return False

    modified = False

    # Phase 1: Fix passage leaks (must come first, before space fixing)
    if fix_passage_leaks(questions):
        modified = True

    # Phase 2: Fix missing spaces in text
    if fix_text_quality_in_questions(questions):
        modified = True

    if modified and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return modified


def main():
    global stats

    parser = argparse.ArgumentParser(description='修復題目文字品質')
    parser.add_argument('--input', default='考古題庫', help='輸入目錄')
    parser.add_argument('--category', help='只處理特定類科')
    parser.add_argument('--dry-run', action='store_true', help='不實際寫入')
    parser.add_argument('--verbose', '-v', action='store_true', help='顯示詳細資訊')
    args = parser.parse_args()

    base_dir = Path(args.input)
    if not base_dir.exists():
        base_dir = Path(__file__).parent.parent / args.input
    if not base_dir.exists():
        print(f"找不到目錄: {args.input}")
        return

    _load_word_dict()

    total_files = 0
    modified_files = 0

    for json_path in sorted(base_dir.rglob('試題.json')):
        if args.category and args.category not in str(json_path):
            continue

        total_files += 1
        rel_path = json_path.relative_to(base_dir)

        if process_json_file(str(json_path), dry_run=args.dry_run):
            modified_files += 1
            if args.verbose:
                action = "[預覽]" if args.dry_run else "[更新]"
                print(f"  {action} {rel_path}")

    print(f"\n{'=' * 55}")
    print(f"文字品質修復完成{'（dry-run 模式）' if args.dry_run else ''}:")
    print(f"  掃描檔案: {total_files}")
    print(f"  修改檔案: {modified_files}")
    print(f"  ──────────────────────────")
    print(f"  段落滲入修復: {stats['passage_leaks_fixed']} 個選項")
    print(f"  段落欄位建立: {stats['passages_created']} 個題目")
    print(f"  題幹空格修復: {stats['spaces_fixed_stems']} 個題目")
    print(f"  選項空格修復: {stats['spaces_fixed_options']} 個選項")
    print(f"  段落空格修復: {stats['spaces_fixed_passages']} 個段落")
    if args.dry_run:
        print("  （dry-run 模式，未實際寫入）")


if __name__ == '__main__':
    main()
