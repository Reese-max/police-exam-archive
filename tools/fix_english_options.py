#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修復英文閱讀測驗題目的選項和答案。

考選部英文 PDF 的選項格式不使用 (A)(B)(C)(D) 標記，
而是純文字排列（同行或多行），需要特殊處理。

用法:
    python tools/fix_english_options.py --dry-run    # 模擬
    python tools/fix_english_options.py              # 正式執行
"""

import json
import re
import os
import shutil
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("需要安裝 pdfplumber: pip install pdfplumber")
    raise

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAM_DB = PROJECT_ROOT / "考古題庫"
PDFS_MISSING = PROJECT_ROOT / "pdfs_missing"
BACKUPS_DIR = PROJECT_ROOT / "backups"

# 閱讀測驗段落標記
PASSAGE_HEADER = re.compile(r'請依下文回答第\s*(\d+)\s*題至第\s*(\d+)\s*題')
QUESTION_NUM = re.compile(r'^(\d{1,3})\s+(.+)')


def extract_pdf_lines(pdf_path):
    """從 PDF 提取所有行"""
    lines = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.split('\n'):
                    lines.append(line.strip())
    return lines


def is_header_or_note(line):
    """是否為考卷標頭或注意事項"""
    if not line:
        return True
    patterns = [
        r'^\d{2,3}年', r'^代號', r'^頁次', r'^考試', r'^等\s*別',
        r'^類\s*科', r'^科\s*目', r'^座號', r'^(全一|請接|背面|請翻)',
        r'^\d{5}$', r'^-?\d+-?$', r'注意', r'不必抄題', r'不予計分',
        r'鉛筆', r'鋼筆', r'本試題為', r'禁止使用', r'測驗題部分',
        r'^甲、', r'^乙、',
    ]
    for pat in patterns:
        if re.search(pat, line):
            return True
    return False


def parse_english_pdf_smart(pdf_path):
    """
    智慧解析英文 PDF，正確處理無 (A)(B)(C)(D) 標記的選項。

    策略：
    1. 找到所有題號行
    2. 收集每題的所有文字（從當前題號到下一題號之間）
    3. 對於 passage 題組，先提取 passage
    4. 對於克漏字（stem 很短），從 stem 行分割選項
    5. 對於閱讀理解（有問題句），從後續行分割選項
    """
    lines = extract_pdf_lines(pdf_path)

    # 第一步：找所有題號位置和 passage 位置
    question_positions = []  # [(line_idx, question_num, rest_of_line)]
    passage_positions = []   # [(line_idx, start_num, end_num)]

    for i, line in enumerate(lines):
        if is_header_or_note(line):
            continue

        # 檢查 passage header
        pm = PASSAGE_HEADER.search(line)
        if pm:
            passage_positions.append((i, int(pm.group(1)), int(pm.group(2))))
            continue

        # 檢查題號
        qm = QUESTION_NUM.match(line)
        if qm:
            num = int(qm.group(1))
            if 1 <= num <= 80:  # 合理題號範圍
                question_positions.append((i, num, qm.group(2)))

    # 第二步：建立 passage 映射
    passages = {}  # {題號: passage_text}
    for p_idx, start_num, end_num in passage_positions:
        # 收集 passage 文字直到第一個題號
        passage_lines = [lines[p_idx]]
        for j in range(p_idx + 1, len(lines)):
            # 停在下一個題號
            qm = QUESTION_NUM.match(lines[j])
            if qm and 1 <= int(qm.group(1)) <= 80:
                break
            if not is_header_or_note(lines[j]):
                passage_lines.append(lines[j])
        passage_text = ' '.join(passage_lines)
        for n in range(start_num, end_num + 1):
            passages[n] = passage_text

    # 第三步：解析每道題目
    questions = []
    for qi, (line_idx, qnum, rest) in enumerate(question_positions):
        # 收集此題的所有行（到下一題號之前）
        if qi + 1 < len(question_positions):
            next_idx = question_positions[qi + 1][0]
        else:
            next_idx = len(lines)

        q_lines = [rest]
        for j in range(line_idx + 1, next_idx):
            if not is_header_or_note(lines[j]):
                # 跳過 passage header 行
                if PASSAGE_HEADER.search(lines[j]):
                    continue
                q_lines.append(lines[j])

        # 組合所有文字
        full_text = ' '.join(q_lines).strip()

        # 嘗試分離 stem 和 options
        stem, options = split_stem_and_options(full_text, q_lines)

        q = {
            'number': qnum,
            'type': 'choice',
            'stem': stem,
            'section': '乙、測驗題',
        }

        if options and len(options) == 4:
            q['options'] = {
                'A': options[0],
                'B': options[1],
                'C': options[2],
                'D': options[3],
            }

        if qnum in passages:
            q['passage'] = passages[qnum]
            q['subtype'] = 'reading_comprehension'

        questions.append(q)

    return questions


def split_stem_and_options(full_text, q_lines):
    """
    從題目文字中分離 stem 和 4 個選項。

    格式類型：
    1. 克漏字（全短選項在同一行）: "assess allow appoint approach"
    2. 閱讀理解（長選項各佔一行）:
       "According to the passage, which...?
        Option A text.
        Option B text.
        Option C text.
        Option D text."
    3. 混合: stem + 最後一行有4個短選項
    """
    # 先檢查是否有 (A)(B)(C)(D) 格式
    opt_match = re.findall(r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=[\(（][A-Da-d][\)）]|$)', full_text)
    if len(opt_match) == 4:
        # 找到標準格式選項
        first_opt = full_text.find('(A)')
        if first_opt == -1:
            first_opt = full_text.find('（A）')
        stem = full_text[:first_opt].strip() if first_opt > 0 else ''
        return stem, [m[1].strip() for m in opt_match]

    # 類型1：克漏字 - 整行都是4個短選項（通常單字或短語）
    # 檢查是否整個文字就是4個短元素
    words = full_text.split()
    if len(words) == 4 and all(len(w) < 30 for w in words):
        return '', list(words)

    # 類型3：stem + 最後一行4個短選項
    if len(q_lines) >= 2:
        last_line = q_lines[-1].strip()
        last_words = last_line.split()
        if len(last_words) == 4 and all(len(w) < 30 for w in last_words):
            stem = ' '.join(q_lines[:-1]).strip()
            return stem, list(last_words)

        # 也檢查最後一行是否是用空格分隔的4個選項
        # 例如 "3/4 1/4 3/5 4/5"
        parts = re.split(r'\s{2,}', last_line)
        if len(parts) == 4:
            stem = ' '.join(q_lines[:-1]).strip()
            return stem, [p.strip() for p in parts]

    # 類型2：閱讀理解 - 題幹以問號結尾，後面每行一個選項
    # 找問號位置
    q_mark_pos = -1
    for marker in ['？', '?']:
        pos = full_text.rfind(marker)
        if pos > 0:
            q_mark_pos = pos
            break

    if q_mark_pos > 0 and len(q_lines) >= 2:
        # 找問號在哪一行
        cum_len = 0
        stem_line_idx = 0
        for idx, line in enumerate(q_lines):
            cum_len += len(line) + 1
            if '？' in line or '?' in line:
                stem_line_idx = idx
                break

        remaining_lines = [l.strip() for l in q_lines[stem_line_idx + 1:] if l.strip()]

        if len(remaining_lines) == 4:
            stem = ' '.join(q_lines[:stem_line_idx + 1]).strip()
            return stem, remaining_lines

        # 有時候選項會跨行（特別是長選項），嘗試合併
        if len(remaining_lines) > 4:
            # 嘗試按句點分割
            combined = ' '.join(remaining_lines)
            # 用句點或大寫開頭分割
            sentences = re.split(r'(?<=[.。])\s+(?=[A-Z])', combined)
            if len(sentences) == 4:
                stem = ' '.join(q_lines[:stem_line_idx + 1]).strip()
                return stem, [s.strip() for s in sentences]

    # 最後嘗試：如果只有一行，可能是 stem 和選項混合
    if len(q_lines) == 1:
        # 嘗試用大量空格分割
        parts = re.split(r'\s{3,}', full_text)
        if len(parts) == 4:
            return '', [p.strip() for p in parts]
        if len(parts) == 5:
            return parts[0].strip(), [p.strip() for p in parts[1:]]

    # 無法分離，返回原文作為 stem
    return full_text, []


def find_answer_keys():
    """
    從考選部試題答案中建立答案對照表。
    嘗試從現有 JSON 中已有答案的同題號取得。
    """
    answers = {}  # {(year, subject_keyword, qnum): answer}

    for json_file in EXAM_DB.rglob("試題.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        year_dir = json_file.parent.parent.name  # "106年"
        subject_dir = json_file.parent.name

        for q in data.get('questions', []):
            if q.get('type') == 'choice' and q.get('answer') and q.get('options'):
                num = q['number']
                key = (year_dir, subject_dir, num)
                answers[key] = q['answer']

    return answers


def fix_questions_in_json(json_path, pdf_questions, answer_keys, dry_run=False):
    """
    修復 JSON 中缺選項的題目。

    Args:
        json_path: 目標 JSON
        pdf_questions: 從 PDF 解析出的題目列表（含選項）
        answer_keys: 全域答案對照表
        dry_run: 是否模擬

    Returns:
        int: 修復題數
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    year_dir = json_path.parent.parent.name
    subject_dir = json_path.parent.name

    # 建立 PDF 題目索引
    pdf_q_map = {q['number']: q for q in pdf_questions}

    fixed = 0
    for q in data.get('questions', []):
        if q.get('type') != 'choice':
            continue
        num = q.get('number')
        if not isinstance(num, int):
            continue

        needs_fix = (not q.get('options') or len(q.get('options', {})) < 4)

        if not needs_fix:
            continue

        # 從 PDF 結果找對應題目
        if num in pdf_q_map:
            pdf_q = pdf_q_map[num]
            if pdf_q.get('options') and len(pdf_q['options']) == 4:
                if dry_run:
                    print(f"  [DRY-RUN] 修復 Q{num}: 加入選項 {list(pdf_q['options'].keys())}")
                else:
                    q['options'] = pdf_q['options']
                    if pdf_q.get('stem') and len(pdf_q['stem']) > len(q.get('stem', '')):
                        q['stem'] = pdf_q['stem']
                    if pdf_q.get('passage') and not q.get('passage'):
                        q['passage'] = pdf_q['passage']
                        q['subtype'] = 'reading_comprehension'

                # 嘗試找答案
                if not q.get('answer'):
                    key = (year_dir, subject_dir, num)
                    if key in answer_keys:
                        if not dry_run:
                            q['answer'] = answer_keys[key]
                        print(f"  [{'DRY-RUN' if dry_run else 'OK'}] Q{num}: 從答案庫找到答案 {answer_keys[key]}")

                fixed += 1

    if not dry_run and fixed > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')

    return fixed


def main():
    import argparse
    parser = argparse.ArgumentParser(description='修復英文閱讀測驗的選項和答案')
    parser.add_argument('--dry-run', action='store_true', help='只顯示不寫入')
    parser.add_argument('-v', '--verbose', action='store_true', help='詳細輸出')
    args = parser.parse_args()

    print("=" * 60)
    print("  英文閱讀測驗選項修復器")
    print("=" * 60)

    if args.dry_run:
        print("[MODE] 模擬執行\n")

    # 備份
    backup_dir = None
    if not args.dry_run:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = BACKUPS_DIR / f"fix_english_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 備份目錄: {backup_dir}\n")

    # 建立答案庫
    print("載入答案庫...")
    answer_keys = find_answer_keys()
    print(f"答案庫: {len(answer_keys)} 筆\n")

    # 找所有需要修復的 JSON（英文科、有缺選項的題目）
    print("掃描需要修復的檔案...")
    files_to_fix = []  # [(json_path, missing_nums)]
    for json_file in sorted(EXAM_DB.rglob("試題.json")):
        if '英文' not in json_file.parent.name:
            continue
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        missing = []
        for q in data.get('questions', []):
            if q.get('type') == 'choice' and isinstance(q.get('number'), int):
                if not q.get('options') or len(q.get('options', {})) < 4:
                    missing.append(q['number'])
        if missing:
            files_to_fix.append((json_file, missing))

    print(f"需修復: {len(files_to_fix)} 個檔案, 共 {sum(len(m) for _, m in files_to_fix)} 題\n")

    if not files_to_fix:
        print("無需修復！")
        return

    # 解析所有英文 PDF
    print("解析英文 PDF...")
    pdf_results = {}  # {(year, subject_keyword): [questions]}
    for pdf_file in sorted(PDFS_MISSING.rglob("*.pdf")):
        if '英文' not in pdf_file.name:
            continue
        year_dir = pdf_file.parent.name  # "106年"
        print(f"  解析: {year_dir}/{pdf_file.name}")
        questions = parse_english_pdf_smart(pdf_file)
        with_opts = sum(1 for q in questions if q.get('options') and len(q['options']) == 4)
        print(f"    {len(questions)} 題, {with_opts} 有完整選項")
        pdf_results[(year_dir, pdf_file.stem)] = questions

    # 修復每個檔案
    print(f"\n{'=' * 60}")
    print("  開始修復")
    print(f"{'=' * 60}\n")

    total_fixed = 0
    for json_path, missing_nums in files_to_fix:
        rel = json_path.relative_to(EXAM_DB)
        year_dir = json_path.parent.parent.name
        print(f"\n--- {rel} (缺 Q{missing_nums}) ---")

        # 備份
        if backup_dir and not args.dry_run:
            bk = backup_dir / rel
            bk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_path, bk)

        # 找匹配的 PDF 結果
        best_match = None
        best_count = 0
        for (py, pname), pqs in pdf_results.items():
            if py != year_dir:
                continue
            # 計算有多少缺失題號在 PDF 結果中有選項
            matched = sum(1 for q in pqs
                         if q['number'] in missing_nums
                         and q.get('options')
                         and len(q['options']) == 4)
            if matched > best_count:
                best_count = matched
                best_match = pqs

        if best_match:
            fixed = fix_questions_in_json(
                json_path, best_match, answer_keys, args.dry_run
            )
            if fixed:
                print(f"  修復 {fixed} 題")
                total_fixed += fixed
            else:
                print(f"  [WARN] PDF 解析未能提取選項")
        else:
            print(f"  [WARN] 找不到匹配的 PDF 結果")

    print(f"\n{'=' * 60}")
    print(f"  總計修復: {total_fixed} 題")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
