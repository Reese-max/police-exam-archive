#!/usr/bin/env python3
"""修復英文閱讀測驗的段落文字/選項混入問題

KR1: 清理選項中混入的段落文字
KR2: 清理題幹中混入的上一題選項，並提取段落文字
KR3: 修復行政警察 106年偵查法學 Q6 metadata 混入
"""

import json
import glob
import re
import os
import shutil
from datetime import datetime


def backup_file(fp):
    """備份檔案"""
    backup_dir = f"backups/content_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    rel = os.path.relpath(fp)
    dest = os.path.join(backup_dir, rel.replace(os.sep, '_'))
    shutil.copy2(fp, dest)
    return dest


def load_json(fp):
    with open(fp, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(fp, data):
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Pattern to match passage intro variations:
# - 請依下文回答第53題至第57題
# - 請依下文回答第41至45題
# - 請回答下列第41題至第45題
# - 第37題至第40題為篇章結構題組
PASSAGE_INTRO_RE = re.compile(
    r'(?:請(?:依下文)?回答(?:下列)?)?第\s*(\d+)\s*題?至第?\s*(\d+)\s*題'
    r'(?:為篇章結構題組)?[,，]?\s*(?:各題請依文意[,，]?從四個選項中選出最合適者[,，]?各題答案內容不重複)?'
    r'\s*[:：]?\s*'
)

# Pattern to match leading options in stem: (A)xxx (B)yyy (C)zzz (D)www
LEADING_OPTS_RE = re.compile(
    r'^\s*[\(（]A[\)）](.*?)[\(（]B[\)）](.*?)[\(（]C[\)）](.*?)[\(（]D[\)）](.*?)$',
    re.DOTALL
)

# For stems that have options + more content
LEADING_OPTS_PREFIX_RE = re.compile(
    r'^\s*[\(（]A[\)）].*?[\(（]D[\)）][^請]*?(請依下文回答)',
    re.DOTALL
)


def find_passage_groups(questions):
    """找出段落文字及其對應的題號範圍

    掃描所有 option D 和 stem 中的 '請依下文回答第X題至第Y題' 模式
    返回: [(start_num, end_num, passage_text), ...]
    """
    groups = []

    for q in questions:
        if q.get('type') != 'choice':
            continue

        num = q.get('number')
        if not isinstance(num, int):
            continue

        # Check option D
        opt_d = str(q.get('options', {}).get('D', ''))
        m = PASSAGE_INTRO_RE.search(opt_d)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            passage_text = opt_d[m.start():]
            groups.append((start, end, passage_text, num, 'option_d'))

        # Check stem
        stem = q.get('stem', '') or ''
        m = PASSAGE_INTRO_RE.search(stem)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            passage_text = stem[m.start():]
            groups.append((start, end, passage_text, num, 'stem'))

    return groups


def fix_file(fp, dry_run=False):
    """修復單一檔案的所有內容問題"""
    d = load_json(fp)
    if d.get('metadata', {}).get('_is_duplicate'):
        return 0

    questions = d.get('questions', [])
    changes = 0

    # Step 1: Find all passage groups
    passage_groups = find_passage_groups(questions)

    # Build a map: question_number -> passage_text
    passage_map = {}
    for start, end, passage_text, source_q, source_type in passage_groups:
        for n in range(start, end + 1):
            if n not in passage_map:
                passage_map[n] = passage_text

    # Step 2: Fix each question
    for q in questions:
        if q.get('type') != 'choice':
            continue

        num = q.get('number')
        if not isinstance(num, int):
            continue

        stem = q.get('stem', '') or ''
        opts = q.get('options', {})

        # Fix 2a: Clean option D - remove passage text
        if 'D' in opts:
            opt_d = str(opts['D'])
            # Split at passage intro
            m = PASSAGE_INTRO_RE.search(opt_d)
            if m:
                # Keep only the real option value
                real_val = opt_d[:m.start()].rstrip(' -\n\t–—')
                if real_val != opt_d:
                    opts['D'] = real_val
                    changes += 1

        # Fix 2b: Clean stem - remove leading options from previous question
        if re.match(r'\s*[\(（][A-D][\)）]', stem):
            # Case 1: Stem is ONLY options (cloze question)
            m_full = LEADING_OPTS_RE.match(stem.strip())
            if m_full:
                # This is a cloze question, stem should reference passage
                if num in passage_map:
                    q['stem'] = ''  # Clear, passage will be set separately
                else:
                    q['stem'] = ''
                changes += 1
            else:
                # Case 2: Stem has options + passage intro
                m_prefix = PASSAGE_INTRO_RE.search(stem)
                if m_prefix:
                    # Keep from passage intro onward as stem
                    # (but actually this passage belongs to a LATER group)
                    # The current question's own stem should be empty (it's cloze)
                    q['stem'] = ''
                    changes += 1
                else:
                    # Stem starts with options but has other content too
                    # Try to strip the (A)...(D) prefix
                    m_strip = re.match(
                        r'\s*[\(（]A[\)）].*?[\(（]D[\)）][^\n]*?\n(.*)',
                        stem, re.DOTALL
                    )
                    if m_strip:
                        q['stem'] = m_strip.group(1).strip()
                        changes += 1

        # Fix 2c: Set passage for questions in passage groups
        if num in passage_map and not q.get('passage'):
            q['passage'] = passage_map[num]
            changes += 1

    if changes > 0 and not dry_run:
        backup_file(fp)
        save_json(fp, d)

    return changes


def fix_detective_q6():
    """KR3: 修復行政警察 106年偵查法學 Q6"""
    fp = '考古題庫/行政警察/106年/偵查法學與犯罪偵查/試題.json'
    if not os.path.exists(fp):
        print(f"  檔案不存在: {fp}")
        return 0

    d = load_json(fp)
    questions = d.get('questions', [])
    changes = 0

    for q in questions:
        if q.get('number') == 6 and q.get('type') == 'choice':
            stem = q.get('stem', '')
            # Find and remove essay content + metadata
            # The stem starts mid-essay, look for the actual Q6 content
            # Pattern: ends with "乙、測驗題部分:(50分) 代號:6501 1本試題為..."
            # then "1 關於通訊保障及監察法..."
            m = re.search(
                r'乙、測驗題?部分[:：]?\s*\(\d+分\)\s*代號[:：]\s*\d+\s*'
                r'[\d\s]*本試題為單一選擇題.*?不予計分。\s*'
                r'(\d+\s+.*)',
                stem, re.DOTALL
            )
            if m:
                # The real Q6 stem should be after the metadata
                # But actually, Q6's real content was likely parsed into this blob
                # Find the actual Q1 content at the end
                real_q1_match = re.search(
                    r'(\d+)\s+(關於通訊保障及監察法.*)',
                    stem, re.DOTALL
                )
                if real_q1_match:
                    # This Q6 has Q1's content mixed in
                    # The simplest fix: truncate at '乙、測驗' marker
                    cut_idx = stem.index('乙、測驗')
                    clean_stem = stem[:cut_idx].rstrip()
                    q['stem'] = clean_stem
                    changes += 1
                    print(f"  Q6 題幹截斷: {len(stem)} -> {len(clean_stem)} 字元")

    if changes > 0:
        backup_file(fp)
        save_json(fp, d)

    return changes


def main():
    print("=== 內容品質修復 ===")
    print()

    # KR1 + KR2: Fix English reading comprehension passage leaks
    print("--- KR1+KR2: 修復英文閱讀測驗段落/選項混入 ---")
    files = glob.glob('考古題庫/**/試題.json', recursive=True)
    total_changes = 0
    files_changed = 0

    for fp in files:
        changes = fix_file(fp)
        if changes > 0:
            total_changes += changes
            files_changed += 1

    print(f"  修改 {files_changed} 個檔案, {total_changes} 處變更")
    print()

    # KR3: Fix detective Q6
    print("--- KR3: 修復行政警察 106年偵查法學 Q6 ---")
    kr3_changes = fix_detective_q6()
    print(f"  {kr3_changes} 處變更")
    print()

    # Verification
    print("--- 驗證 ---")
    leaked_opt = 0
    leaked_stem = 0
    meta_in_stem = 0

    for fp in files:
        d = load_json(fp)
        if d.get('metadata', {}).get('_is_duplicate'):
            continue
        for q in d.get('questions', []):
            if q.get('type') != 'choice':
                continue
            opts = q.get('options', {})
            stem = q.get('stem', '') or ''
            if 'D' in opts and '請依下文回答' in str(opts['D']):
                leaked_opt += 1
            if re.match(r'\s*[\(（][A-D][\)）]', stem):
                leaked_stem += 1
            if re.search(r'乙、測驗|代號[:：]\s*\d{4}', stem):
                meta_in_stem += 1

    print(f"  選項中段落殘留: {leaked_opt}")
    print(f"  題幹中選項殘留: {leaked_stem}")
    print(f"  題幹中 metadata: {meta_in_stem}")

    stats = {
        'total_changes': total_changes + kr3_changes,
        'files_changed': files_changed + (1 if kr3_changes else 0),
        'leaked_opt_remaining': leaked_opt,
        'leaked_stem_remaining': leaked_stem,
        'meta_remaining': meta_in_stem,
    }
    save_json('fix_content_stats.json', stats)
    print(f"\n統計已儲存: fix_content_stats.json")


if __name__ == '__main__':
    main()
