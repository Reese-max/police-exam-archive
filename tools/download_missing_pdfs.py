# -*- coding: utf-8 -*-
"""
缺失題目 PDF 下載器
自動從考選部網站下載所有缺失題目對應的原始 PDF 試卷。
根據 download_all_categories.py 的下載邏輯改寫。
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

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://wwwq.moex.gov.tw/exam/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive'
}

# 考試名稱篩選關鍵字
EXAM_KEYWORDS = [
    "警察人員考試",
    "警察人員特考",
    "司法人員考試",
    "司法人員特考",
]

# PDF 儲存根目錄
SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdfs_missing")

# ===== 需要下載的缺失題目定義 =====

# 一、整題遺失：需要特定科目的「試題」PDF
MISSING_QUESTIONS = [
    {
        'year': 107,
        'category': '刑事警察學系',
        'subject_keyword': '刑案現場處理與刑事鑑識',
        'missing_q': 'Q23',
        'description': '刑事警察學系/107年/刑案現場處理與刑事鑑識（缺 Q23）',
    },
    {
        'year': 109,
        'category': '刑事警察學系',
        'subject_keyword': '刑案現場處理與刑事鑑識',
        'missing_q': 'Q11',
        'description': '刑事警察學系/109年/刑案現場處理與刑事鑑識（缺 Q11）',
    },
    {
        'year': 113,
        'category': '刑事警察學系',
        'subject_keyword': '刑案現場處理與刑事鑑識',
        'missing_q': 'Q6',
        'description': '刑事警察學系/113年/刑案現場處理與刑事鑑識（缺 Q6）',
    },
    {
        'year': 109,
        'category': '水上警察學系',
        'subject_keyword': '水上警察情境實務',
        'missing_q': 'Q2',
        'description': '水上警察學系/109年/水上警察情境實務（缺 Q2）',
    },
    {
        'year': 106,
        'category': '鑑識科學學系',
        'subject_keyword': '犯罪偵查',
        'missing_q': 'Q47',
        'description': '鑑識科學學系/106年/犯罪偵查（缺 Q47）',
    },
]

# 二、英文閱讀測驗缺失：需要特定的「憲法與英文」科目 PDF
MISSING_ENGLISH = [
    # 全部類科通用的警察專業英文
    {
        'year': 106,
        'subject_keyword': '中華民國憲法與警察專業英文',
        'description': '106年 中華民國憲法與警察專業英文（全類科通用）',
        'exam_keyword': '警察人員',
    },
    {
        'year': 107,
        'subject_keyword': '中華民國憲法與警察專業英文',
        'description': '107年 中華民國憲法與警察專業英文（全類科通用）',
        'exam_keyword': '警察人員',
    },
    # 消防專業英文
    {
        'year': 106,
        'subject_keyword': '中華民國憲法與消防',
        'description': '106年 消防 中華民國憲法與消防警察專業英文',
        'exam_keyword': '警察人員',
    },
    {
        'year': 107,
        'subject_keyword': '中華民國憲法與消防',
        'description': '107年 消防 中華民國憲法與消防警察專業英文',
        'exam_keyword': '警察人員',
    },
    {
        'year': 112,
        'subject_keyword': '中華民國憲法與消防',
        'description': '112年 消防 中華民國憲法與消防警察專業英文',
        'exam_keyword': '警察人員',
    },
    # 水上警察專業英文
    {
        'year': 107,
        'subject_keyword': '中華民國憲法與水上警察',
        'description': '107年 水上警察 中華民國憲法與水上警察專業英文',
        'exam_keyword': '警察人員',
    },
    # 犯罪防治學系矯治組 法學英文（司法特考）
    {
        'year': 106,
        'subject_keyword': '法學知識與英文',
        'description': '犯罪防治學系矯治組 106年 法學英文',
        'exam_keyword': '司法人員',
        'category_hint': '矯治',
    },
    {
        'year': 107,
        'subject_keyword': '法學知識與英文',
        'description': '犯罪防治學系矯治組 107年 法學英文',
        'exam_keyword': '司法人員',
        'category_hint': '矯治',
    },
    {
        'year': 108,
        'subject_keyword': '法學知識與英文',
        'description': '犯罪防治學系矯治組 108年 法學英文',
        'exam_keyword': '司法人員',
        'category_hint': '矯治',
    },
    {
        'year': 109,
        'subject_keyword': '法學知識與英文',
        'description': '犯罪防治學系矯治組 109年 法學英文',
        'exam_keyword': '司法人員',
        'category_hint': '矯治',
    },
    {
        'year': 110,
        'subject_keyword': '法學知識與英文',
        'description': '犯罪防治學系矯治組 110年 法學英文',
        'exam_keyword': '司法人員',
        'category_hint': '矯治',
    },
    {
        'year': 114,
        'subject_keyword': '法學知識與英文',
        'description': '犯罪防治學系矯治組 114年 法學英文',
        'exam_keyword': '司法人員',
        'category_hint': '矯治',
    },
]


def sanitize_filename(name):
    """清理檔名"""
    name = html_module.unescape(name)
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()[:80]


def get_exam_list(session, year, exam_keyword=None):
    """取得指定年份的考試列表"""
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}"
    keywords = exam_keyword if isinstance(exam_keyword, list) else ([exam_keyword] if exam_keyword else EXAM_KEYWORDS)

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
                    if any(kw in name for kw in keywords):
                        exams.append({'code': code, 'name': name, 'year': year})
            return exams
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  取得 {year} 年考試列表失敗: {e}")
                return []
    return []


def get_exam_page_soup(session, year, exam_code):
    """取得考試頁面的 BeautifulSoup 物件"""
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={year + 1911}&e={exam_code}"
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=30, verify=False)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  取得考試頁面失敗: {e}")
                return None
    return None


def find_subject_downloads(soup, subject_keyword):
    """
    在考試頁面中找到符合關鍵字的科目，回傳其下載連結。
    回傳格式: list of {subject_name, type, url}
    """
    results = []
    links = soup.find_all('a', href=re.compile(r'wHandExamQandA_File\.ashx'))

    for link in links:
        if not isinstance(link, Tag):
            continue
        href = str(link.get('href', ''))
        if not href:
            continue

        type_m = re.search(r'[&?]t=([QSMR])', href)
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

        # 檢查科目是否符合關鍵字
        if subject_keyword in subject_name:
            results.append({
                'subject_name': subject_name,
                'type': file_type,
                'url': html_module.unescape(href),
            })

    return results


def identify_category_from_page(soup):
    """從考試頁面中識別出各類科的科目（用於判斷整題遺失的類科歸屬）"""
    from collections import defaultdict

    raw = defaultdict(list)
    links = soup.find_all('a', href=re.compile(r'wHandExamQandA_File\.ashx'))

    for link in links:
        if not isinstance(link, Tag):
            continue
        href = str(link.get('href', ''))
        code_m = re.search(r'[&?]c=(\d+)', href)
        if not code_m:
            continue

        cat_code = code_m.group(1)
        tr = link.find_parent('tr')
        if not tr or not isinstance(tr, Tag):
            continue
        label = tr.find('label', {'class': 'exam-title'}) or tr.find('label')
        if not label or not isinstance(label, Tag):
            continue

        subject_name = label.get_text(strip=True)
        if subject_name and subject_name not in raw[cat_code]:
            raw[cat_code].append(subject_name)

    return raw


def identify_category_name(subjects_list):
    """根據科目清單識別類科名稱"""
    subjects_text = '|||'.join(subjects_list)

    # 司法特考：矯治組/監獄官
    if '監獄學' in subjects_text and '監獄行刑法' in subjects_text:
        if '監獄學概要' not in subjects_text:
            return '犯罪防治學系矯治組'

    # 內軌判定
    is_internal = (
        '中華民國憲法與警察專業英文' in subjects_text or
        '中華民國憲法與消防' in subjects_text or
        '中華民國憲法與水上警察' in subjects_text
    )
    if not is_internal:
        return None

    if '犯罪偵查學' in subjects_text and '刑案現場處理' in subjects_text:
        return '刑事警察學系'
    if '水上警察' in subjects_text and ('海上犯罪偵查' in subjects_text or '水上警察情境' in subjects_text):
        return '水上警察學系'
    if '物理鑑識' in subjects_text or '刑事化學' in subjects_text:
        return '鑑識科學學系'
    if '警察學與警察勤務' in subjects_text:
        return '行政警察學系'
    if '外事警察' in subjects_text:
        return '外事警察學系'
    if '情報學' in subjects_text and '國家安全情報法制' in subjects_text:
        return '公共安全學系社安組'
    if '諮商輔導與婦幼保護' in subjects_text:
        return '犯罪防治學系預防組'
    if '火災學與消防化學' in subjects_text:
        return '消防學系'
    if '交通警察學' in subjects_text:
        return '交通學系交通組'
    if '電腦犯罪偵查' in subjects_text:
        return '資訊管理學系'
    if '移民情勢與政策分析' in subjects_text:
        return '國境警察學系境管組'
    if '法律學系作業' in subjects_text:
        return '法律學系'
    if '警察人事行政與法制' in subjects_text:
        return '行政管理學系'

    return None


def download_pdf(session, url, path):
    """下載單一 PDF 檔案"""
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        return True, os.path.getsize(path), True  # success, size, skipped

    os.makedirs(os.path.dirname(path), exist_ok=True)

    for attempt in range(5):
        try:
            resp = session.get(url, headers=HEADERS, stream=True, timeout=60, verify=False)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', '')
            if 'pdf' not in ct.lower() and 'octet-stream' not in ct.lower():
                return False, f"非 PDF（Content-Type: {ct}）", False

            with open(path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)

            size = os.path.getsize(path)
            if size > 1024:
                return True, size, False
            else:
                os.remove(path)
                return False, "檔案過小（可能非有效 PDF）", False
        except Exception as e:
            if attempt < 4:
                time.sleep(2 ** attempt)
            else:
                return False, str(e)[:80], False
    return False, "重試失敗", False


def download_missing_questions(session, stats):
    """下載整題遺失的科目 PDF"""
    print("\n" + "=" * 70)
    print("【一】下載整題遺失的科目 PDF（5 筆）")
    print("=" * 70)

    # 按年份分組避免重複請求
    years_needed = sorted(set(item['year'] for item in MISSING_QUESTIONS))

    for year in years_needed:
        items_this_year = [item for item in MISSING_QUESTIONS if item['year'] == year]
        print(f"\n--- 民國 {year} 年 ---")

        exams = get_exam_list(session, year)
        if not exams:
            for item in items_this_year:
                print(f"  [失敗] {item['description']}：找不到考試列表")
                stats['failed'].append(item['description'])
            continue

        for exam in exams:
            soup = get_exam_page_soup(session, year, exam['code'])
            if not soup:
                continue

            # 識別各類科
            raw_categories = identify_category_from_page(soup)

            for cat_code, subjects_list in raw_categories.items():
                cat_name = identify_category_name(subjects_list)
                if not cat_name:
                    continue

                for item in items_this_year:
                    if item['category'] != cat_name:
                        continue
                    if item.get('_done'):
                        continue

                    # 尋找符合的科目下載連結
                    downloads = find_subject_downloads(soup, item['subject_keyword'])
                    if not downloads:
                        continue

                    # 只下載「試題」PDF
                    for dl in downloads:
                        if dl['type'] != '試題':
                            continue

                        safe_subject = sanitize_filename(dl['subject_name'])
                        save_path = os.path.join(
                            SAVE_DIR, f"{year}年", f"{safe_subject}_試題.pdf"
                        )
                        pdf_url = urljoin(BASE_URL, dl['url'])

                        ok, result, skipped = download_pdf(session, pdf_url, save_path)
                        if ok:
                            if skipped:
                                print(f"  [跳過] {item['description']}（已存在）")
                                stats['skipped'] += 1
                            else:
                                print(f"  [成功] {item['description']} ({result / 1024:.0f} KB)")
                                stats['success'] += 1
                                stats['total_size'] += result
                            item['_done'] = True
                        else:
                            print(f"  [失敗] {item['description']}：{result}")
                            stats['failed'].append(item['description'])
                            item['_done'] = True

            time.sleep(1.5)

    # 檢查是否有未處理的項目
    for item in MISSING_QUESTIONS:
        if not item.get('_done'):
            print(f"  [未找到] {item['description']}：在考試頁面中找不到對應科目")
            stats['not_found'].append(item['description'])


def download_missing_english(session, stats):
    """下載英文閱讀測驗缺失的科目 PDF"""
    print("\n" + "=" * 70)
    print("【二】下載英文閱讀測驗缺失的科目 PDF")
    print("=" * 70)

    # 按年份和考試關鍵字分組
    years_needed = sorted(set(item['year'] for item in MISSING_ENGLISH))

    for year in years_needed:
        items_this_year = [item for item in MISSING_ENGLISH if item['year'] == year]
        print(f"\n--- 民國 {year} 年 ---")

        # 收集該年份需要的考試關鍵字
        exam_keywords_needed = list(set(item['exam_keyword'] for item in items_this_year))
        exams = get_exam_list(session, year, exam_keywords_needed)

        if not exams:
            for item in items_this_year:
                print(f"  [失敗] {item['description']}：找不到考試列表")
                stats['failed'].append(item['description'])
            continue

        for exam in exams:
            soup = get_exam_page_soup(session, year, exam['code'])
            if not soup:
                continue

            for item in items_this_year:
                if item.get('_done'):
                    continue

                # 確認考試類型匹配
                if item['exam_keyword'] not in exam['name']:
                    continue

                # 如果有類科提示（矯治組），需要確認是監獄官相關考試
                if item.get('category_hint') == '矯治':
                    # 確認頁面中包含監獄官相關科目
                    raw_categories = identify_category_from_page(soup)
                    has_judicial = False
                    for cat_code, subjects_list in raw_categories.items():
                        cat_name = identify_category_name(subjects_list)
                        if cat_name == '犯罪防治學系矯治組':
                            has_judicial = True
                            break
                    if not has_judicial:
                        continue

                # 尋找符合的科目下載連結
                downloads = find_subject_downloads(soup, item['subject_keyword'])
                if not downloads:
                    continue

                # 下載「試題」PDF
                for dl in downloads:
                    if dl['type'] != '試題':
                        continue

                    safe_subject = sanitize_filename(dl['subject_name'])

                    # 英文科目：加上考試名稱前綴避免重名
                    if item.get('category_hint') == '矯治':
                        prefix = "矯治組_"
                    elif '消防' in item['subject_keyword']:
                        prefix = "消防_"
                    elif '水上警察' in item['subject_keyword']:
                        prefix = "水上警察_"
                    else:
                        prefix = ""

                    save_path = os.path.join(
                        SAVE_DIR, f"{year}年", f"{prefix}{safe_subject}_試題.pdf"
                    )
                    pdf_url = urljoin(BASE_URL, dl['url'])

                    ok, result, skipped = download_pdf(session, pdf_url, save_path)
                    if ok:
                        if skipped:
                            print(f"  [跳過] {item['description']}（已存在）")
                            stats['skipped'] += 1
                        else:
                            print(f"  [成功] {item['description']} ({result / 1024:.0f} KB)")
                            stats['success'] += 1
                            stats['total_size'] += result
                        item['_done'] = True
                    else:
                        print(f"  [失敗] {item['description']}：{result}")
                        stats['failed'].append(item['description'])
                        item['_done'] = True
                    break  # 同一科目只下載一份試題

            time.sleep(1.5)

    # 檢查是否有未處理的項目
    for item in MISSING_ENGLISH:
        if not item.get('_done'):
            print(f"  [未找到] {item['description']}：在考試頁面中找不到對應科目")
            stats['not_found'].append(item['description'])


def main():
    print("=" * 70)
    print("  缺失題目 PDF 下載器")
    print(f"  來源: 考選部考畢試題查詢平臺")
    print(f"  儲存目錄: {os.path.abspath(SAVE_DIR)}")
    print(f"  執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    os.makedirs(SAVE_DIR, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    stats = {
        'success': 0,
        'skipped': 0,
        'total_size': 0,
        'failed': [],
        'not_found': [],
    }

    start = datetime.now()

    # 下載整題遺失的科目 PDF
    download_missing_questions(session, stats)

    # 下載英文閱讀測驗缺失的科目 PDF
    download_missing_english(session, stats)

    elapsed = datetime.now() - start
    session.close()

    # 輸出摘要
    print(f"\n{'=' * 70}")
    print("下載摘要")
    print(f"{'=' * 70}")
    print(f"耗時: {elapsed}")
    print(f"新下載: {stats['success']} 個檔案")
    print(f"跳過（已存在）: {stats['skipped']} 個檔案")
    print(f"新下載大小: {stats['total_size'] / (1024 * 1024):.2f} MB")

    if stats['failed']:
        print(f"\n下載失敗（{len(stats['failed'])} 筆）:")
        for item in stats['failed']:
            print(f"  - {item}")

    if stats['not_found']:
        print(f"\n未找到（{len(stats['not_found'])} 筆）:")
        for item in stats['not_found']:
            print(f"  - {item}")

    total = stats['success'] + stats['skipped'] + len(stats['failed']) + len(stats['not_found'])
    ok = stats['success'] + stats['skipped']
    print(f"\n結果: {ok}/{total} 成功")
    print(f"儲存位置: {os.path.abspath(SAVE_DIR)}")

    # 儲存下載報告
    report = {
        'download_time': datetime.now().isoformat(),
        'duration': str(elapsed),
        'stats': {
            'success': stats['success'],
            'skipped': stats['skipped'],
            'total_size_mb': round(stats['total_size'] / (1024 * 1024), 2),
            'failed_count': len(stats['failed']),
            'not_found_count': len(stats['not_found']),
        },
        'failed': stats['failed'],
        'not_found': stats['not_found'],
    }
    report_path = os.path.join(SAVE_DIR, 'download_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"下載報告: {report_path}")


if __name__ == "__main__":
    main()
