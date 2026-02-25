#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從考選部下載試題答案 PDF，解析後回填到缺答案的 JSON。
同時處理 7 題缺選項的問題（從 PDF 原文手動對應）。

用法:
    python tools/fix_missing_answers.py --dry-run
    python tools/fix_missing_answers.py
"""

import json
import re
import os
import time
import shutil
import requests
import warnings
import urllib3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    print("需要安裝 pdfplumber: pip install pdfplumber")
    raise

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAM_DB = PROJECT_ROOT / "考古題庫"
PDFS_MISSING = PROJECT_ROOT / "pdfs_missing"
BACKUPS_DIR = PROJECT_ROOT / "backups"

BASE_URL = "https://wwwq.moex.gov.tw/exam/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}

# 需要答案的考試列表
# (民國年, 考試代碼列表, 科目關鍵字, 缺失題號)
ANSWER_TARGETS = [
    {
        'year': 106,
        'subject_keyword': '警察專業英文',
        'missing_nums': [59, 60],
        'exam_keywords': ['警察人員'],
    },
    {
        'year': 106,
        'subject_keyword': '消防警察專業英文',
        'missing_nums': [56, 57, 58, 59, 60],
        'exam_keywords': ['警察人員'],
    },
    {
        'year': 107,
        'subject_keyword': '警察專業英文',
        'missing_nums': [56, 57, 58, 59, 60],
        'exam_keywords': ['警察人員'],
    },
    {
        'year': 107,
        'subject_keyword': '消防警察專業英文',
        'missing_nums': [56, 57, 58, 59, 60],
        'exam_keywords': ['警察人員'],
    },
    {
        'year': 107,
        'subject_keyword': '水上警察專業英文',
        'missing_nums': list(range(51, 61)),
        'exam_keywords': ['警察人員'],
    },
    {
        'year': 108,
        'subject_keyword': '法學知識與英文',
        'missing_nums': [49],
        'exam_keywords': ['司法人員'],
        'category_filter': '矯治',
    },
    {
        'year': 110,
        'subject_keyword': '法學知識與英文',
        'missing_nums': [46, 48],
        'exam_keywords': ['司法人員'],
        'category_filter': '矯治',
    },
    {
        'year': 112,
        'subject_keyword': '消防警察專業英文',
        'missing_nums': [60],
        'exam_keywords': ['警察人員'],
    },
]


def download_answer_pdf(session, year, subject_keyword, exam_keywords, save_dir):
    """
    從考選部下載答案 PDF。

    策略：搜尋該年度考試頁面，找到匹配科目的答案下載連結。
    """
    from bs4 import BeautifulSoup, Tag
    import html as html_module

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # 先找考試代碼
    search_url = f"{BASE_URL}wFrmExamQandASearch.aspx"
    try:
        resp = session.get(search_url, timeout=30, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] 無法連線考選部: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')

    # 搜尋考試列表連結
    exam_links = []
    for link in soup.find_all('a', href=True):
        href = str(link.get('href', ''))
        text = link.get_text(strip=True)
        if f'y={year + 1911}' in href or f'y={year+1911}' in href.replace(' ', ''):
            for kw in exam_keywords:
                if kw in text:
                    exam_links.append((text, href))
                    break

    # 也嘗試直接用常見考試代碼
    common_exam_codes = {
        '警察人員': ['001', '101', '003', '103', '080'],
        '司法人員': ['006', '106', '007', '107'],
    }

    for kw in exam_keywords:
        for code in common_exam_codes.get(kw, []):
            exam_url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}&e={code}"
            try:
                resp = session.get(exam_url, timeout=30, verify=False)
                if resp.status_code == 200 and '試題' in resp.text:
                    exam_links.append((f"{kw} (code={code})", exam_url))
            except Exception:
                pass
            time.sleep(0.5)

    if not exam_links:
        print(f"  [WARN] 找不到 {year}年 {exam_keywords} 的考試頁面")
        return None

    # 在考試頁面中找答案 PDF 連結
    for exam_name, exam_href in exam_links:
        if exam_href.startswith('http'):
            page_url = exam_href
        else:
            page_url = f"{BASE_URL}{exam_href}"

        try:
            resp = session.get(page_url, timeout=30, verify=False)
            resp.raise_for_status()
        except Exception:
            continue

        page_soup = BeautifulSoup(resp.text, 'html.parser')

        # 找所有下載連結
        for dl_link in page_soup.find_all('a', href=re.compile(r'wHandExamQandA_File')):
            href = str(dl_link.get('href', ''))
            type_m = re.search(r'[&?]t=([QSMR])', href)
            if not type_m or type_m.group(1) not in ('S', 'M'):
                continue  # 只要答案(S)或更正答案(M)

            # 確認是匹配的科目
            tr = dl_link.find_parent('tr')
            if not tr:
                continue
            label = tr.find('label')
            if not label:
                continue
            subject_text = label.get_text(strip=True)

            if subject_keyword not in subject_text:
                continue

            # 下載答案 PDF
            dl_url = html_module.unescape(href)
            if not dl_url.startswith('http'):
                dl_url = f"{BASE_URL}{dl_url}"

            answer_type = '更正答案' if type_m.group(1) == 'M' else '答案'
            filename = f"{year}年_{subject_text}_{answer_type}.pdf"
            filepath = save_dir / filename

            if filepath.exists() and filepath.stat().st_size > 500:
                print(f"  [SKIP] 已存在: {filename}")
                return filepath

            try:
                resp = session.get(dl_url, timeout=60, verify=False)
                resp.raise_for_status()
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                size_kb = len(resp.content) / 1024
                print(f"  [OK] 下載: {filename} ({size_kb:.0f} KB)")
                return filepath
            except Exception as e:
                print(f"  [ERROR] 下載失敗: {e}")

        time.sleep(1)

    return None


def parse_answer_pdf(pdf_path):
    """
    解析答案 PDF，提取題號→答案的映射。

    考選部答案 PDF 格式為表格：
    題號 | 第1題 | 第2題 | ... | 第10題
    答案 |   B   |   A   | ... |   C
    """
    answers = {}

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            # 方法1：表格格式（考選部標準格式）
            tables = page.extract_tables()
            for table in tables:
                if len(table) < 2:
                    continue
                header = table[0]
                answer_row = table[1]
                if not header or not answer_row:
                    continue

                # 解析「第X題」格式的題號
                for col_idx in range(len(header)):
                    cell = str(header[col_idx] or '').strip()
                    m = re.search(r'第(\d+)題', cell)
                    if not m:
                        continue
                    num = int(m.group(1))
                    if col_idx < len(answer_row):
                        ans = str(answer_row[col_idx] or '').strip()
                        if ans and len(ans) == 1 and ans in 'ABCD':
                            answers[num] = ans
                        elif '送分' in ans or '一律給分' in ans:
                            answers[num] = '送分'

            # 方法2：純文字備援（數字+答案配對）
            text = page.extract_text()
            if text:
                pairs = re.findall(r'第(\d{1,3})題\s+([A-D])\b', text)
                for num_str, ans in pairs:
                    num = int(num_str)
                    if num not in answers and 1 <= num <= 100:
                        answers[num] = ans

                # 方法3：送分標記
                if '送分' in text or '一律給分' in text:
                    give_marks = re.findall(r'第\s*(\d+)\s*題.*?(?:送分|一律給分)', text)
                    for num_str in give_marks:
                        num = int(num_str)
                        if num not in answers:
                            answers[num] = '送分'

    return answers


def update_json_answers(json_path, answers_map, target_nums, dry_run=False):
    """更新 JSON 中缺失的答案"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated = 0
    for q in data.get('questions', []):
        if q.get('type') != 'choice':
            continue
        num = q.get('number')
        if num not in target_nums:
            continue
        if q.get('answer'):
            continue  # 已有答案

        if num in answers_map:
            if dry_run:
                print(f"    [DRY-RUN] Q{num} → {answers_map[num]}")
            else:
                q['answer'] = answers_map[num]
            updated += 1

    if not dry_run and updated > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')

    return updated


# ===== 7 題缺選項的硬編碼修復 =====
# 這些題目的 PDF 格式特殊，自動解析無法分離選項
# 直接從 PDF 原文人工對應

MANUAL_OPTIONS_FIX = [
    # 水上警察學系/107年 Q51-53, Q55（克漏字題，選項在 PDF 同一行）
    {
        'json_glob': '水上警察學系/107年/中華民國憲法與水上警察專業英文/試題.json',
        'fixes': {
            51: {
                'stem': '',
                'options': {'A': 'commuters', 'B': 'terminals', 'C': 'referees', 'D': 'vessels'},
            },
            52: {
                'stem': '',
                'options': {'A': 'free from', 'B': 'irrespective of', 'C': 'in contrast to', 'D': 'by order of'},
            },
            53: {
                'stem': '',
                'options': {'A': 'rituals', 'B': 'episodes', 'C': 'intervals', 'D': 'fragments'},
            },
            55: {
                'stem': '',
                'options': {'A': 'without', 'B': 'through', 'C': 'under', 'D': 'except'},
            },
        }
    },
    # 犯罪防治學系矯治組/108年 Q49（OCR 文字黏合，需手動分離）
    {
        'json_glob': '犯罪防治學系矯治組/108年/法學知識與英文*/試題.json',
        'fixes': {
            49: {
                'stem': 'Which of the following is considered an external environment?',
                'options': {
                    'A': 'An office setting.',
                    'B': 'A meditative activity.',
                    'C': 'A biological timekeeping system.',
                    'D': "A desire to change one's behavior.",
                },
            },
        }
    },
    # 犯罪防治學系矯治組/110年 Q46, Q48（OCR 文字黏合，需手動分離）
    {
        'json_glob': '犯罪防治學系矯治組/110年/法學知識與英文*/試題.json',
        'fixes': {
            46: {
                'stem': 'Which of the following statements is TRUE, according to the text above?',
                'options': {
                    'A': 'At the beginning, there were less than 1,000 colleges with 160,000 students existing in the US.',
                    'B': 'In the 1830s, state colleges and universities were set up to train teachers for the explosive growth of K-12 education.',
                    'C': 'Junior colleges were usually set up by city school systems starting in the 1930s.',
                    'D': 'Community colleges were renamed from junior colleges as low-cost institutions with a strong component of vocational education.',
                },
            },
            48: {
                'stem': 'Which is one of the factors that contributed to the rapid growth of community colleges in the United States?',
                'options': {
                    'A': 'It is a major new trend to include as many rural students as possible.',
                    'B': 'The purpose is to handle the explosive growth of K-12 education.',
                    'C': 'Parents and businessmen wanted nearby, low-cost schools in rural or small-town areas to provide training for the growing white-collar labor force.',
                    'D': 'Many community colleges were located in the center of the fast-growing metropolis to provide more advanced technical jobs in the blue-collar sphere.',
                },
            },
        }
    },
]


def fix_manual_options(dry_run=False):
    """修復 7 題缺選項的問題"""
    print("\n=== 修復缺選項（7 題手動對應）===\n")
    fixed = 0

    for spec in MANUAL_OPTIONS_FIX:
        glob_pattern = spec['json_glob']
        # 在考古題庫中找匹配的 JSON
        parts = glob_pattern.replace('\\', '/').split('/')
        search_dir = EXAM_DB
        for part in parts[:-1]:
            if '*' in part:
                # 模糊匹配目錄
                found = False
                for d in search_dir.iterdir():
                    if d.is_dir() and part.replace('*', '') in d.name:
                        search_dir = d
                        found = True
                        break
                if not found:
                    print(f"  [WARN] 找不到目錄: {part} in {search_dir}")
                    break
            else:
                search_dir = search_dir / part

        json_path = search_dir / parts[-1]
        if not json_path.exists():
            # 嘗試 glob
            matches = list(EXAM_DB.glob(glob_pattern))
            if matches:
                json_path = matches[0]
            else:
                print(f"  [WARN] 找不到: {glob_pattern}")
                continue

        print(f"  {json_path.relative_to(EXAM_DB)}")

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        modified = False
        for q in data.get('questions', []):
            if q.get('type') != 'choice':
                continue
            num = q.get('number')
            if num in spec['fixes']:
                fix = spec['fixes'][num]
                if not q.get('options') or len(q.get('options', {})) < 4:
                    if dry_run:
                        print(f"    [DRY-RUN] Q{num}: 加入選項 {list(fix['options'].keys())}")
                    else:
                        q['options'] = fix['options']
                        if fix.get('stem') and (not q.get('stem') or len(q['stem']) < 5):
                            q['stem'] = fix['stem']
                    modified = True
                    fixed += 1

        if not dry_run and modified:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write('\n')

    print(f"\n  缺選項修復: {fixed} 題")
    return fixed


def main():
    import argparse
    parser = argparse.ArgumentParser(description='下載考選部答案並回填')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    print("=" * 60)
    print("  缺失答案修復器")
    print("=" * 60)

    if args.dry_run:
        print("[MODE] 模擬執行\n")

    # 備份
    backup_dir = None
    if not args.dry_run:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = BACKUPS_DIR / f"fix_answers_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] 備份目錄: {backup_dir}\n")

    # 第一部分：修復 7 題缺選項
    fix_manual_options(args.dry_run)

    # 第二部分：下載答案 PDF 並回填
    print("\n" + "=" * 60)
    print("  下載試題答案")
    print("=" * 60 + "\n")

    answer_dir = PDFS_MISSING / "answers"
    answer_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    all_answers = {}  # {(year, subject_keyword): {num: answer}}

    for target in ANSWER_TARGETS:
        year = target['year']
        subject_kw = target['subject_keyword']
        missing_nums = target['missing_nums']
        exam_kws = target['exam_keywords']

        key = (year, subject_kw)
        if key in all_answers:
            continue

        print(f"\n--- {year}年 {subject_kw} (需 Q{missing_nums}) ---")

        # 下載答案 PDF
        pdf_path = download_answer_pdf(session, year, subject_kw, exam_kws, answer_dir)
        time.sleep(1.5)

        if pdf_path:
            answers = parse_answer_pdf(pdf_path)
            relevant = {n: answers.get(n) for n in missing_nums if n in answers}
            print(f"  解析到 {len(answers)} 個答案, 匹配 {len(relevant)} 個")
            if relevant:
                print(f"  答案: {relevant}")
            all_answers[key] = answers
        else:
            print(f"  [WARN] 未能下載答案 PDF")
            all_answers[key] = {}

    # 回填答案到 JSON
    print("\n" + "=" * 60)
    print("  回填答案到 JSON")
    print("=" * 60 + "\n")

    total_updated = 0
    for target in ANSWER_TARGETS:
        year = target['year']
        subject_kw = target['subject_keyword']
        missing_nums = target['missing_nums']
        cat_filter = target.get('category_filter')

        key = (year, subject_kw)
        answers = all_answers.get(key, {})
        if not answers:
            continue

        year_str = f"{year}年"

        # 找所有匹配的 JSON
        for json_file in sorted(EXAM_DB.rglob("試題.json")):
            if subject_kw not in json_file.parent.name:
                continue
            if json_file.parent.parent.name != year_str:
                continue
            if cat_filter and cat_filter not in str(json_file):
                continue

            rel = json_file.relative_to(EXAM_DB)

            # 備份
            if backup_dir and not args.dry_run:
                bk = backup_dir / rel
                bk.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(json_file, bk)

            updated = update_json_answers(json_file, answers, missing_nums, args.dry_run)
            if updated:
                print(f"  {rel}: {updated} 題答案已回填")
                total_updated += updated

    print(f"\n{'=' * 60}")
    print(f"  總計回填答案: {total_updated} 題")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
