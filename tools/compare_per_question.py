#!/usr/bin/env python3
"""
逐題精準比對系統 v3
針對選擇題逐題比對 PDF vs HTML 的文字差異。
只報告 PDF 與 HTML 之間內容不一致的題目。

策略:
  1. 從 PDF 提取全文
  2. 從 HTML 提取每道選擇題的題幹+選項
  3. 在 PDF 全文中定位每道題，取出對應段落
  4. 正規化後比較，報告差異
"""

import re
import sys
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

import pdfplumber
from bs4 import BeautifulSoup

BASE_DIR = Path(r"C:\Users\User\Desktop\考古題下載\資管系考古題")
HTML_FILE = BASE_DIR / "資管系考古題總覽.html"

SUBJECT_FOLDERS = {
    "38157": "中華民國憲法與警察專業英文",
    "28884": "國文",
    "30930": "國文",
    "11008": "國文",
    "66628": "數位鑑識執法",
    "46543": "警察情境實務",
    "73897": "警察情境實務",
    "93826": "警察法規",
    "63567": "警察法規",
    "89699": "警政資訊管理與應用",
    "92248": "電腦犯罪偵查",
}

DISPLAY = {
    "38157": "憲法英文", "28884": "國文", "30930": "國文", "11008": "國文",
    "66628": "數位鑑識", "46543": "情境實務", "73897": "情境實務",
    "93826": "警察法規", "63567": "警察法規", "89699": "資訊管理", "92248": "電腦犯罪",
}


def find_pdf(year, code):
    year_dir = BASE_DIR / f"{year}年"
    if not year_dir.exists():
        return None
    prefix = SUBJECT_FOLDERS.get(code, "")[:3]
    for d in year_dir.iterdir():
        if d.is_dir() and d.name.startswith(prefix):
            p = d / "試題.pdf"
            if p.exists():
                return p
    return None


def extract_pdf_text(path):
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


def norm(text):
    """極度正規化：去空白、轉小寫、統一標點"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r'\s+', '', t)
    t = t.replace('，', ',').replace('。', '.').replace('；', ';')
    t = t.replace('：', ':').replace('？', '?').replace('！', '!')
    t = t.replace('（', '(').replace('）', ')').replace('「', '"').replace('」', '"')
    # 移除 HTML 中的 _____ (填空符號)
    t = re.sub(r'_+', '', t)
    return t.lower()


def extract_html_questions(soup, card_id):
    """從 HTML 提取某個 card 的所有選擇題"""
    card = soup.find("div", id=card_id)
    if not card:
        return []

    questions = []
    for q_div in card.find_all("div", class_=re.compile(r'mc-question|question')):
        q = {}
        # 題號
        num_span = q_div.find("span", class_=re.compile(r'q-num|q-number'))
        if num_span:
            m = re.search(r'(\d+)', num_span.get_text())
            q["num"] = int(m.group(1)) if m else 0
        else:
            q["num"] = 0

        # 題幹
        text_span = q_div.find("span", class_="q-text")
        q["stem"] = text_span.get_text(strip=True) if text_span else ""

        questions.append(q)

    # 也提取選項（它們是獨立的 div）
    all_opts = []
    for opt_div in card.find_all("div", class_=re.compile(r'mc-option|option')):
        label_span = opt_div.find("span", class_="opt-label")
        text_span = opt_div.find("span", class_="opt-text")
        if label_span and text_span:
            label = label_span.get_text(strip=True).replace("(", "").replace(")", "").strip().upper()
            text = text_span.get_text(strip=True)
            all_opts.append({"label": label, "text": text})

    return questions, all_opts


def find_question_in_pdf(pdf_text, q_num, q_stem):
    """在 PDF 全文中定位某道題目"""
    # 用題號定位
    patterns = [
        rf'(?:^|\n)\s*{q_num}\s*[\.、）\)]\s*',
        rf'(?:^|\n)\s*{q_num}\s+',
    ]
    for pat in patterns:
        m = re.search(pat, pdf_text)
        if m:
            # 從匹配位置開始，取到下一個題號
            start = m.end()
            next_q = re.search(rf'(?:^|\n)\s*{q_num + 1}\s*[\.、）\)]', pdf_text[start:])
            if next_q:
                return pdf_text[start:start + next_q.start()].strip()
            else:
                # 取到文末或最多 2000 字元
                return pdf_text[start:start + 2000].strip()
    return None


def compare_stem(pdf_q_text, html_stem, q_num):
    """比對題幹"""
    n_pdf = norm(pdf_q_text)
    n_html = norm(html_stem)

    if not n_html or len(n_html) < 5:
        return []

    # 在 PDF 正規化文字中尋找 HTML 題幹
    # 取 HTML 題幹的前 20 字做定位
    anchor = n_html[:min(20, len(n_html))]
    idx = n_pdf.find(anchor)

    if idx == -1:
        # 嘗試更短的定位
        anchor = n_html[:min(10, len(n_html))]
        idx = n_pdf.find(anchor)

    if idx == -1:
        # 用 SequenceMatcher
        sim = SequenceMatcher(None, n_pdf[:len(n_html)*2], n_html).ratio()
        if sim < 0.5:
            return []  # 完全對不上，跳過
        if sim > 0.95:
            return []  # 足夠相似

        # 找出差異
        issues = []
        matcher = SequenceMatcher(None, n_pdf[:len(n_html)*2], n_html)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                continue
            p_seg = n_pdf[i1:i2]
            h_seg = n_html[j1:j2]
            if len(p_seg) + len(h_seg) < 2:
                continue
            # 過濾常見的結構差異
            if re.match(r'^[\(\)abcd_]+$', p_seg) or re.match(r'^[\(\)abcd_]+$', h_seg):
                continue
            if re.match(r'^\d{5}', p_seg):
                continue
            issues.append({
                "pdf_diff": p_seg[:50],
                "html_diff": h_seg[:50],
                "tag": tag,
            })
        return issues
    else:
        # 找到了定位點，比較對應段落
        pdf_segment = n_pdf[idx:idx + len(n_html) + 20]
        sim = SequenceMatcher(None, pdf_segment[:len(n_html)], n_html).ratio()
        if sim > 0.95:
            return []

        issues = []
        matcher = SequenceMatcher(None, pdf_segment[:len(n_html)+5], n_html)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                continue
            p_seg = pdf_segment[i1:i2]
            h_seg = n_html[j1:j2]
            if len(p_seg) + len(h_seg) < 2:
                continue
            if re.match(r'^[\(\)abcd_]+$', p_seg) or re.match(r'^[\(\)abcd_]+$', h_seg):
                continue
            if re.match(r'^\d{5}', p_seg):
                continue
            issues.append({
                "pdf_diff": p_seg[:50],
                "html_diff": h_seg[:50],
                "tag": tag,
            })
        return issues


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    parser.add_argument("--subject", type=str)
    args = parser.parse_args()

    print("=" * 70)
    print("  逐題精準比對系統 v3")
    print("=" * 70)

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    total_issues = 0
    total_checked = 0

    for card in soup.find_all("div", class_="subject-card"):
        card_id = card.get("id", "")
        m = re.match(r'y(\d+)-(\d+)', card_id)
        if not m:
            continue
        year = int(m.group(1))
        code = m.group(2)

        if args.year and year != args.year:
            continue
        if args.subject and code != args.subject:
            continue

        name = DISPLAY.get(code, code)
        pdf_path = find_pdf(year, code)
        if not pdf_path:
            continue

        # 只檢查有選擇題的科目
        questions, all_opts = extract_html_questions(soup, card_id)
        if not questions:
            continue

        pdf_text = extract_pdf_text(pdf_path)
        if not pdf_text:
            continue

        card_issues = []

        for q in questions:
            q_num = q["num"]
            if q_num == 0:
                continue

            pdf_q = find_question_in_pdf(pdf_text, q_num, q["stem"])
            if not pdf_q:
                continue

            total_checked += 1
            diffs = compare_stem(pdf_q, q["stem"], q_num)

            for d in diffs:
                card_issues.append(
                    f"  Q{q_num}: [{d['tag']}] PDF='{d['pdf_diff']}' HTML='{d['html_diff']}'"
                )

        if card_issues:
            print(f"\n[{year}年 {name}] ⚠ {len(card_issues)} 個差異")
            for ci in card_issues:
                print(ci)
            total_issues += len(card_issues)
        # 不印 ✓ 以減少輸出

    print(f"\n{'=' * 70}")
    print(f"  檢查題目: {total_checked}")
    print(f"  差異總數: {total_issues}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
