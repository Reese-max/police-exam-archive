#!/usr/bin/env python3
"""修復 PDF 萃取文字品質問題

KR1: 替換 PUA 字元 (ue18c-ue18f) → (A)-(D)
KR2: 用 wordninja 分離英文連字
"""

import json
import glob
import re
import os
import shutil
import wordninja
from datetime import datetime


# PUA character mapping from PDF font encoding
PUA_MAP = {
    '\ue18c': '(A)',
    '\ue18d': '(B)',
    '\ue18e': '(C)',
    '\ue18f': '(D)',
}
PUA_RE = re.compile('[\ue18c-\ue18f]')

# Detect concatenated English words: lowercase followed by uppercase
# e.g., "wasArrestedBecause" or all-lowercase long strings
CAMEL_RE = re.compile(r'([a-z])([A-Z])')

# Long all-lowercase English words (18+ chars) that are likely concatenated
LONG_LOWER_RE = re.compile(r'\b([a-z]{18,})\b')

# Protect known legitimate long words and patterns
LEGITIMATE_LONG = {
    'internationalization', 'internationalize', 'counterintelligence',
    'telecommunications', 'telecommunication', 'unconstitutional',
    'counterterrorism', 'multidisciplinary', 'interdisciplinary',
    'disproportionately', 'disproportionate', 'environmentally',
    'environmentalist', 'electromagnetic', 'constitutionality',
    'constitutionally', 'characteristically', 'pharmaceutical',
    'pharmaceuticals', 'entrepreneurship', 'extraordinarily',
    'comprehensively', 'counterproductive', 'professionalism',
    'notwithstanding', 'straightforward', 'acknowledgement',
    'acknowledgment', 'overrepresented', 'underrepresented',
    'misrepresentation', 'misunderstanding', 'indistinguishable',
    'incomprehensible', 'transportation', 'responsibilities',
    'representatives', 'superintendent', 'overwhelmingly',
    'characterization', 'discrimination', 'whistleblowers',
    'whichofthefollowing',  # This is actually concatenated, don't protect
}

# Only protect words that are actual single English words
REAL_LONG_WORDS = set()
for w in LEGITIMATE_LONG:
    # Verify with wordninja - if it stays as one word, it's legitimate
    split = wordninja.split(w)
    if len(split) == 1:
        REAL_LONG_WORDS.add(w.lower())


def load_json(fp):
    with open(fp, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(fp, data):
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_file(fp):
    backup_dir = f"backups/text_quality_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    rel = os.path.relpath(fp)
    dest = os.path.join(backup_dir, rel.replace(os.sep, '_'))
    shutil.copy2(fp, dest)
    return dest


def fix_pua_chars(text):
    """替換 PUA 字元為 (A)-(D)"""
    if not text:
        return text, 0
    count = len(PUA_RE.findall(text))
    if count == 0:
        return text, 0
    result = PUA_RE.sub(lambda m: PUA_MAP.get(m.group(), m.group()), text)
    return result, count


def fix_english_concat(text):
    """修復英文連字問題

    策略:
    1. 先處理 camelCase 邊界 (wasArrested → was Arrested)
    2. 再用 wordninja 處理全小寫長字串
    """
    if not text:
        return text, 0

    changes = 0

    # Step 1: Split at camelCase boundaries
    # But only for sequences that look like concatenated words, not acronyms
    def split_camel(m):
        return m.group(1) + ' ' + m.group(2)

    new_text = CAMEL_RE.sub(split_camel, text)
    if new_text != text:
        changes += 1
        text = new_text

    # Step 2: Find remaining long lowercase words and split with wordninja
    def split_long_word(m):
        word = m.group(1)
        if word.lower() in REAL_LONG_WORDS:
            return word
        split = wordninja.split(word)
        if len(split) > 1:
            return ' '.join(split)
        return word

    new_text = LONG_LOWER_RE.sub(split_long_word, text)
    if new_text != text:
        changes += 1
        text = new_text

    return text, changes


def fix_file(fp, dry_run=False):
    """修復單一檔案"""
    d = load_json(fp)
    if d.get('metadata', {}).get('_is_duplicate'):
        return {'pua': 0, 'concat': 0}

    pua_total = 0
    concat_total = 0

    for q in d.get('questions', []):
        # Fix stem
        stem = q.get('stem', '') or ''
        if stem:
            stem, pua_c = fix_pua_chars(stem)
            pua_total += pua_c
            stem, concat_c = fix_english_concat(stem)
            concat_total += concat_c
            q['stem'] = stem

        # Fix passage
        passage = q.get('passage', '') or ''
        if passage:
            passage, pua_c = fix_pua_chars(passage)
            pua_total += pua_c
            passage, concat_c = fix_english_concat(passage)
            concat_total += concat_c
            q['passage'] = passage

        # Fix options
        opts = q.get('options', {})
        if opts:
            for k in list(opts.keys()):
                v = str(opts[k])
                v, pua_c = fix_pua_chars(v)
                pua_total += pua_c
                v, concat_c = fix_english_concat(v)
                concat_total += concat_c
                opts[k] = v

    total = pua_total + concat_total
    if total > 0 and not dry_run:
        backup_file(fp)
        save_json(fp, d)

    return {'pua': pua_total, 'concat': concat_total}


def verify():
    """驗證修復結果"""
    files = glob.glob('考古題庫/**/試題.json', recursive=True)
    pua_remaining = 0
    concat_remaining = 0
    long_words_remaining = 0

    for fp in files:
        d = load_json(fp)
        if d.get('metadata', {}).get('_is_duplicate'):
            continue
        for q in d.get('questions', []):
            for field in ['stem', 'passage']:
                text = q.get(field, '') or ''
                pua_remaining += len(PUA_RE.findall(text))
                if CAMEL_RE.search(text):
                    concat_remaining += 1
                long_words_remaining += len(LONG_LOWER_RE.findall(text))
            for v in (q.get('options', {}) or {}).values():
                vs = str(v)
                pua_remaining += len(PUA_RE.findall(vs))
                if CAMEL_RE.search(vs):
                    concat_remaining += 1
                long_words_remaining += len(LONG_LOWER_RE.findall(vs))

    return {
        'pua_remaining': pua_remaining,
        'concat_camel_remaining': concat_remaining,
        'long_words_remaining': long_words_remaining,
    }


def main():
    print("=== PDF 萃取文字品質修復 ===")
    print()

    files = glob.glob('考古題庫/**/試題.json', recursive=True)
    total_pua = 0
    total_concat = 0
    files_changed = 0

    for fp in files:
        result = fix_file(fp)
        if result['pua'] + result['concat'] > 0:
            files_changed += 1
            total_pua += result['pua']
            total_concat += result['concat']

    print(f"修改 {files_changed} 個檔案")
    print(f"  PUA 字元替換: {total_pua}")
    print(f"  英文連字修復: {total_concat}")
    print()

    print("--- 驗證 ---")
    v = verify()
    print(f"  PUA 殘留: {v['pua_remaining']}")
    print(f"  camelCase 殘留: {v['concat_camel_remaining']}")
    print(f"  超長單字殘留: {v['long_words_remaining']}")

    stats = {
        'files_changed': files_changed,
        'pua_fixed': total_pua,
        'concat_fixed': total_concat,
        **v,
    }
    save_json('fix_text_quality_stats.json', stats)
    print(f"\n統計已儲存: fix_text_quality_stats.json")


if __name__ == '__main__':
    main()
