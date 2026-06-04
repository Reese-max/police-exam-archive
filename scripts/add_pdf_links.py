#!/usr/bin/env python3
"""為考古題網站的部門頁面加上 PDF 下載連結。

功能：
1. 建立 JSON 目錄名 → PDF 目錄名的對應表
2. 掃描每個部門 HTML 中的 subject-card
3. 從 card 的 year-section 和 h3 標題推斷 PDF 路徑
4. 在 subject-header 後插入 PDF 下載按鈕
5. 可選：將 PDF 複製到考古題網站目錄下（方便 GitHub Pages 部署）

用法:
    python scripts/add_pdf_links.py                    # 只加連結（不複製 PDF）
    python scripts/add_pdf_links.py --copy-pdfs        # 加連結 + 複製 PDF 到網站目錄
    python scripts/add_pdf_links.py --dry-run           # 預覽模式，不修改檔案
"""

import argparse
import glob
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = ROOT / "考古題網站"
DATA_DIR = ROOT / "考古題庫"


# 手動對應表：HTML目錄名 → PDF目錄名（處理三等/四等命名差異）
MANUAL_OVERRIDES = {
    '交通學系交通組': '交通警察交通組',
    '交通學系電訊組': '交通警察電訊組',
    '公共安全學系情報組': '公共情報',
    '公共安全學系社安組': '公共安全',
    '刑事警察學系': '刑事警察',
    '國境警察學系境管組': '國境警察',
    '國境警察學系移民組': '國境警察學系移民組',  # PDF 存在長名目錄
    '外事警察學系': '外事警察',
    '水上警察學系': '水上警察',
    '行政管理學系': '行政管理',
    '行政警察學系': '行政警察',
    '資訊管理學系': '資訊管理',
    '鑑識科學學系': '鑑識科學',
    '犯罪防治學系矯治組': '犯罪防治矯治組',
    '犯罪防治學系預防組': '犯罪防治預防組',
}


def build_dir_mapping() -> dict[str, str]:
    """建立 PDF 目錄名 → JSON 目錄名的對應表。"""
    pdf_dirs = set()
    json_dirs = set()

    for cat in os.listdir(DATA_DIR):
        cat_path = DATA_DIR / cat
        if not cat_path.is_dir() or cat.startswith('.'):
            continue
        has_pdf = False
        has_json = False
        for root, dirs, files in os.walk(cat_path):
            for f in files:
                if f.endswith('.pdf'):
                    has_pdf = True
                if f.endswith('.json'):
                    has_json = True
        if has_pdf:
            pdf_dirs.add(cat)
        if has_json:
            json_dirs.add(cat)

    mapping = {}

    # 先用手動對應（HTML目錄 → PDF目錄）
    # 反轉：PDF目錄 → HTML目錄
    for html_dir, pdf_dir in MANUAL_OVERRIDES.items():
        if pdf_dir in pdf_dirs:
            mapping[pdf_dir] = html_dir

    # 自動匹配：完全匹配
    for pdf_dir in sorted(pdf_dirs):
        if pdf_dir not in mapping:
            if pdf_dir in json_dirs:
                mapping[pdf_dir] = pdf_dir

    return mapping


def _normalize(s: str) -> str:
    """正規化科目名稱：統一括號、去除空白差異。"""
    return s.replace('（', '(').replace('）', ')').replace('　', ' ').strip()


def find_pdf(category_short: str, year: int, subject: str) -> dict[str, Path]:
    """在考古題庫中找對應的 PDF 檔案。

    Returns: {type: path}，type 為 'exam', 'answer', 'correction'
    """
    pdf_dir = DATA_DIR / category_short
    year_dir = pdf_dir / f"{year}年"

    if not year_dir.exists():
        return {}

    result = {}
    norm_subject = _normalize(subject)

    # 找最匹配的科目目錄
    for subj_dir in year_dir.iterdir():
        if not subj_dir.is_dir():
            continue
        norm_dir = _normalize(subj_dir.name)
        # 精確匹配或包含匹配（正規化後）
        if (norm_dir == norm_subject or
                norm_subject.startswith(norm_dir) or
                norm_dir.startswith(norm_subject)):
            for f in subj_dir.iterdir():
                if f.name == '試題.pdf':
                    result['exam'] = f
                elif f.name == '答案.pdf':
                    result['answer'] = f
                elif f.name == '更正答案.pdf':
                    result['correction'] = f
            if result:
                return result

    # 模糊匹配：去掉括號內容後比較
    for subj_dir in year_dir.iterdir():
        if not subj_dir.is_dir():
            continue
        clean_a = re.sub(r'[（(].*?[）)]', '', subject).strip()
        clean_b = re.sub(r'[（(].*?[）)]', '', subj_dir.name).strip()
        if clean_a == clean_b or clean_a.startswith(clean_b) or clean_b.startswith(clean_a):
            for f in subj_dir.iterdir():
                if f.name == '試題.pdf':
                    result['exam'] = f
                elif f.name == '答案.pdf':
                    result['answer'] = f
                elif f.name == '更正答案.pdf':
                    result['correction'] = f
            if result:
                return result

    return {}


def process_html(html_path: Path, dir_map: dict, copy_pdfs: bool = False,
                 dry_run: bool = False) -> tuple[int, int]:
    """處理一個部門 HTML 檔案，加入 PDF 下載連結。

    Returns: (total_cards, cards_with_pdf)
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 從路徑推斷 category：考古題網站/行政警察/行政警察考古題總覽.html
    rel = html_path.relative_to(WEBSITE_DIR)
    page_cat = rel.parts[0]  # e.g., "行政警察"

    # 找對應的 PDF 短名目錄
    pdf_cat = None

    # 先查手動對應表
    if page_cat in MANUAL_OVERRIDES:
        pdf_cat = MANUAL_OVERRIDES[page_cat]
    else:
        for short_name, json_name in dir_map.items():
            if page_cat == short_name or page_cat == json_name:
                pdf_cat = short_name
                break
            if page_cat.startswith(short_name) or short_name.startswith(page_cat):
                pdf_cat = short_name
                break

    if not pdf_cat:
        return 0, 0

    # 解析 HTML：找 year-section 和 subject-card
    # 用正則逐個處理 subject-card
    total_cards = 0
    cards_with_pdf = 0

    def replace_card(match):
        nonlocal total_cards, cards_with_pdf
        card_html = match.group(0)
        total_cards += 1

        # 從 card 的 id 推斷年份：id="y114-15a7b19c"
        id_match = re.search(r'id="y(\d+)-', card_html)
        if not id_match:
            return card_html
        year = int(id_match.group(1))

        # 從 h3 標題推斷科目
        h3_match = re.search(r'<h3[^>]*>(.*?)</h3>', card_html)
        if not h3_match:
            return card_html
        subject = h3_match.group(1).strip()
        # 去掉可能的年份標籤（subject view 中）
        subject = re.sub(r'<span class="sv-year-tag">.*?</span>', '', subject).strip()

        # 找 PDF
        pdfs = find_pdf(pdf_cat, year, subject)
        if not pdfs:
            return card_html

        cards_with_pdf += 1

        # 建立 PDF 下載連結 HTML
        links = []
        website_rel = html_path.parent.relative_to(WEBSITE_DIR)

        if 'exam' in pdfs:
            if copy_pdfs:
                dest = WEBSITE_DIR / "pdfs" / pdf_cat / f"{year}年" / subject / "試題.pdf"
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists():
                        shutil.copy2(pdfs['exam'], dest)
                pdf_url = f"../pdfs/{pdf_cat}/{year}年/{subject}/試題.pdf"
            else:
                # 相對路徑指向考古題庫
                pdf_url = f"../../考古題庫/{pdf_cat}/{year}年/{subject}/試題.pdf"
            links.append(f'<a class="pdf-link" href="{pdf_url}" target="_blank" title="下載原始試題 PDF">📄 試題</a>')

        if 'answer' in pdfs:
            if copy_pdfs:
                dest = WEBSITE_DIR / "pdfs" / pdf_cat / f"{year}年" / subject / "答案.pdf"
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists():
                        shutil.copy2(pdfs['answer'], dest)
                pdf_url = f"../pdfs/{pdf_cat}/{year}年/{subject}/答案.pdf"
            else:
                pdf_url = f"../../考古題庫/{pdf_cat}/{year}年/{subject}/答案.pdf"
            links.append(f'<a class="pdf-link" href="{pdf_url}" target="_blank" title="下載答案 PDF">📝 答案</a>')

        if 'correction' in pdfs:
            if copy_pdfs:
                dest = WEBSITE_DIR / "pdfs" / pdf_cat / f"{year}年" / subject / "更正答案.pdf"
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists():
                        shutil.copy2(pdfs['correction'], dest)
                pdf_url = f"../pdfs/{pdf_cat}/{year}年/{subject}/更正答案.pdf"
            else:
                pdf_url = f"../../考古題庫/{pdf_cat}/{year}年/{subject}/更正答案.pdf"
            links.append(f'<a class="pdf-link" href="{pdf_url}" target="_blank" title="下載更正答案 PDF">✏️ 更正</a>')

        links_html = '<div class="pdf-links">' + ''.join(links) + '</div>'

        # 在 subject-header 後插入
        if '<div class="pdf-links">' not in card_html:
            card_html = card_html.replace(
                '</div>\n<div class="subject-body">',
                '</div>\n' + links_html + '\n<div class="subject-body">',
                1
            )
            # 如果上面沒匹配到，嘗試另一種格式
            if links_html not in card_html:
                card_html = card_html.replace(
                    '</div>\n<div class="subject-body"',
                    '</div>\n' + links_html + '\n<div class="subject-body"',
                    1
                )

        return card_html

    # 用正則找到所有 subject-card 並處理
    new_content = re.sub(
        r'<div class="subject-card"[^>]*>.*?</div>\s*</div>\s*</div>',
        replace_card,
        content,
        flags=re.DOTALL
    )

    if not dry_run and new_content != content:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return total_cards, cards_with_pdf


def add_css(dry_run: bool = False):
    """在 style.css 中加入 PDF 連結的樣式。"""
    css_path = WEBSITE_DIR / "css" / "style.css"
    if not css_path.exists():
        return

    with open(css_path, 'r', encoding='utf-8') as f:
        css = f.read()

    if '.pdf-links' in css:
        return  # 已有樣式

    pdf_css = """
/* === PDF 下載連結 === */
.pdf-links { display: flex; gap: 0.5rem; flex-wrap: wrap; padding: 0.4rem 0 0.6rem; }
.pdf-link { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.25rem 0.6rem; font-size: 0.78rem; color: var(--text-light); background: var(--bg); border: 1px solid var(--border); border-radius: 4px; text-decoration: none; transition: border-color 0.15s, color 0.15s; }
.pdf-link:hover { border-color: var(--accent); color: var(--accent); }
"""

    if not dry_run:
        with open(css_path, 'a', encoding='utf-8') as f:
            f.write(pdf_css)


def main():
    parser = argparse.ArgumentParser(description="為部門頁面加入 PDF 下載連結")
    parser.add_argument("--copy-pdfs", action="store_true", help="複製 PDF 到網站目錄")
    parser.add_argument("--dry-run", action="store_true", help="預覽模式，不修改檔案")
    args = parser.parse_args()

    print("建立目錄對應表...")
    dir_map = build_dir_mapping()
    for short, long in sorted(dir_map.items()):
        print(f"  {short} → {long}")

    print(f"\n掃描 HTML 頁面...")
    html_files = sorted(WEBSITE_DIR.glob("*/*考古題總覽.html"))
    total_cards = 0
    total_with_pdf = 0

    for html_path in html_files:
        cards, with_pdf = process_html(html_path, dir_map, args.copy_pdfs, args.dry_run)
        if with_pdf > 0:
            rel = html_path.relative_to(WEBSITE_DIR)
            print(f"  {rel}: {with_pdf}/{cards} 有 PDF")
        total_cards += cards
        total_with_pdf += with_pdf

    # 加入 CSS 樣式
    add_css(args.dry_run)

    print(f"\n完成：{total_with_pdf}/{total_cards} 個 subject-card 有 PDF 連結")
    if args.dry_run:
        print("(預覽模式，未修改檔案)")


if __name__ == "__main__":
    main()
