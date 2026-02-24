# -*- coding: utf-8 -*-
"""
國境警察學系移民組考畢試題下載器
從考選部考畢試題查詢平臺下載 106-114 年移民行政人員考試 PDF 試題
支援二等、三等（含各語組）、四等

用法:
  python download_immigration.py                    # 下載全部
  python download_immigration.py --years 110-114    # 只下載 110-114 年
  python download_immigration.py --levels 三等 四等  # 只下載三等和四等
  python download_immigration.py --list             # 列出可用考試
"""

import os
import re
import html as html_module
import time
import json
import argparse
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

# 預設年份範圍：民國 106-114 年
DEFAULT_YEARS = list(range(106, 115))

# 考試名稱篩選關鍵字（國境警察學系移民組與司法特考合辦）
EXAM_KEYWORDS = [
    "移民行政人員考試",
    "移民行政人員特考",
    "司法人員考試",       # 國境警察學系移民組常與司法特考合辦
    "司法官考試",
    "警察人員考試",       # 114年起與警察特考合辦
]

# 國境警察學系移民組等別識別
# 二等：有「研究」二字的科目
# 三等：有「外國文」或「移民專業英文」
# 四等：科目名含「概要」

# 三等語組對照
LANGUAGE_GROUPS = {
    '英文': '英文組',
    '日文': '日文組',
    '西班牙文': '西班牙文組',
    '法文': '法文組',
    '韓文': '韓文組',
    '葡萄牙文': '葡萄牙文組',
    '越南文': '越南文組',
    '泰文': '泰文組',
    '印尼文': '印尼文組',
    '德文': '德文組',
    '俄文': '俄文組',
    '阿拉伯文': '阿拉伯文組',
}

# 快取檔案路徑
CACHE_FILE = os.path.join(os.path.dirname(__file__), '.download_cache_immigration.json')


def sanitize_filename(name):
    """清理檔名"""
    name = html_module.unescape(name)
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()[:80]


def load_cache():
    """載入下載快取"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    """儲存下載快取"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  快取儲存失敗: {e}")


def is_cached(cache, url, file_path):
    """檢查是否已下載"""
    key = f"{url}:{file_path}"
    return key in cache and os.path.exists(file_path)


def mark_cached(cache, url, file_path, size):
    """標記為已下載"""
    key = f"{url}:{file_path}"
    cache[key] = {
        'size': size,
        'time': datetime.now().isoformat()
    }


def identify_immigration_level(subjects_text):
    """
    從科目名稱識別國境警察學系移民組等別
    Returns: ('二等', None) / ('三等', '英文組') / ('四等', None) / None
    """
    # 先確認是國境警察學系移民組科目（而非其他考試）
    immigration_keywords = [
        '入出國及移民法規', '移民政策', '移民執法',
        '國土安全', '移民情勢', '移民專業'
    ]
    has_immigration = any(kw in subjects_text for kw in immigration_keywords)
    if not has_immigration:
        return None

    # 二等：科目名含「研究」
    if '行政法研究' in subjects_text or '移民政策分析研究' in subjects_text:
        return ('二等', None)

    # 四等：科目名含「概要」（且有移民相關科目）
    if ('概要' in subjects_text and
        ('入出國及移民法規概要' in subjects_text or
         '移民執法概要' in subjects_text or
         '國土安全概要' in subjects_text)):
        return ('四等', None)

    # 三等：根據外國文科目判斷語組
    for lang_key, group_name in LANGUAGE_GROUPS.items():
        if lang_key in subjects_text and '兼試' in subjects_text:
            return ('三等', group_name)

    # 三等但無法判斷語組（可能是共同科目）
    if ('行政法' in subjects_text and '入出國及移民法規' in subjects_text
            and '概要' not in subjects_text and '研究' not in subjects_text):
        return ('三等', None)

    return None


def get_exam_list(session, year):
    """取得指定年份的考試列表，篩選出移民相關考試"""
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
            return exams
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  取得 {year} 年考試列表失敗: {e}")
                return []
    return []


def parse_exam_page_immigration(session, year, exam_code):
    """
    解析考試頁面，提取國境警察學系移民組相關科目

    Returns:
        dict: {
            ('二等', None): {科目名: {downloads: [...]}},
            ('三等', '英文組'): {科目名: {downloads: [...]}},
            ('四等', None): {科目名: {downloads: [...]}},
        }
    """
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}&e={exam_code}"
    try:
        resp = session.get(url, timeout=30, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"  取得考試頁面失敗: {e}")
        return {}

    soup = BeautifulSoup(resp.text, 'html.parser')

    # 先收集 raw: {cat_code: {subject_name: {downloads: [...]}}}
    raw = defaultdict(lambda: defaultdict(lambda: {'downloads': []}))

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

        raw[cat_code][subject_name]['downloads'].append({
            'type': file_type,
            'url': html_module.unescape(href)
        })

    # 根據科目特徵識別國境警察學系移民組等別
    # 策略：先找出各 cat_code 的等別，再去重合併
    # 對於三等，各語組的共同科目（國文、行政法等）只保留第一次出現的
    # 但各語組獨有的「外國文」科目要保留
    results = {}
    for cat_code, subjects_dict in raw.items():
        subjects_list = list(subjects_dict.keys())
        subjects_text = '|||'.join(subjects_list)

        level_info = identify_immigration_level(subjects_text)
        if not level_info:
            continue

        level, group = level_info

        # 三等各語組合併為一個 key：('三等', None)
        # 共同科目只取一次，外國文科目全部保留
        if level == '三等':
            key = ('三等', None)
        else:
            key = (level, None)

        if key not in results:
            results[key] = {}
        for subj_name, subj_info in subjects_dict.items():
            if subj_name not in results[key]:
                # 新科目，直接加入（取第一次出現的 URL 即可）
                results[key][subj_name] = subj_info
            # 同名科目已存在就跳過（去重，避免重複下載）

    return results


def download_file(session, url, path, cache):
    """下載單一 PDF 檔案（帶快取檢查）"""
    if is_cached(cache, url, path):
        return True, os.path.getsize(path), True

    os.makedirs(os.path.dirname(path), exist_ok=True)

    for attempt in range(5):
        try:
            resp = session.get(url, headers=HEADERS, stream=True, timeout=60, verify=False)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', '')
            if 'pdf' not in ct.lower() and 'octet-stream' not in ct.lower():
                return False, "非PDF", False
            with open(path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            size = os.path.getsize(path)
            if size > 1024:
                mark_cached(cache, url, path, size)
                return True, size, False
            else:
                os.remove(path)
                return False, "檔案過小", False
        except Exception as e:
            if attempt < 4:
                time.sleep(2 ** attempt)
            else:
                return False, str(e)[:50], False
    return False, "重試失敗", False


def main():
    parser = argparse.ArgumentParser(description='國境警察學系移民組考畢試題下載器')
    parser.add_argument('--years', '-y', type=str, default='106-114',
                        help='年份範圍，如: 106-114, 110, 110,112,114')
    parser.add_argument('--levels', '-l', nargs='+',
                        choices=['二等', '三等', '四等', 'all'],
                        default=['all'],
                        help='選擇等別（預設: all）')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='輸出目錄（預設: 國境警察學系移民組PDF/）')
    parser.add_argument('--no-cache', action='store_true',
                        help='不使用快取')
    parser.add_argument('--list', action='store_true',
                        help='僅列出可用的考試（不下載）')
    args = parser.parse_args()

    # 解析年份
    years_str = args.years
    if '-' in years_str and ',' not in years_str:
        parts = years_str.split('-')
        years = list(range(int(parts[0]), int(parts[1]) + 1))
    elif ',' in years_str:
        years = sorted([int(y.strip()) for y in years_str.split(',')])
    else:
        years = [int(years_str)]

    # 解析等別篩選
    if 'all' in args.levels:
        target_levels = None
    else:
        target_levels = set(args.levels)

    # 輸出目錄
    save_dir = args.output or os.path.join(os.path.dirname(__file__), "國境警察學系移民組PDF")
    os.makedirs(save_dir, exist_ok=True)

    # 快取
    cache = {} if args.no_cache else load_cache()

    print("=" * 70)
    print("  國境警察學系移民組考畢試題下載器")
    print(f"  目標年份: 民國 {years[0]}~{years[-1]} 年")
    if target_levels:
        print(f"  目標等別: {', '.join(target_levels)}")
    else:
        print("  目標等別: 全部（二等、三等、四等）")
    print("=" * 70)

    session = requests.Session()
    session.headers.update(HEADERS)

    stats = {
        'success': 0,
        'failed': 0,
        'cached': 0,
        'total_size': 0,
        'levels_found': defaultdict(list),
        'failed_list': [],
    }
    start = datetime.now()

    all_data = {}  # {year: {(level, group): {subj: info}}}

    for year in years:
        print(f"\n{'─' * 70}")
        print(f"掃描民國 {year} 年...")

        exams = get_exam_list(session, year)
        if not exams:
            print(f"  民國 {year} 年沒有找到相關考試")
            continue

        year_data = {}

        for exam in exams:
            print(f"  考試: {exam['name']}")

            # 檢查考試名稱是否真的包含移民
            if '移民' not in exam['name'] and args.list:
                # list 模式也顯示可能的合辦考試
                pass

            immigration_data = parse_exam_page_immigration(
                session, year, exam['code'])

            if not immigration_data:
                continue

            for (level, group), subjects in immigration_data.items():
                # 篩選等別
                if target_levels and level not in target_levels:
                    continue

                key = (level, group)
                group_label = f"{level}"
                stats['levels_found'][group_label].append(year)

                if args.list:
                    print(f"    [{group_label}] {len(subjects)} 個科目:")
                    for subj in sorted(subjects.keys()):
                        print(f"      - {subj}")
                    continue

                # 下載 PDFs
                level_dir_name = f"{level}"
                year_dir = os.path.join(save_dir, f"{year}年", level_dir_name)

                print(f"    [{group_label}] {len(subjects)} 個科目")

                for subj_name, subj_info in subjects.items():
                    safe_name = sanitize_filename(subj_name)
                    subj_dir = os.path.join(year_dir, safe_name)
                    os.makedirs(subj_dir, exist_ok=True)

                    for dl in subj_info['downloads']:
                        fname = f"{dl['type']}.pdf"
                        fpath = os.path.join(subj_dir, fname)
                        pdf_url = urljoin(BASE_URL, dl['url'])

                        ok, result, was_cached = download_file(
                            session, pdf_url, fpath, cache)
                        if ok:
                            if was_cached:
                                stats['cached'] += 1
                            else:
                                stats['success'] += 1
                                stats['total_size'] += result
                                print(f"      ✓ {group_label}/{safe_name}/{fname} "
                                      f"({result / 1024:.0f} KB)")
                        else:
                            stats['failed'] += 1
                            stats['failed_list'].append({
                                'year': year,
                                'level': level,
                                'group': group,
                                'subject': subj_name,
                                'type': dl['type'],
                                'reason': result
                            })
                            print(f"      ✗ {fname}: {result}")
                        time.sleep(0.3)

                # 儲存到 year_data
                if key not in year_data:
                    year_data[key] = {}
                year_data[key].update(subjects)

            time.sleep(1)

        all_data[year] = year_data

    # 儲存快取
    if not args.no_cache:
        save_cache(cache)

    elapsed = datetime.now() - start

    # 輸出報告
    print(f"\n{'=' * 70}")
    if args.list:
        print("掃描完成！")
    else:
        print("下載完成！")
    print(f"{'=' * 70}")
    print(f"耗時: {elapsed}")

    if not args.list:
        print(f"新下載: {stats['success']} 個檔案")
        print(f"快取命中: {stats['cached']} 個檔案")
        print(f"失敗: {stats['failed']} 個檔案")
        print(f"新下載大小: {stats['total_size'] / (1024 * 1024):.2f} MB")

    print(f"\n等別統計:")
    for level_label in sorted(stats['levels_found'].keys()):
        found_years = stats['levels_found'][level_label]
        print(f"  {level_label}: {len(found_years)} 年 "
              f"({min(found_years)}-{max(found_years)})")

    if not args.list:
        print(f"\n儲存位置: {os.path.abspath(save_dir)}")

    if stats['failed_list']:
        log_path = os.path.join(save_dir, '失敗清單.json')
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(stats['failed_list'], f, ensure_ascii=False, indent=2)
        print(f"失敗清單: {log_path}")

    # 儲存下載摘要
    summary = {
        'download_time': datetime.now().isoformat(),
        'duration': str(elapsed),
        'years': years,
        'levels': {
            label: sorted(yrs)
            for label, yrs in stats['levels_found'].items()
        },
        'stats': {
            'success': stats['success'],
            'cached': stats['cached'],
            'failed': stats['failed'],
            'total_size_mb': round(stats['total_size'] / (1024 * 1024), 2)
        }
    }
    summary_path = os.path.join(save_dir, 'download_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"下載摘要: {summary_path}")

    session.close()


if __name__ == "__main__":
    main()
