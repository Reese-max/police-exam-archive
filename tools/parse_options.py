# -*- coding: utf-8 -*-
"""
選項解析工具 — 將選擇題 stem 中的 (A)(B)(C)(D) 拆為獨立 options 欄位

用法:
  python tools/parse_options.py                    # 處理所有 JSON 檔案
  python tools/parse_options.py --dry-run          # 只顯示會怎麼改，不實際寫入
  python tools/parse_options.py --category 行政警察 # 只處理特定類科
"""

import os
import re
import json
import argparse
from pathlib import Path

# 選項標記的 regex：匹配 (A) (B) (C) (D) 及全形括號版本
# 也匹配 (E) 以防有五選一的題目
OPTION_PATTERN = re.compile(
    r'[\s\u3000]*[（(]\s*([A-E])\s*[）)]\s*'
)

# 用來偵測 stem 是否以選項開頭（填空題）
STARTS_WITH_OPTION = re.compile(
    r'^\s*[（(]\s*[A-E]\s*[）)]'
)

# OCR 常見行末雜訊
TRAILING_NOISE = re.compile(r'\s*-\s*、\s*$')
# 多餘空格（中文字間不該有空格的情況除外，保守處理）
MULTIPLE_SPACES = re.compile(r'  +')


def clean_text(text):
    """清理 OCR 瑕疵"""
    if not text:
        return text
    # 移除行末 "- 、" 雜訊
    text = TRAILING_NOISE.sub('', text)
    # 合併多餘空格
    text = MULTIPLE_SPACES.sub(' ', text)
    return text.strip()


def parse_options_from_stem(stem):
    """
    從 stem 中解析出選項 (A)(B)(C)(D)，回傳 (clean_stem, options_dict)

    Returns:
        tuple: (stem_without_options, {'A': '...', 'B': '...', ...}) or (stem, None) if no options found
    """
    if not stem:
        return stem, None

    # 找所有選項標記的位置
    matches = list(OPTION_PATTERN.finditer(stem))

    if not matches:
        return stem, None

    # 至少需要 2 個選項才認定為有效選項格式
    labels = [m.group(1) for m in matches]

    # 找出連續的 A, B, C, D 序列
    # 有些題目 stem 中可能包含 "(A)" 但不是選項（如引用文章）
    # 策略：找最後一組 A 開頭的連續序列
    best_start_idx = None
    for i, label in enumerate(labels):
        if label == 'A':
            # 檢查從這個 A 開始是否有連續的 B, C, D
            seq = [labels[j] for j in range(i, len(labels))]
            expected = list('ABCD')[:len(seq)]
            if len(seq) >= 2 and seq[:len(expected)] == expected:
                best_start_idx = i

    if best_start_idx is None:
        return stem, None

    # 使用找到的最佳起始位置
    option_matches = matches[best_start_idx:]
    option_labels = [m.group(1) for m in option_matches]

    # 確認至少有 A 和 B
    if 'A' not in option_labels or 'B' not in option_labels:
        return stem, None

    # 提取各選項文字
    options = {}
    first_match = option_matches[0]
    stem_part = stem[:first_match.start()]

    for i, match in enumerate(option_matches):
        label = match.group(1)
        start = match.end()
        if i + 1 < len(option_matches):
            end = option_matches[i + 1].start()
        else:
            end = len(stem)
        option_text = stem[start:end].strip()
        option_text = clean_text(option_text)
        options[label] = option_text

    stem_part = clean_text(stem_part)

    return stem_part, options


def process_question(question):
    """處理單一題目，回傳是否有修改"""
    if question.get('type') != 'choice':
        # 申論題也做文字清理
        if question.get('stem'):
            cleaned = clean_text(question['stem'])
            if cleaned != question['stem']:
                question['stem'] = cleaned
                return True
        return False

    # 如果已經有 options 欄位且不為空，跳過
    if question.get('options') and len(question['options']) >= 2:
        # 但還是做文字清理
        changed = False
        if question.get('stem'):
            cleaned = clean_text(question['stem'])
            if cleaned != question['stem']:
                question['stem'] = cleaned
                changed = True
        for key in list(question.get('options', {}).keys()):
            cleaned = clean_text(question['options'][key])
            if cleaned != question['options'][key]:
                question['options'][key] = cleaned
                changed = True
        return changed

    # 從 stem 中解析選項
    stem = question.get('stem', '')
    new_stem, options = parse_options_from_stem(stem)

    if options is None:
        # 沒找到選項，只做文字清理
        cleaned = clean_text(stem)
        if cleaned != stem:
            question['stem'] = cleaned
            return True
        return False

    question['stem'] = new_stem
    question['options'] = options
    return True


def process_json_file(json_path, dry_run=False):
    """處理單一 JSON 檔案"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [跳過] {json_path}: {e}")
        return 0

    questions = data.get('questions', [])
    if not questions:
        return 0

    modified_count = 0
    for q in questions:
        if process_question(q):
            modified_count += 1

    if modified_count > 0 and not dry_run:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return modified_count


def main():
    parser = argparse.ArgumentParser(description='解析選擇題選項')
    parser.add_argument('--input', default='考古題庫', help='輸入目錄')
    parser.add_argument('--category', help='只處理特定類科')
    parser.add_argument('--dry-run', action='store_true', help='不實際寫入')
    args = parser.parse_args()

    base_dir = Path(args.input)
    if not base_dir.exists():
        # 嘗試相對於腳本目錄
        base_dir = Path(__file__).parent.parent / args.input
    if not base_dir.exists():
        print(f"找不到目錄: {args.input}")
        return

    total_files = 0
    total_modified = 0
    total_questions_modified = 0

    for json_path in sorted(base_dir.rglob('試題.json')):
        if args.category:
            if args.category not in str(json_path):
                continue

        rel_path = json_path.relative_to(base_dir)
        modified = process_json_file(str(json_path), dry_run=args.dry_run)
        total_files += 1

        if modified > 0:
            total_modified += 1
            total_questions_modified += modified
            action = "[預覽]" if args.dry_run else "[更新]"
            print(f"  {action} {rel_path}: {modified} 題已處理")

    print(f"\n{'=' * 50}")
    print(f"處理完成:")
    print(f"  掃描檔案: {total_files}")
    print(f"  修改檔案: {total_modified}")
    print(f"  修改題目: {total_questions_modified}")
    if args.dry_run:
        print("  (dry-run 模式，未實際寫入)")


if __name__ == '__main__':
    main()
