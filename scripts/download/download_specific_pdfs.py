#!/usr/bin/env python3
"""下載特定 PDF 用於補完審計修復 (F3 answer + F5 Q54)"""
import os
import re
import sys
import json
import requests
import warnings
import urllib3
import html as html_module
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
from collections import defaultdict

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://wwwq.moex.gov.tw/exam/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
}
SAVE_DIR = 'downloads_for_fix'


def get_exam_list(session, minguo_year):
    """取得指定年份的考試列表"""
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={minguo_year + 1911}"
    print(f'  請求: {url}')
    resp = session.get(url, timeout=30, verify=False)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    exam_select = soup.find("select", id=re.compile(r'ddlExamCode'))
    if not exam_select:
        print('  找不到考試下拉選單')
        return []
    exams = []
    for option in exam_select.find_all("option"):
        if isinstance(option, Tag) and option.has_attr('value') and option['value']:
            exams.append({
                'code': option['value'],
                'name': option.get_text(strip=True)
            })
    return exams


def get_exam_page(session, minguo_year, exam_code):
    """取得考試頁面 HTML"""
    url = f"{BASE_URL}wFrmExamQandASearch.aspx?y={minguo_year + 1911}&e={exam_code}"
    print(f'  請求考試頁面: {url}')
    resp = session.get(url, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.text


def parse_page_for_downloads(html_content):
    """解析頁面找出所有科目的下載連結

    Returns:
        dict: {category_code: {subject_name: {'downloads': [{'type': '試題'/'答案'/..., 'url': ...}]}}}
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    raw_structure = defaultdict(lambda: defaultdict(lambda: {'downloads': []}))

    links = soup.find_all('a', href=re.compile(r'wHandExamQandA_File\.ashx'))

    for link in links:
        if not isinstance(link, Tag):
            continue
        href = link.get('href', '')
        if not href:
            continue

        href_str = str(href)
        code_match = re.search(r'[&?]c=(\d+)', href_str)
        type_match = re.search(r'[&?]t=([QSMR])', href_str)

        if not code_match:
            continue

        category_code = code_match.group(1)
        file_type_code = type_match.group(1) if type_match else 'Q'
        file_type = {
            'Q': '試題',
            'S': '答案',
            'M': '更正答案',
            'R': '參考答案'
        }.get(file_type_code, '試題')

        # 找科目名稱
        tr = link.find_parent('tr')
        if not tr or not isinstance(tr, Tag):
            continue

        label = tr.find('label', {'class': 'exam-title'})
        if not label:
            label = tr.find('label')
        if not label or not isinstance(label, Tag):
            continue

        subject_name = label.get_text(strip=True)
        if not subject_name or subject_name in ['試題', '答案', '更正答案', '參考答案']:
            continue

        full_url = html_module.unescape(str(href))
        if not full_url.startswith('http'):
            full_url = urljoin(BASE_URL, full_url)

        raw_structure[category_code][subject_name]['downloads'].append({
            'type': file_type,
            'type_code': file_type_code,
            'url': full_url
        })

    return raw_structure


def download_pdf(session, url, filepath):
    """下載 PDF"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not url.startswith('http'):
        url = urljoin(BASE_URL, url)
    print(f'    下載: {url}')
    resp = session.get(url, timeout=60, verify=False, stream=True)
    resp.raise_for_status()
    with open(filepath, 'wb') as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    size = os.path.getsize(filepath)
    print(f'    完成: {filepath} ({size:,} bytes)')
    return size


def download_f3_answer(session):
    """下載 F3: 108年 公共安全/情報 外國文（英文）的答案 PDF"""
    print('\n' + '=' * 60)
    print('F3: 下載 108年外國文（英文）答案')
    print('=' * 60)

    minguo_year = 108
    exams = get_exam_list(session, minguo_year)
    print(f'  {minguo_year}年找到 {len(exams)} 個考試:')
    for e in exams:
        print(f'    [{e["code"]}] {e["name"]}')

    # 找警察人員考試或國家安全情報人員考試
    target_exams = [e for e in exams if '警察' in e['name'] or '情報' in e['name'] or '國家安全' in e['name']]
    print(f'\n  目標考試: {len(target_exams)} 個')

    downloaded = []
    for exam in target_exams:
        print(f'\n  --- 檢查: {exam["name"]} ---')
        html_content = get_exam_page(session, minguo_year, exam['code'])
        structure = parse_page_for_downloads(html_content)

        for cat_code, subjects in structure.items():
            for subj_name, info in subjects.items():
                # 找外國文（英文）
                if '外國文' in subj_name and '英文' in subj_name:
                    print(f'    找到科目: [{cat_code}] {subj_name}')
                    for dl in info['downloads']:
                        print(f'      {dl["type"]}: {dl["url"]}')
                        safe_name = re.sub(r'[\\/*?:"<>|]', '_', subj_name)
                        filename = f'{minguo_year}_{cat_code}_{safe_name}_{dl["type"]}.pdf'
                        filepath = os.path.join(SAVE_DIR, filename)
                        try:
                            download_pdf(session, dl['url'], filepath)
                            downloaded.append({
                                'file': filepath,
                                'type': dl['type'],
                                'subject': subj_name,
                                'cat_code': cat_code,
                                'exam': exam['name']
                            })
                        except Exception as e:
                            print(f'      下載失敗: {e}')

    return downloaded


def download_f5_q54(session):
    """下載 F5: 106年 水上警察 中華民國憲法與水上警察專業英文的試題+答案 PDF"""
    print('\n' + '=' * 60)
    print('F5: 下載 106年水上警察專業英文 試題+答案')
    print('=' * 60)

    minguo_year = 106
    exams = get_exam_list(session, minguo_year)
    print(f'  {minguo_year}年找到 {len(exams)} 個考試:')
    for e in exams:
        print(f'    [{e["code"]}] {e["name"]}')

    target_exams = [e for e in exams if '警察' in e['name']]
    print(f'\n  目標考試: {len(target_exams)} 個')

    downloaded = []
    for exam in target_exams:
        print(f'\n  --- 檢查: {exam["name"]} ---')
        html_content = get_exam_page(session, minguo_year, exam['code'])
        structure = parse_page_for_downloads(html_content)

        for cat_code, subjects in structure.items():
            for subj_name, info in subjects.items():
                # 找水上警察專業英文
                if '水上警察' in subj_name and '英文' in subj_name:
                    print(f'    找到科目: [{cat_code}] {subj_name}')
                    for dl in info['downloads']:
                        print(f'      {dl["type"]}: {dl["url"]}')
                        safe_name = re.sub(r'[\\/*?:"<>|]', '_', subj_name)
                        filename = f'{minguo_year}_{cat_code}_{safe_name}_{dl["type"]}.pdf'
                        filepath = os.path.join(SAVE_DIR, filename)
                        try:
                            download_pdf(session, dl['url'], filepath)
                            downloaded.append({
                                'file': filepath,
                                'type': dl['type'],
                                'subject': subj_name,
                                'cat_code': cat_code,
                                'exam': exam['name']
                            })
                        except Exception as e:
                            print(f'      下載失敗: {e}')

    return downloaded


if __name__ == '__main__':
    os.makedirs(SAVE_DIR, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    print('考選部 PDF 下載工具（補完修復專用）')
    print('目標:')
    print('  F3: 108年 外國文（英文）答案 -> 補 Q1-Q40 answer')
    print('  F5: 106年 水上警察專業英文 試題+答案 -> 補 Q54')

    f3_files = download_f3_answer(session)
    f5_files = download_f5_q54(session)

    print('\n' + '=' * 60)
    print('下載結果摘要')
    print('=' * 60)
    print(f'\nF3 下載 {len(f3_files)} 個檔案:')
    for f in f3_files:
        print(f'  {f["type"]}: {f["file"]}')
    print(f'\nF5 下載 {len(f5_files)} 個檔案:')
    for f in f5_files:
        print(f'  {f["type"]}: {f["file"]}')

    # 儲存下載紀錄
    record = {'f3': f3_files, 'f5': f5_files}
    record_path = os.path.join(SAVE_DIR, 'download_record.json')
    with open(record_path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f'\n下載紀錄已儲存: {record_path}')
