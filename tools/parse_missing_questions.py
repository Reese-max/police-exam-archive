#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析 pdfs_missing/ 目錄中下載的 PDF，提取缺失的題目並寫入對應的 JSON。

處理兩類缺失：
1. 整題遺失（5 筆）— 從 PDF 中找到特定題號
2. 英文閱讀測驗（~128 題）— 提取 passage + cloze/reading comprehension

用法:
    python tools/parse_missing_questions.py                 # 正式執行
    python tools/parse_missing_questions.py --dry-run       # 只顯示不寫入
    python tools/parse_missing_questions.py --verbose       # 詳細輸出
"""

import os
import re
import json
import copy
import shutil
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("需要安裝 pdfplumber: pip install pdfplumber")
    raise

# ===== 專案根目錄 =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAM_DB = PROJECT_ROOT / "考古題庫"
PDFS_MISSING = PROJECT_ROOT / "pdfs_missing"
REPORTS_DIR = PROJECT_ROOT / "reports"
BACKUPS_DIR = PROJECT_ROOT / "backups"

# ===== 正則模式（取自 pdf_to_questions.py）=====
CHOICE_Q_PATTERN = re.compile(
    r'^[\s]*(\d{1,3})\s*[\.、．)\s]\s*(.+)', re.DOTALL
)

OPTION_PATTERN = re.compile(
    r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=[\(（][A-Da-d][\)）]|$)',
    re.DOTALL
)

INLINE_OPTIONS_PATTERN = re.compile(
    r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=\s*[\(（][A-Da-d][\)）]|\s*$)'
)

SECTION_PATTERN = re.compile(
    r'^[\s]*(甲|乙)\s*[、．.]\s*(申論題|測驗題|選擇題)'
)

ESSAY_Q_PATTERN = re.compile(
    r'^[\s]*([一二三四五六七八九十]+)\s*[、．.]\s*(.+)', re.DOTALL
)

HEADER_LINE_PATTERNS = [
    re.compile(r'^\d{2,3}年(公務|特種)'),
    re.compile(r'^代號[:：]'),
    re.compile(r'^頁次[:：]'),
    re.compile(r'^考試(別|時間)'),
    re.compile(r'^等\s*別[:：]'),
    re.compile(r'^類\s*科'),
    re.compile(r'^科\s*目[:：]'),
    re.compile(r'^座號'),
    re.compile(r'^(全一張|全一頁)'),
    re.compile(r'^-?\d+-?$'),
    re.compile(r'^\d{5}$'),
    re.compile(r'^(請接背面|請以背面)'),
    re.compile(r'^(背面尚有|請翻頁)'),
]

NOTE_PATTERN = re.compile(r'^[\s]*[※＊\*]?\s*注意\s*[：:]')

# 閱讀測驗段落標記
PASSAGE_HEADER_PATTERN = re.compile(
    r'請依下文回答第\s*(\d+)\s*題至第\s*(\d+)\s*題'
)

# OCR 修復規則（簡化版）
OCR_FIXES = [
    (re.compile(r'(\w)ti on\b'), r'\1tion'),
    (re.compile(r'(\w)si on\b'), r'\1sion'),
    (re.compile(r'\bth at\b'), 'that'),
    (re.compile(r'\bth is\b'), 'this'),
    (re.compile(r'\bth e\b'), 'the'),
    (re.compile(r'\bth ey\b'), 'they'),
    (re.compile(r'\bth eir\b'), 'their'),
    (re.compile(r'\bth ere\b'), 'there'),
    (re.compile(r'\bth ese\b'), 'these'),
    (re.compile(r'\bth ose\b'), 'those'),
    (re.compile(r'\bth rough\b'), 'through'),
    (re.compile(r'\bwh at\b'), 'what'),
    (re.compile(r'\bwh en\b'), 'when'),
    (re.compile(r'\bwh ere\b'), 'where'),
    (re.compile(r'\bwh ich\b'), 'which'),
    (re.compile(r'\bwh ile\b'), 'while'),
    (re.compile(r'\bf or\b'), 'for'),
    (re.compile(r'\bf rom\b'), 'from'),
    (re.compile(r'\bin to\b'), 'into'),
    (re.compile(r'\bhum an\b'), 'human'),
    (re.compile(r'\bpers on\b'), 'person'),
    (re.compile(r'\bpris on\b'), 'prison'),
    (re.compile(r'\breas on\b'), 'reason'),
    (re.compile(r'\bcomm on\b'), 'common'),
    (re.compile(r'\bmonit or\b'), 'monitor'),
]


def fix_ocr(text):
    """套用 OCR 修復規則"""
    for pattern, replacement in OCR_FIXES:
        text = pattern.sub(replacement, text)
    return text


def normalize_text(text):
    """正規化文字"""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\b\d{5}\b', '', text)  # 移除考卷代號
    text = fix_ocr(text)
    return text.strip()


def is_header_line(line):
    """判斷是否為考卷標頭行"""
    line = line.strip()
    if not line:
        return True
    for pat in HEADER_LINE_PATTERNS:
        if pat.match(line):
            return True
    if any(kw in line for kw in ['人員考試', '考試別', '退除役軍人']):
        if len(line) < 80:
            return True
    return False


def is_note_line(line):
    """判斷是否為注意事項"""
    line = line.strip()
    return bool(NOTE_PATTERN.match(line)) or \
        '不必抄題' in line or '不予計分' in line or \
        '禁止使用電子計算器' in line or \
        '本試題為單一選擇題' in line or \
        '鋼筆或原子筆' in line or \
        '2B鉛筆' in line or \
        '應使用本國文字' in line or \
        '可以使用電子計算器' in line


def extract_pdf_text(pdf_path):
    """從 PDF 提取文字"""
    pages_text = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return pages_text


def extract_content_lines(pages_text):
    """從 PDF 文字中提取內容行（排除標頭和注意事項）"""
    content_lines = []
    in_note = False

    for page_text in pages_text:
        for line in page_text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            if is_header_line(stripped):
                continue

            if is_note_line(stripped):
                in_note = True
                continue

            if in_note and not CHOICE_Q_PATTERN.match(stripped) and \
               not ESSAY_Q_PATTERN.match(stripped) and \
               not SECTION_PATTERN.match(stripped):
                continue

            in_note = False
            content_lines.append(stripped)

    return content_lines


def parse_single_question(content_lines, start_idx, target_num=None):
    """
    從 content_lines 的 start_idx 開始解析一道選擇題。

    Args:
        content_lines: 所有內容行
        start_idx: 開始位置
        target_num: 如果指定，只找這個題號

    Returns:
        (question_dict, next_idx) 或 (None, next_idx)
    """
    i = start_idx
    while i < len(content_lines):
        line = content_lines[i]

        choice_match = CHOICE_Q_PATTERN.match(line)
        if choice_match:
            num = int(choice_match.group(1))

            if target_num is not None and num != target_num:
                i += 1
                continue

            stem = choice_match.group(2).strip()

            # 收集題幹後續行和選項
            i += 1
            options_text = ''
            while i < len(content_lines):
                next_line = content_lines[i]
                if CHOICE_Q_PATTERN.match(next_line) or \
                   ESSAY_Q_PATTERN.match(next_line) or \
                   SECTION_PATTERN.match(next_line):
                    break

                if re.match(r'\s*[\(（][A-Da-d][\)）]', next_line):
                    options_text += ' ' + next_line
                elif options_text:
                    options_text += ' ' + next_line
                else:
                    stem += ' ' + next_line
                i += 1

            # 解析選項
            options = {}
            if options_text:
                opt_matches = INLINE_OPTIONS_PATTERN.findall(options_text)
                for label, text in opt_matches:
                    options[label.upper()] = normalize_text(text.strip())

            # 也嘗試從題幹末尾提取選項
            if not options:
                opt_matches = INLINE_OPTIONS_PATTERN.findall(stem)
                if opt_matches:
                    first_opt_pos = stem.find('(A)')
                    if first_opt_pos == -1:
                        first_opt_pos = stem.find('（A）')
                    if first_opt_pos > 0:
                        options_part = stem[first_opt_pos:]
                        stem = stem[:first_opt_pos].strip()
                        opt_matches = INLINE_OPTIONS_PATTERN.findall(options_part)
                        for label, text in opt_matches:
                            options[label.upper()] = normalize_text(text.strip())

            q = {
                'number': num,
                'type': 'choice',
                'stem': normalize_text(stem),
                'section': '乙、測驗題',
            }
            if options:
                q['options'] = options
            return q, i

        i += 1

    return None, i


def parse_all_questions_from_pdf(pdf_path):
    """解析 PDF 中的所有選擇題"""
    pages_text = extract_pdf_text(pdf_path)
    if not pages_text:
        return []

    content_lines = extract_content_lines(pages_text)
    questions = []
    i = 0
    while i < len(content_lines):
        q, i = parse_single_question(content_lines, i)
        if q:
            questions.append(q)
        else:
            i += 1
    return questions


def extract_specific_question(pdf_path, target_num):
    """從 PDF 中提取特定題號的選擇題"""
    pages_text = extract_pdf_text(pdf_path)
    if not pages_text:
        return None

    content_lines = extract_content_lines(pages_text)
    i = 0
    while i < len(content_lines):
        q, i = parse_single_question(content_lines, i, target_num=target_num)
        if q:
            return q
    return None


def parse_reading_comprehension(pdf_path):
    """
    解析英文閱讀測驗 PDF，提取所有題目包括 passage。

    Returns:
        list[dict]: 含 passage 和 subtype 的題目列表
    """
    pages_text = extract_pdf_text(pdf_path)
    if not pages_text:
        return []

    full_text = '\n'.join(pages_text)
    content_lines = extract_content_lines(pages_text)

    # 先做一遍基本解析
    questions = []
    i = 0
    while i < len(content_lines):
        q, i = parse_single_question(content_lines, i)
        if q:
            questions.append(q)
        else:
            i += 1

    if not questions:
        return []

    # 找出 passage 段落，並關聯到對應題目
    # 掃描所有內容行尋找 passage header
    passage_ranges = []  # [(start_num, end_num, passage_text)]

    for idx, line in enumerate(content_lines):
        m = PASSAGE_HEADER_PATTERN.search(line)
        if m:
            start_num = int(m.group(1))
            end_num = int(m.group(2))

            # 收集 passage 文字（從 header 到下一個題號之前）
            passage_text = line
            for j in range(idx + 1, len(content_lines)):
                if CHOICE_Q_PATTERN.match(content_lines[j]):
                    break
                passage_text += ' ' + content_lines[j]

            passage_ranges.append((start_num, end_num, normalize_text(passage_text)))

    # 為相關題目標記 passage 和 subtype
    for q in questions:
        num = q['number']
        for start_num, end_num, passage in passage_ranges:
            if start_num <= num <= end_num:
                q['passage'] = passage
                # 判斷是克漏字還是閱讀理解
                if not q['stem'] or len(q['stem']) < 20:
                    q['subtype'] = 'cloze'
                else:
                    q['subtype'] = 'reading_comprehension'
                break

    return questions


def load_answer_key(json_path):
    """
    從同目錄的答案.json載入正確答案。

    Returns:
        dict: {題號: 答案} 或空 dict
    """
    answer_path = json_path.parent / "答案.json"
    if not answer_path.exists():
        return {}

    with open(answer_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    answers = {}
    for q in data.get('questions', []):
        if q.get('type') == 'choice' and 'number' in q and 'answer' in q:
            answers[q['number']] = q['answer']
    return answers


def find_answer_for_question(num, json_path):
    """
    嘗試從多處找到題目答案。

    1. 同目錄的答案.json
    2. 考古題庫中同科目的答案.json
    """
    # 先查同目錄
    answers = load_answer_key(json_path)
    if num in answers:
        return answers[num]

    # 查考古題庫
    if EXAM_DB.exists():
        for answer_file in EXAM_DB.rglob("答案.json"):
            try:
                with open(answer_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 只在同科目/同年的答案中查
                if data.get('subject') == json_path.parent.name:
                    year_dir = json_path.parent.parent.name
                    if year_dir in str(answer_file):
                        for q in data.get('questions', []):
                            if q.get('number') == num and q.get('answer'):
                                return q['answer']
            except (json.JSONDecodeError, KeyError):
                continue

    return ""


def load_json(path):
    """讀取 JSON 檔案"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    """寫入 JSON 檔案"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def backup_json(json_path, backup_dir):
    """備份 JSON 檔案"""
    rel = json_path.relative_to(EXAM_DB)
    backup_path = backup_dir / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(json_path, backup_path)
    return backup_path


def insert_question_into_json(json_path, question, dry_run=False, backup_dir=None):
    """
    將一道題目插入 JSON 檔案。

    Args:
        json_path: 目標 JSON 路徑
        question: 題目 dict
        dry_run: 只顯示不寫入
        backup_dir: 備份目錄

    Returns:
        bool: 是否成功插入
    """
    if not json_path.exists():
        print(f"  [ERROR] JSON 不存在: {json_path}")
        return False

    data = load_json(json_path)
    existing_nums = set()
    for q in data.get('questions', []):
        if q.get('type') == 'choice' and isinstance(q.get('number'), int):
            existing_nums.add(q['number'])

    num = question['number']
    if num in existing_nums:
        print(f"  [SKIP] Q{num} 已存在於 {json_path.name}")
        return False

    if dry_run:
        print(f"  [DRY-RUN] 會插入 Q{num} 到 {json_path}")
        return True

    # 備份
    if backup_dir:
        backup_json(json_path, backup_dir)

    # 插入題目
    data['questions'].append(question)

    # 排序：申論題先（按原始順序），選擇題按 number 排序
    essays = [q for q in data['questions'] if q.get('type') != 'choice']
    choices = [q for q in data['questions'] if q.get('type') == 'choice']
    choices.sort(key=lambda q: q.get('number', 0))
    data['questions'] = essays + choices

    save_json(json_path, data)
    print(f"  [OK] 插入 Q{num} 到 {json_path}")
    return True


def insert_questions_into_json(json_path, questions, dry_run=False, backup_dir=None):
    """
    將多道題目插入 JSON 檔案。

    Returns:
        int: 成功插入的題數
    """
    if not json_path.exists():
        print(f"  [ERROR] JSON 不存在: {json_path}")
        return 0

    data = load_json(json_path)
    existing_nums = set()
    for q in data.get('questions', []):
        if q.get('type') == 'choice' and isinstance(q.get('number'), int):
            existing_nums.add(q['number'])

    to_insert = [q for q in questions if q['number'] not in existing_nums]
    if not to_insert:
        print(f"  [SKIP] 所有題目都已存在於 {json_path}")
        return 0

    if dry_run:
        for q in to_insert:
            print(f"  [DRY-RUN] 會插入 Q{q['number']} 到 {json_path}")
        return len(to_insert)

    # 備份
    if backup_dir:
        backup_json(json_path, backup_dir)

    # 插入
    data['questions'].extend(copy.deepcopy(to_insert))

    # 排序
    essays = [q for q in data['questions'] if q.get('type') != 'choice']
    choices = [q for q in data['questions'] if q.get('type') == 'choice']
    choices.sort(key=lambda q: q.get('number', 0))
    data['questions'] = essays + choices

    save_json(json_path, data)
    nums_str = ', '.join(f'Q{q["number"]}' for q in to_insert)
    print(f"  [OK] 插入 {len(to_insert)} 題 ({nums_str}) 到 {json_path}")
    return len(to_insert)


# ===== 缺失題目定義 =====

# 一、整題遺失（5 筆）
MISSING_SINGLE_QUESTIONS = [
    {
        "description": "刑事警察學系/107年/刑案現場處理與刑事鑑識 Q23",
        "json_path": "刑事警察學系/107年/刑案現場處理與刑事鑑識/試題.json",
        "target_num": 23,
        "pdf_pattern": "107*刑案*",
    },
    {
        "description": "刑事警察學系/109年/刑案現場處理與刑事鑑識 Q11",
        "json_path": "刑事警察學系/109年/刑案現場處理與刑事鑑識/試題.json",
        "target_num": 11,
        "pdf_pattern": "109*刑案*",
    },
    {
        "description": "刑事警察學系/113年/刑案現場處理與刑事鑑識 Q6",
        "json_path": "刑事警察學系/113年/刑案現場處理與刑事鑑識/試題.json",
        "target_num": 6,
        "pdf_pattern": "113*刑案*",
    },
    {
        "description": "水上警察學系/109年/水上警察情境實務 Q2",
        "json_path": None,  # 需動態尋找
        "json_subject_pattern": "水上警察情境實務",
        "json_category": "水上警察學系",
        "json_year": "109年",
        "target_num": 2,
        "pdf_pattern": "109*水上*情境*",
    },
    {
        "description": "鑑識科學學系/106年/犯罪偵查 Q47",
        "json_path": "鑑識科學學系/106年/犯罪偵查/試題.json",
        "target_num": 47,
        "pdf_pattern": "106*犯罪偵查*",
    },
]


def find_json_path(category, year, subject_pattern):
    """在考古題庫中找到匹配的試題.json路徑"""
    category_dir = EXAM_DB / category / year
    if not category_dir.exists():
        return None

    for d in category_dir.iterdir():
        if d.is_dir() and subject_pattern in d.name:
            json_path = d / "試題.json"
            if json_path.exists():
                return json_path
    return None


def find_pdf_in_missing(pattern):
    """在 pdfs_missing/ 目錄中找到匹配的 PDF"""
    if not PDFS_MISSING.exists():
        return []

    results = []
    for pdf_file in PDFS_MISSING.rglob("*.pdf"):
        name = pdf_file.stem
        # 簡單的 glob-like 匹配
        parts = pattern.split('*')
        match = True
        remaining = name
        for part in parts:
            if not part:
                continue
            idx = remaining.find(part)
            if idx == -1:
                match = False
                break
            remaining = remaining[idx + len(part):]
        if match:
            results.append(pdf_file)

    return results


def find_all_english_pdfs():
    """在 pdfs_missing/ 中找所有英文科目的 PDF"""
    if not PDFS_MISSING.exists():
        return []

    results = []
    for pdf_file in PDFS_MISSING.rglob("*.pdf"):
        name = pdf_file.name
        if '英文' in name or 'english' in name.lower():
            results.append(pdf_file)

    return results


def find_english_json_targets(year_str, subject_keyword, category_filter=None):
    """
    找到英文共用試題應寫入的所有類科 JSON。

    Args:
        year_str: "109年" 等
        subject_keyword: "中華民國憲法與警察專業英文" 等
        category_filter: 如果指定，只在此類科目錄下搜尋

    Returns:
        list[Path]: JSON 路徑列表
    """
    targets = []
    if not EXAM_DB.exists():
        return targets

    for category_dir in EXAM_DB.iterdir():
        if not category_dir.is_dir():
            continue
        if category_filter and category_filter not in category_dir.name:
            continue
        year_dir = category_dir / year_str
        if not year_dir.exists():
            continue
        for subject_dir in year_dir.iterdir():
            if subject_dir.is_dir() and subject_keyword in subject_dir.name:
                json_path = subject_dir / "試題.json"
                if json_path.exists():
                    targets.append(json_path)

    return targets


def process_single_missing(spec, dry_run=False, backup_dir=None, verbose=False):
    """
    處理一筆整題遺失。

    Returns:
        dict: 處理結果
    """
    desc = spec["description"]
    target_num = spec["target_num"]
    pdf_pattern = spec["pdf_pattern"]

    result = {
        "description": desc,
        "target_num": target_num,
        "status": "pending",
        "message": "",
    }

    # 確定 JSON 路徑
    if spec.get("json_path"):
        json_path = EXAM_DB / spec["json_path"]
    else:
        json_path = find_json_path(
            spec["json_category"],
            spec["json_year"],
            spec["json_subject_pattern"]
        )

    if not json_path or not json_path.exists():
        result["status"] = "error"
        result["message"] = f"找不到目標 JSON"
        print(f"  [ERROR] {desc}: 找不到目標 JSON")
        return result

    result["json_path"] = str(json_path)

    # 先檢查題目是否已存在
    data = load_json(json_path)
    existing_nums = set()
    for q in data.get('questions', []):
        if q.get('type') == 'choice' and isinstance(q.get('number'), int):
            existing_nums.add(q['number'])

    if target_num in existing_nums:
        # 題目已存在，檢查是否有完整選項
        for q in data['questions']:
            if q.get('number') == target_num and q.get('type') == 'choice':
                if q.get('options') and len(q['options']) == 4:
                    result["status"] = "skip"
                    result["message"] = f"Q{target_num} 已存在且有完整選項"
                    print(f"  [SKIP] {desc}: Q{target_num} 已存在且有完整選項")
                    return result
                else:
                    # 選項不完整，需要從 PDF 修復
                    if verbose:
                        print(f"  [INFO] {desc}: Q{target_num} 存在但選項不完整，嘗試修復")
                    break

    # 找 PDF
    pdfs = find_pdf_in_missing(pdf_pattern)
    if not pdfs:
        # 嘗試在 pdfs_missing 子目錄中找
        if PDFS_MISSING.exists():
            all_pdfs = list(PDFS_MISSING.rglob("*.pdf"))
            if verbose:
                print(f"  [INFO] pdfs_missing/ 中共有 {len(all_pdfs)} 個 PDF")
                for p in all_pdfs:
                    print(f"    - {p.name}")

        result["status"] = "no_pdf"
        result["message"] = f"找不到匹配的 PDF（模式: {pdf_pattern}）"
        print(f"  [WARN] {desc}: 找不到 PDF（等待下載完成）")
        return result

    pdf_path = pdfs[0]
    if verbose:
        print(f"  [INFO] 使用 PDF: {pdf_path}")

    # 從 PDF 提取題目
    question = extract_specific_question(pdf_path, target_num)
    if not question:
        # 嘗試解析所有題目看看有什麼
        all_qs = parse_all_questions_from_pdf(pdf_path)
        all_nums = [q['number'] for q in all_qs]
        result["status"] = "not_found"
        result["message"] = f"PDF 中找不到 Q{target_num}（找到: {all_nums}）"
        print(f"  [ERROR] {desc}: PDF 中找不到 Q{target_num}（PDF 題號: {all_nums}）")
        return result

    # 嘗試找答案
    if not question.get('answer'):
        answer = find_answer_for_question(target_num, json_path)
        if answer:
            question['answer'] = answer

    # 插入
    if target_num in existing_nums:
        # 替換有問題的題目
        if not dry_run:
            if backup_dir:
                backup_json(json_path, backup_dir)
            for idx, q in enumerate(data['questions']):
                if q.get('number') == target_num and q.get('type') == 'choice':
                    data['questions'][idx] = question
                    break
            save_json(json_path, data)
            print(f"  [OK] 替換 Q{target_num} 於 {json_path}")
        else:
            print(f"  [DRY-RUN] 會替換 Q{target_num} 於 {json_path}")
        result["status"] = "replaced"
    else:
        success = insert_question_into_json(json_path, question, dry_run, backup_dir)
        result["status"] = "inserted" if success else "error"

    result["message"] = f"Q{target_num} {'已處理' if not dry_run else '待處理'}"
    return result


def process_english_reading(dry_run=False, backup_dir=None, verbose=False):
    """
    處理英文閱讀測驗（~128 題）。

    從 pdfs_missing/ 找到英文 PDF，解析閱讀測驗題目，
    找出 JSON 中缺失的題號並插入。

    Returns:
        list[dict]: 處理結果列表
    """
    results = []

    # 找所有英文 PDF
    eng_pdfs = find_all_english_pdfs()
    if not eng_pdfs:
        print("\n[INFO] 未找到英文閱讀測驗 PDF（等待下載完成）")
        return results

    print(f"\n=== 處理英文閱讀測驗 ===")
    print(f"找到 {len(eng_pdfs)} 個英文 PDF")

    for pdf_path in sorted(eng_pdfs):
        print(f"\n--- 解析: {pdf_path.name} ---")

        name = pdf_path.stem

        # 從父目錄名推斷年份（PDF 存在 pdfs_missing/106年/ 等目錄下）
        parent_name = pdf_path.parent.name
        year_match = re.search(r'(\d{3})年?', parent_name)
        if not year_match:
            # fallback: 從檔名推斷
            year_match = re.search(r'(\d{3})年?', name)
        if not year_match:
            print(f"  [WARN] 無法推斷年份: 目錄={parent_name}, 檔名={name}")
            continue

        year_num = year_match.group(1)
        year_str = f"{year_num}年"

        # 推斷科目關鍵字和目標類科
        subject_keyword = None
        target_categories = None  # None = 自動搜尋全部匹配
        if '矯治組' in name or '法學知識與英文' in name:
            subject_keyword = '英文'
            target_categories = ['犯罪防治學系矯治組']
        elif '水上' in name and '英文' in name:
            subject_keyword = '中華民國憲法與水上警察'
        elif '消防' in name and '英文' in name:
            subject_keyword = '中華民國憲法與消防警察專業英文'
            target_categories = ['消防學系']
        elif '警察專業英文' in name or '憲法與警察' in name:
            subject_keyword = '中華民國憲法與警察專業英文'
        elif '英文' in name:
            subject_keyword = '英文'

        if not subject_keyword:
            print(f"  [WARN] 無法從檔名推斷科目: {name}")
            continue

        print(f"  年份: {year_str}, 科目關鍵字: {subject_keyword}")

        # 解析 PDF
        questions = parse_reading_comprehension(pdf_path)
        if not questions:
            print(f"  [WARN] 未從 PDF 解析出任何題目")
            continue

        print(f"  解析出 {len(questions)} 題")
        passage_qs = [q for q in questions if q.get('passage')]
        print(f"  其中 {len(passage_qs)} 題含 passage")

        # 找所有目標 JSON
        if target_categories:
            target_jsons = []
            for cat in target_categories:
                target_jsons.extend(find_english_json_targets(
                    year_str, subject_keyword, category_filter=cat
                ))
        else:
            target_jsons = find_english_json_targets(year_str, subject_keyword)
        if not target_jsons:
            print(f"  [WARN] 找不到 {year_str} {subject_keyword} 的 JSON")
            continue

        print(f"  將寫入 {len(target_jsons)} 個類科 JSON")

        # 對每個目標 JSON 插入缺失題目
        for json_path in sorted(target_jsons):
            category = json_path.parent.parent.parent.name
            inserted = insert_questions_into_json(
                json_path, questions, dry_run, backup_dir
            )

            results.append({
                "pdf": str(pdf_path),
                "json": str(json_path),
                "category": category,
                "year": year_str,
                "inserted": inserted,
                "total_parsed": len(questions),
            })

    return results


def scan_pdfs_missing_structure(verbose=False):
    """掃描 pdfs_missing/ 目錄結構，列出可用的 PDF"""
    if not PDFS_MISSING.exists():
        print(f"[WARN] pdfs_missing/ 目錄不存在 ({PDFS_MISSING})")
        print("[INFO] 請先執行下載腳本（tools/download_missing_pdfs.py）")
        return []

    pdfs = list(PDFS_MISSING.rglob("*.pdf"))
    if not pdfs:
        print(f"[WARN] pdfs_missing/ 目錄為空")
        return []

    print(f"\npdfs_missing/ 中共有 {len(pdfs)} 個 PDF:")
    for p in sorted(pdfs):
        rel = p.relative_to(PDFS_MISSING)
        size_kb = p.stat().st_size / 1024
        print(f"  {rel} ({size_kb:.1f} KB)")

    return pdfs


def main():
    parser = argparse.ArgumentParser(
        description='解析 pdfs_missing/ 中的 PDF，提取缺失題目寫入 JSON'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='只顯示會做的操作，不實際寫入'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='詳細輸出'
    )
    parser.add_argument(
        '--skip-single', action='store_true',
        help='跳過整題遺失的處理'
    )
    parser.add_argument(
        '--skip-english', action='store_true',
        help='跳過英文閱讀測驗的處理'
    )
    parser.add_argument(
        '--report', action='store_true', default=True,
        help='產生處理報告（預設開啟）'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  缺失題目 PDF 解析器")
    print("=" * 60)

    if args.dry_run:
        print("[MODE] 模擬執行（--dry-run），不會寫入任何檔案")

    # 建立備份目錄
    backup_dir = None
    if not args.dry_run:
        timestamp = datetime.now().strftime('%Y%m%d')
        backup_dir = BACKUPS_DIR / f"parse_missing_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 備份目錄: {backup_dir}")

    # 掃描 PDF 目錄
    available_pdfs = scan_pdfs_missing_structure(args.verbose)

    report = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "pdfs_found": len(available_pdfs),
        "single_questions": [],
        "english_reading": [],
        "summary": {
            "single_processed": 0,
            "single_inserted": 0,
            "single_replaced": 0,
            "single_skipped": 0,
            "single_errors": 0,
            "english_files_updated": 0,
            "english_questions_inserted": 0,
        }
    }

    # ===== 一、整題遺失 =====
    if not args.skip_single:
        print(f"\n{'=' * 60}")
        print("  一、處理整題遺失（5 筆）")
        print(f"{'=' * 60}")

        for spec in MISSING_SINGLE_QUESTIONS:
            print(f"\n--- {spec['description']} ---")
            result = process_single_missing(
                spec, args.dry_run, backup_dir, args.verbose
            )
            report["single_questions"].append(result)
            report["summary"]["single_processed"] += 1

            if result["status"] == "inserted":
                report["summary"]["single_inserted"] += 1
            elif result["status"] == "replaced":
                report["summary"]["single_replaced"] += 1
            elif result["status"] == "skip":
                report["summary"]["single_skipped"] += 1
            elif result["status"] in ("error", "not_found", "no_pdf"):
                report["summary"]["single_errors"] += 1

    # ===== 二、英文閱讀測驗 =====
    if not args.skip_english:
        print(f"\n{'=' * 60}")
        print("  二、處理英文閱讀測驗")
        print(f"{'=' * 60}")

        eng_results = process_english_reading(
            args.dry_run, backup_dir, args.verbose
        )
        report["english_reading"] = eng_results

        for r in eng_results:
            if r["inserted"] > 0:
                report["summary"]["english_files_updated"] += 1
                report["summary"]["english_questions_inserted"] += r["inserted"]

    # ===== 產生報告 =====
    print(f"\n{'=' * 60}")
    print("  處理報告")
    print(f"{'=' * 60}")

    s = report["summary"]
    print(f"\n整題遺失:")
    print(f"  處理: {s['single_processed']}")
    print(f"  插入: {s['single_inserted']}")
    print(f"  替換: {s['single_replaced']}")
    print(f"  跳過: {s['single_skipped']}")
    print(f"  錯誤/未找到: {s['single_errors']}")

    print(f"\n英文閱讀測驗:")
    print(f"  更新檔案數: {s['english_files_updated']}")
    print(f"  插入題數: {s['english_questions_inserted']}")

    # 儲存報告
    if args.report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "parse_missing_report.json"
        save_json(report_path, report)
        print(f"\n[INFO] 報告已儲存: {report_path}")

    print(f"\n{'=' * 60}")
    total = s['single_inserted'] + s['single_replaced'] + s['english_questions_inserted']
    print(f"  總計: 插入/替換 {total} 題")
    print(f"{'=' * 60}")

    return 0 if s['single_errors'] == 0 else 1


if __name__ == "__main__":
    exit(main())
