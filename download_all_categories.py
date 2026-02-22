# -*- coding: utf-8 -*-
"""
三等警察特考（內軌）全類科考古題下載器
支援 14 個類科組別（含交通警察交通組/電訊組），年份範圍 105-114 年
基於 download_資管系.py 通用化改寫，複用 考古題下載.py 的 identify_category() 邏輯
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://wwwq.moex.gov.tw/exam/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive'
}

# 預設年份範圍：民國 105-114 年
DEFAULT_YEARS = list(range(105, 115))

# 考試名稱篩選關鍵字
EXAM_KEYWORDS = [
    "警察人員考試",
    "警察人員特考",
    "警察鐵路人員考試",
    "司法人員考試",       # 犯罪防治矯治組（監獄官）
    "司法人員特考",
]

# ===== 15 個類科組別定義 =====
CATEGORIES = {
    '行政警察': {
        'code': 501,
        'short': '行政警察',
        'full': '警察人員考試三等考試_行政警察人員',
        'key_subjects': ['警察學與警察勤務'],
        'description': '警察學與警察勤務、警察政策與犯罪預防',
    },
    '外事警察': {
        'code': 502,
        'short': '外事警察',
        'full': '警察人員考試三等考試_外事警察人員',
        'key_subjects': ['外事警察學'],
        'description': '外事警察學、國際公法',
    },
    '刑事警察': {
        'code': 503,
        'short': '刑事警察',
        'full': '警察人員考試三等考試_刑事警察人員',
        'key_subjects': ['犯罪偵查學', '刑案現場處理'],
        'description': '犯罪偵查學、刑案現場處理',
    },
    '公共安全': {
        'code': 504,
        'short': '公共安全',
        'full': '警察人員考試三等考試_公共安全人員',
        'key_subjects': ['情報學', '國家安全情報法制'],
        'description': '情報學、國家安全情報法制',
    },
    '犯罪防治預防組': {
        'code': 505,
        'short': '犯防預防',
        'full': '警察人員考試三等考試_犯罪防治人員預防組',
        'key_subjects': ['諮商輔導與婦幼保護', '犯罪分析'],
        'description': '諮商輔導與婦幼保護、犯罪分析',
        'exam_type': 'police',
    },
    '犯罪防治矯治組': {
        'code': '505b',
        'short': '犯防矯治',
        'full': '司法人員考試三等考試_監獄官',
        'key_subjects': ['監獄學', '監獄行刑法與羈押法', '刑事政策'],
        'description': '監獄學、監獄行刑法與羈押法、刑事政策、犯罪學與再犯預測',
        'exam_type': 'judicial',
    },
    '消防警察': {
        'code': 506,
        'short': '消防警察',
        'full': '警察人員考試三等考試_消防警察人員',
        'key_subjects': ['火災學與消防化學', '消防安全設備'],
        'description': '火災學與消防化學、消防安全設備',
    },
    '交通警察交通組': {
        'code': 507,
        'short': '交通交通',
        'full': '警察人員考試三等考試_交通警察人員交通組',
        'key_subjects': ['交通警察學', '交通統計與分析'],
        'description': '交通警察學、交通統計與分析',
    },
    '交通警察電訊組': {
        'code': '507b',
        'short': '交通電訊',
        'full': '警察人員考試三等考試_交通警察人員電訊組',
        'key_subjects': ['通訊犯罪偵查', '通訊系統', '電路學'],
        'description': '通訊犯罪偵查、通訊系統、電路學',
    },
    '資訊管理': {
        'code': 508,
        'short': '資訊管理',
        'full': '警察人員考試三等考試_警察資訊管理人員',
        'key_subjects': ['電腦犯罪偵查', '數位鑑識執法'],
        'description': '電腦犯罪偵查、數位鑑識執法',
    },
    '鑑識科學': {
        'code': 509,
        'short': '鑑識科學',
        'full': '警察人員考試三等考試_刑事鑑識人員',
        'key_subjects': ['物理鑑識', '刑事化學', '刑事生物'],
        'description': '物理鑑識、刑事化學、刑事生物',
    },
    '國境警察': {
        'code': 510,
        'short': '國境警察',
        'full': '警察人員考試三等考試_國境警察人員',
        'key_subjects': ['移民情勢與政策分析', '國境執法'],
        'description': '移民情勢與政策分析、國境執法',
    },
    '水上警察': {
        'code': 511,
        'short': '水上警察',
        'full': '警察人員考試三等考試_水上警察人員',
        'key_subjects': ['水上警察學', '海上犯罪偵查法學'],
        'description': '水上警察學、海上犯罪偵查法學',
    },
    '警察法制': {
        'code': 512,
        'short': '警察法制',
        'full': '警察人員考試三等考試_警察法制人員',
        'key_subjects': ['警察法制作業'],
        'description': '警察法制作業、行政法與警察行政違規調查裁處作業',
    },
    '行政管理': {
        'code': 513,
        'short': '行政管理',
        'full': '警察人員考試三等考試_行政管理人員',
        'key_subjects': ['警察人事行政與法制', '警察組織與事務管理'],
        'description': '警察人事行政與法制、警察組織與事務管理',
    },
}

# 快取檔案路徑
CACHE_FILE = os.path.join(os.path.dirname(__file__), '.download_cache_all.json')


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
    if key in cache and os.path.exists(file_path):
        return True
    return False


def mark_cached(cache, url, file_path, size):
    """標記為已下載"""
    key = f"{url}:{file_path}"
    cache[key] = {
        'size': size,
        'time': datetime.now().isoformat()
    }


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
            return exams
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  取得 {year} 年考試列表失敗: {e}")
                return []
    return []


def identify_category_from_subjects(subjects_text):
    """
    根據科目名稱識別類科
    複用 考古題下載.py 的 identify_category() 邏輯
    支援警察特考（內軌）+ 司法特考（監獄官/矯治組）
    """
    # === 司法特考：犯罪防治矯治組（監獄官）===
    if '監獄學' in subjects_text and '監獄行刑法' in subjects_text:
        # 排除四等監所管理員（概要科目）
        if '監獄學概要' not in subjects_text:
            return '犯罪防治矯治組'

    # === 內軌判定：必須有這三種英文科目之一 ===
    is_internal = (
        '中華民國憲法與警察專業英文' in subjects_text or
        '中華民國憲法與消防警察專業英文' in subjects_text or
        '中華民國憲法與水上警察專業英文' in subjects_text
    )
    if not is_internal:
        return None

    # 按特徵科目識別 14 個警察特考類科組別
    if '警察學與警察勤務' in subjects_text:
        return '行政警察'
    if '外事警察學' in subjects_text:
        return '外事警察'
    if '犯罪偵查學' in subjects_text and '刑案現場處理' in subjects_text:
        return '刑事警察'
    if '情報學' in subjects_text and '國家安全情報法制' in subjects_text:
        return '公共安全'
    if '諮商輔導與婦幼保護' in subjects_text and '犯罪分析' in subjects_text:
        return '犯罪防治預防組'
    if '火災學與消防化學' in subjects_text and '消防安全設備' in subjects_text:
        return '消防警察'
    # 交通警察：電訊組必須在交通組之前判斷（電訊組科目更獨特）
    if '通訊犯罪偵查' in subjects_text and '通訊系統' in subjects_text and '電路學' in subjects_text:
        return '交通警察電訊組'
    if '交通警察學' in subjects_text and '交通統計與分析' in subjects_text:
        return '交通警察交通組'
    if '電腦犯罪偵查' in subjects_text and '數位鑑識執法' in subjects_text:
        return '資訊管理'
    if '物理鑑識' in subjects_text and '刑事化學' in subjects_text and '刑事生物' in subjects_text:
        return '鑑識科學'
    if '移民情勢與政策分析' in subjects_text and '國境執法' in subjects_text:
        return '國境警察'
    if '水上警察學' in subjects_text and '海上犯罪偵查法學' in subjects_text:
        return '水上警察'
    if '警察法制作業' in subjects_text:
        return '警察法制'
    if '警察人事行政與法制' in subjects_text and '警察組織與事務管理' in subjects_text:
        return '行政管理'

    return None


def parse_exam_page(session, year, exam_code, target_categories=None):
    """
    解析考試頁面，識別並提取指定類科的科目
    Args:
        session: requests session
        year: 民國年份
        exam_code: 考試代碼
        target_categories: 目標類科列表，None 表示全部
    Returns:
        dict: {類科名稱: {科目名稱: {downloads: [...]}}}
    """
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}&e={exam_code}"
    try:
        resp = session.get(url, timeout=30, verify=False)
        resp.raise_for_status()
    except Exception as e:
        print(f"  取得考試頁面失敗: {e}")
        return {}

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

    # 根據科目特徵識別類科
    results = {}
    for cat_code, subjects_dict in raw.items():
        subjects_list = list(subjects_dict.keys())
        subjects_text = '|||'.join(subjects_list)

        category_name = identify_category_from_subjects(subjects_text)
        if not category_name:
            continue

        # 如果有指定目標類科，只保留目標
        if target_categories and category_name not in target_categories:
            continue

        results[category_name] = subjects_dict

    return results


def download_file(session, url, path, cache):
    """下載單一 PDF 檔案（帶快取檢查）"""
    if is_cached(cache, url, path):
        return True, os.path.getsize(path), True  # success, size, cached

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


def print_banner(target_categories, years):
    """顯示標題"""
    print("=" * 70)
    print("  三等警察特考（內軌）全類科考古題下載器")
    print(f"  目標年份: 民國 {years[0]}~{years[-1]} 年")
    if target_categories:
        print(f"  目標類科: {', '.join(target_categories)}")
    else:
        print(f"  目標類科: 全部 {len(CATEGORIES)} 個類科")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='三等警察特考全類科考古題下載器')
    parser.add_argument('--categories', '-c', nargs='+',
                        choices=list(CATEGORIES.keys()) + ['all'],
                        default=['all'],
                        help='選擇類科（預設: all）')
    parser.add_argument('--years', '-y', type=str, default='105-114',
                        help='年份範圍，如: 105-114, 110, 110,112,114')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='輸出目錄（預設: 考古題庫/）')
    parser.add_argument('--workers', '-w', type=int, default=3,
                        help='併發下載數（預設: 3）')
    parser.add_argument('--no-cache', action='store_true',
                        help='不使用快取')
    parser.add_argument('--list', action='store_true',
                        help='僅列出可用的類科')
    args = parser.parse_args()

    # 列出類科
    if args.list:
        print("\n可用的三等內軌類科:")
        print("-" * 60)
        for name, info in CATEGORIES.items():
            print(f"  {info['code']} {name:8s} | {info['description']}")
        print()
        return

    # 解析年份
    years_str = args.years
    if '-' in years_str and ',' not in years_str:
        parts = years_str.split('-')
        years = list(range(int(parts[0]), int(parts[1]) + 1))
    elif ',' in years_str:
        years = sorted([int(y.strip()) for y in years_str.split(',')])
    else:
        years = [int(years_str)]

    # 解析類科
    if 'all' in args.categories:
        target_categories = None  # None = 全部
        target_list = list(CATEGORIES.keys())
    else:
        target_categories = args.categories
        target_list = args.categories

    # 輸出目錄
    save_dir = args.output or os.path.join(os.path.dirname(__file__), "考古題庫")
    os.makedirs(save_dir, exist_ok=True)

    # 快取
    cache = {} if args.no_cache else load_cache()

    print_banner(target_categories, years)

    session = requests.Session()
    session.headers.update(HEADERS)

    stats = {
        'success': 0,
        'failed': 0,
        'cached': 0,
        'total_size': 0,
        'categories_found': defaultdict(list),  # {類科: [年份]}
        'failed_list': [],
    }
    start = datetime.now()

    # 逐年掃描
    for year in years:
        print(f"\n{'─' * 70}")
        print(f"掃描民國 {year} 年...")

        exams = get_exam_list(session, year)
        if not exams:
            print(f"  民國 {year} 年沒有找到警察相關考試")
            continue

        for exam in exams:
            print(f"  考試: {exam['name']}")
            categories_data = parse_exam_page(
                session, year, exam['code'], target_categories)

            if not categories_data:
                continue

            for cat_name, subjects in categories_data.items():
                stats['categories_found'][cat_name].append(year)
                cat_dir = os.path.join(save_dir, cat_name, f"{year}年")

                print(f"    [{cat_name}] {len(subjects)} 個科目")

                for subj_name, subj_info in subjects.items():
                    safe_name = sanitize_filename(subj_name)
                    subj_dir = os.path.join(cat_dir, safe_name)
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
                                print(f"      下載 {cat_name}/{year}年/{safe_name}/{fname} "
                                      f"({result / 1024:.0f} KB)")
                        else:
                            stats['failed'] += 1
                            stats['failed_list'].append({
                                'year': year,
                                'category': cat_name,
                                'subject': subj_name,
                                'type': dl['type'],
                                'reason': result
                            })
                            print(f"      失敗 {fname}: {result}")
                        time.sleep(0.3)

            # 不要 break，同一年可能有多個考試（警察特考 + 司法特考）
            time.sleep(1)  # 考試之間暫停避免被封鎖

    # 儲存快取
    if not args.no_cache:
        save_cache(cache)

    elapsed = datetime.now() - start

    # 輸出報告
    print(f"\n{'=' * 70}")
    print("下載完成！")
    print(f"{'=' * 70}")
    print(f"耗時: {elapsed}")
    print(f"新下載: {stats['success']} 個檔案")
    print(f"快取命中: {stats['cached']} 個檔案")
    print(f"失敗: {stats['failed']} 個檔案")
    print(f"新下載大小: {stats['total_size'] / (1024 * 1024):.2f} MB")
    print(f"\n類科統計:")
    for cat_name in target_list:
        found_years = stats['categories_found'].get(cat_name, [])
        if found_years:
            print(f"  {cat_name}: {len(found_years)} 年 ({min(found_years)}-{max(found_years)})")
        else:
            print(f"  {cat_name}: 未找到")
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
        'categories': {
            cat: sorted(yrs) for cat, yrs in stats['categories_found'].items()
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
