# -*- coding: utf-8 -*-
"""
警察資訊管理人員（資管系）考古題專用下載器
目標：近10年（105-114年）三等警察特考 資訊管理人員 所有科目試題
"""

import os
import re
import html as html_module
import time
import json
import requests
import warnings
import urllib3
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://wwwq.moex.gov.tw/exam/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive'
}

# 目標年份範圍：民國 105-114 年（近10年）
TARGET_YEARS = list(range(105, 115))

# 考試名稱篩選關鍵字（涵蓋不同年份的命名差異）
EXAM_KEYWORDS = [
    "警察人員考試",
    "警察人員特考",
    "警察鐵路人員考試",  # 102年合併名稱
]

# 儲存目錄
SAVE_DIR = os.path.join(os.path.dirname(__file__), "資管系考古題")


def sanitize_filename(name):
    """清理檔名"""
    name = html_module.unescape(name)
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()[:80]


def get_exam_list(session, year):
    """取得指定年份的考試列表，篩選出警察相關考試"""
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}"
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=30, verify=False)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            select = soup.find("select", id=re.compile(r'ddlExamCode'))
            if not select:
                return []

            exams = []
            for opt in select.find_all("option"):
                if isinstance(opt, Tag) and opt.has_attr('value') and opt['value']:
                    code = opt['value']
                    name = opt.get_text(strip=True)
                    if any(kw in name for kw in EXAM_KEYWORDS):
                        exams.append({'code': code, 'name': name, 'year': year})
                        print(f"  找到考試: {name}")
            return exams
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  取得 {year} 年考試列表失敗: {e}")
                return []
    return []


def parse_and_filter_資管(session, year, exam_code, exam_name):
    """解析考試頁面，只擷取資訊管理人員的科目"""
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}&e={exam_code}"
    try:
        resp = session.get(url, timeout=30, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"  取得考試頁面失敗: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    raw = defaultdict(lambda: defaultdict(dict))

    links = soup.find_all('a', href=re.compile(r'wHandExamQandA_File\.ashx'))
    for link in links:
        if not isinstance(link, Tag):
            continue
        href = str(link.get('href', ''))
        if not href:
            continue

        code_m = re.search(r'[&?]c=(\d+)', href)
        type_m = re.search(r'[&?]t=([QSMR])', href)
        if not code_m:
            continue

        cat_code = code_m.group(1)
        file_type = {'Q': '試題', 'S': '答案', 'M': '更正答案', 'R': '參考答案'}.get(
            type_m.group(1) if type_m else 'Q', '試題')

        tr = link.find_parent('tr')
        if not tr or not isinstance(tr, Tag):
            continue
        label = tr.find('label', {'class': 'exam-title'}) or tr.find('label')
        if not label or not isinstance(label, Tag):
            continue

        subject_name = label.get_text(strip=True)
        if not subject_name or subject_name in ['試題', '答案', '更正答案', '參考答案']:
            continue

        entry = raw[cat_code][subject_name]
        if 'downloads' not in entry:
            entry['downloads'] = []
        entry['downloads'].append({
            'type': file_type,
            'url': html_module.unescape(href)
        })

    # 從所有類科代碼中找出資訊管理人員
    for cat_code, subjects_dict in raw.items():
        subjects_list = list(subjects_dict.keys())
        subjects_text = '|||'.join(subjects_list)

        # 內軌判定
        is_internal = (
            '中華民國憲法與警察專業英文' in subjects_text or
            '中華民國憲法與消防警察專業英文' in subjects_text or
            '中華民國憲法與水上警察專業英文' in subjects_text
        )
        if not is_internal:
            continue

        # 資管系識別：電腦犯罪偵查 + 數位鑑識執法
        if '電腦犯罪偵查' in subjects_text and '數位鑑識執法' in subjects_text:
            return subjects_dict

    return None


def download_file(session, url, path):
    """下載單一 PDF 檔案"""
    for attempt in range(5):
        try:
            resp = session.get(url, headers=HEADERS, stream=True, timeout=60, verify=False)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', '')
            if 'pdf' not in ct.lower() and 'octet-stream' not in ct.lower():
                return False, "非PDF"
            with open(path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            size = os.path.getsize(path)
            if size > 1024:
                return True, size
            else:
                os.remove(path)
                return False, "檔案過小"
        except Exception as e:
            if attempt < 4:
                time.sleep(2 ** attempt)
            else:
                return False, str(e)[:50]
    return False, "重試失敗"


def main():
    print("=" * 60)
    print("  警察資訊管理人員（資管系）考古題下載器")
    print(f"  目標年份: 民國 {TARGET_YEARS[0]}~{TARGET_YEARS[-1]} 年")
    print("=" * 60)

    os.makedirs(SAVE_DIR, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    stats = {'success': 0, 'failed': 0, 'total_size': 0, 'years_found': [], 'failed_list': []}
    start = datetime.now()

    for year in TARGET_YEARS:
        print(f"\n{'─' * 60}")
        print(f"掃描民國 {year} 年...")

        exams = get_exam_list(session, year)
        if not exams:
            print(f"  民國 {year} 年沒有找到警察相關考試")
            continue

        found = False
        for exam in exams:
            subjects = parse_and_filter_資管(session, year, exam['code'], exam['name'])
            if not subjects:
                continue

            found = True
            stats['years_found'].append(year)
            year_dir = os.path.join(SAVE_DIR, f"{year}年")
            os.makedirs(year_dir, exist_ok=True)

            print(f"  找到資管系 {len(subjects)} 個科目:")
            for subj_name, subj_info in subjects.items():
                safe_name = sanitize_filename(subj_name)
                subj_dir = os.path.join(year_dir, safe_name)
                os.makedirs(subj_dir, exist_ok=True)
                print(f"    {subj_name} ({len(subj_info['downloads'])} 個檔案)")

                for dl in subj_info['downloads']:
                    fname = f"{dl['type']}.pdf"
                    fpath = os.path.join(subj_dir, fname)
                    pdf_url = urljoin(BASE_URL, dl['url'])

                    ok, result = download_file(session, pdf_url, fpath)
                    if ok:
                        stats['success'] += 1
                        stats['total_size'] += result
                        print(f"      下載 {fname} ({result / 1024:.0f} KB)")
                    else:
                        stats['failed'] += 1
                        stats['failed_list'].append({
                            'year': year, 'subject': subj_name,
                            'type': dl['type'], 'reason': result
                        })
                        print(f"      失敗 {fname}: {result}")
                    time.sleep(0.5)

            break  # 同一年只需處理一個考試（通常只有一筆）

        if not found:
            print(f"  民國 {year} 年未找到資管系考試科目")

    elapsed = datetime.now() - start

    # 輸出總結報告
    print(f"\n{'=' * 60}")
    print("下載完成！")
    print(f"{'=' * 60}")
    print(f"耗時: {elapsed}")
    print(f"成功: {stats['success']} 個檔案")
    print(f"失敗: {stats['failed']} 個檔案")
    print(f"大小: {stats['total_size'] / (1024 * 1024):.2f} MB")
    print(f"涵蓋年份: {', '.join(str(y) for y in stats['years_found'])}")
    print(f"儲存位置: {os.path.abspath(SAVE_DIR)}")

    if stats['failed_list']:
        log_path = os.path.join(SAVE_DIR, '失敗清單.json')
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(stats['failed_list'], f, ensure_ascii=False, indent=2)
        print(f"失敗清單: {log_path}")

    session.close()


if __name__ == "__main__":
    main()
