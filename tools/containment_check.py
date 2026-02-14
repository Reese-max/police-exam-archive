#!/usr/bin/env python3
"""
雙向包含檢查系統 v5
策略：
  - 將 PDF 和 HTML 的文字都拆成有意義的片段（句子/段落）
  - 檢查 PDF 中的每個片段是否能在 HTML 中找到（正規化後）
  - 檢查 HTML 中的每個片段是否能在 PDF 中找到
  - 只報告「內容缺失」或「內容不匹配」的情況
  - 自動過濾考卷標頭、注意事項等結構性差異
"""

import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

BASE_DIR = Path(r"C:\Users\User\Desktop\考古題下載\資管系考古題")
HTML_FILE = BASE_DIR / "資管系考古題總覽.html"

SUBJECT_FOLDERS = {
    "38157": "中華民國憲法與警察專業英文",
    "28884": "國文", "30930": "國文", "11008": "國文",
    "66628": "數位鑑識執法",
    "46543": "警察情境實務", "73897": "警察情境實務",
    "93826": "警察法規", "63567": "警察法規",
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


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r'\s+', '', t)
    repls = {'，': ',', '。': '.', '；': ';', '：': ':', '？': '?', '！': '!',
             '（': '(', '）': ')', '「': '"', '」': '"', '『': "'", '』': "'",
             '—': '-', '─': '-'}
    for k, v in repls.items():
        t = t.replace(k, v)
    return t.lower()


def extract_pdf_text(pdf_path):
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# ============================================================
# 片段提取
# ============================================================

# 要從 PDF 中過濾掉的行（考卷標頭等）
HEADER_PATTERNS = [
    r'^\d{2,3}年(公務|特種)',
    r'^代號[:：]',
    r'^頁次[:：]',
    r'^考試(別|時間)',
    r'^等別[:：]',
    r'^類科',
    r'^科目[:：]',
    r'^座號',
    r'^(全一張|全一頁)',
    r'^(甲|乙)、(申論|測驗)',
    r'^-?\d+-?$',
    r'^\d{5}$',
    r'^請(接背面|以背面)',
    r'^(背面尚有|請翻頁)',
]


def is_header_line(line: str) -> bool:
    line = line.strip()
    for pat in HEADER_PATTERNS:
        if re.match(pat, line):
            return True
    # 考試標頭關鍵字
    if any(kw in line for kw in ['人員考試', '考試別', '退除役軍人轉任', '特種考試交通事業',
                                   '國家安全局', '國家安全情報']):
        if len(line) < 80:
            return True
    return False


def is_instruction_line(line: str) -> bool:
    """判斷是否為考試注意事項"""
    return bool(re.match(r'^※?注意[:：]', line.strip())) or \
           '不必抄題' in line or '不予計分' in line or \
           '禁止使用電子計算器' in line or \
           '本試題為單一選擇題' in line or \
           '鋼筆或原子筆' in line or \
           '2B鉛筆' in line


def extract_meaningful_phrases(text: str, min_len: int = 8) -> list[str]:
    """
    從文字中提取有意義的片段。
    以句號、問號等為分隔，取出每個句子/片段。
    """
    # 先按行拆分，過濾標頭
    lines = text.split('\n')
    content_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if is_header_line(line):
            continue
        if is_instruction_line(line):
            continue
        # 去除行首的五位數代號
        line = re.sub(r'^\d{5}\s*', '', line)
        line = re.sub(r'\s*\d{5}$', '', line)
        if line.strip():
            content_lines.append(line.strip())

    joined = ' '.join(content_lines)

    # 拆成句子（以中文句號、問號、分號為分隔，或以英文句號+空格為分隔）
    sentences = re.split(r'[。？！；\n]|(?<=[a-z])\.\s+(?=[A-Z])', joined)

    phrases = []
    for s in sentences:
        s = s.strip()
        if len(s) >= min_len:
            phrases.append(s)

    return phrases


def extract_html_phrases(soup, card_id: str) -> list[str]:
    """從 HTML 卡片提取所有有意義的文字片段"""
    card = soup.find("div", id=card_id)
    if not card:
        return []

    all_texts = []

    # 選擇題題幹
    for q in card.find_all("div", class_=re.compile(r'mc-question|question')):
        ts = q.find("span", class_="q-text")
        if ts:
            all_texts.append(ts.get_text(strip=True))

    # 選項文字
    for opt in card.find_all("div", class_=re.compile(r'mc-option|option')):
        ts = opt.find("span", class_="opt-text")
        if ts:
            text = ts.get_text(strip=True)
            if len(text) > 5:  # 只保留較長的選項（排除 A/B/C/D 等短選項）
                all_texts.append(text)

    # 申論題
    for essay in card.find_all("div", class_="essay-question"):
        all_texts.append(essay.get_text(strip=True))

    # 考試說明 (exam-note)
    for note in card.find_all("div", class_="exam-note"):
        all_texts.append(note.get_text(strip=True))

    # 閱讀段落
    for p in card.find_all("div", class_="reading-passage"):
        all_texts.append(p.get_text(strip=True))

    # 拆成句子
    phrases = []
    for text in all_texts:
        sents = re.split(r'[。？！；]|(?<=[a-z])\.\s+(?=[A-Z])', text)
        for s in sents:
            s = s.strip()
            if len(s) >= 8:
                phrases.append(s)

    return phrases


def check_containment(source_phrases: list[str], target_text_norm: str,
                      source_name: str, min_match_len: int = 6) -> list[str]:
    """
    檢查 source_phrases 中的每個片段是否能在 target_text_norm 中找到。
    回傳找不到的片段列表。
    """
    missing = []
    for phrase in source_phrases:
        np = norm(phrase)
        if len(np) < min_match_len:
            continue

        # 嘗試在目標中找到此片段（或其大部分）
        found = False

        # 方法 1：完整匹配
        if np in target_text_norm:
            found = True
        else:
            # 方法 2：取片段的中間 70% 來匹配（允許首尾有些差異）
            trim = max(3, len(np) // 5)
            core = np[trim:-trim] if len(np) > trim * 2 + 5 else np
            if len(core) >= 5 and core in target_text_norm:
                found = True
            else:
                # 方法 3：取多個子串來匹配
                chunk_size = min(15, len(np) // 2)
                if chunk_size >= 5:
                    chunks_found = 0
                    total_chunks = 0
                    for i in range(0, len(np) - chunk_size + 1, chunk_size):
                        chunk = np[i:i + chunk_size]
                        total_chunks += 1
                        if chunk in target_text_norm:
                            chunks_found += 1
                    if total_chunks > 0 and chunks_found / total_chunks >= 0.6:
                        found = True

        if not found:
            # 過濾掉明顯的結構性文字
            if any(kw in phrase for kw in ['注意', '不必抄題', '計分', '電子計算器',
                                            '鋼筆', '原子筆', '2B鉛筆', '試卷',
                                            '本試題', '選出一個', '作答者',
                                            '考試別', '等別', '類科', '科目',
                                            '考試時間', '座號', '頁次', '代號',
                                            '請接背面', '背面尚有', '全一頁']):
                continue

            # 過濾掉純選項標號
            if re.match(r'^[\(\)（）ABCD\s]+$', phrase):
                continue

            missing.append(phrase[:80])

    return missing


# ============================================================
# 主程式
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    parser.add_argument("--subject", type=str)
    args = parser.parse_args()

    print("=" * 70)
    print("  雙向包含檢查系統 v5")
    print("=" * 70)
    print()

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    total_issues = 0
    total_pdfs = 0
    clean_count = 0
    report_entries = []

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

        total_pdfs += 1

        try:
            pdf_raw = extract_pdf_text(pdf_path)
        except:
            continue

        # 提取片段
        pdf_phrases = extract_meaningful_phrases(pdf_raw)
        html_phrases = extract_html_phrases(soup, card_id)

        # 正規化全文（用於包含檢查）
        pdf_norm_full = norm(pdf_raw)
        html_norm_full = norm(" ".join(html_phrases))

        issues = []

        # 方向 1：PDF 中的片段是否都在 HTML 中？
        pdf_missing = check_containment(pdf_phrases, html_norm_full, "PDF→HTML")
        for pm in pdf_missing:
            issues.append(f"PDF有/HTML缺: '{pm}'")

        # 方向 2：HTML 中的片段是否都在 PDF 中？
        html_missing = check_containment(html_phrases, pdf_norm_full, "HTML→PDF")
        for hm in html_missing:
            issues.append(f"HTML有/PDF缺: '{hm}'")

        if issues:
            print(f"[{year}年 {name}] ⚠ {len(issues)} 個")
            for iss in issues[:15]:
                print(f"  {iss}")
            if len(issues) > 15:
                print(f"  ... 還有 {len(issues)-15} 個")
            total_issues += len(issues)
            report_entries.append({"year": year, "name": name, "issues": issues})
        else:
            print(f"[{year}年 {name}] ✓")
            clean_count += 1

    print()
    print("=" * 70)
    print(f"  比對 PDF: {total_pdfs}")
    print(f"  通過: {clean_count}")
    print(f"  有差異: {total_pdfs - clean_count}")
    print(f"  差異總數: {total_issues}")
    print("=" * 70)

    # 儲存報告
    rpt = BASE_DIR / "reports" / "containment_report.txt"
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("雙向包含檢查報告\n")
        f.write("=" * 70 + "\n")
        f.write(f"比對: {total_pdfs}, 通過: {clean_count}, 差異: {total_issues}\n\n")
        for e in report_entries:
            f.write(f"\n[{e['year']}年 {e['name']}]\n")
            for i, iss in enumerate(e["issues"], 1):
                f.write(f"  {i}. {iss}\n")
    print(f"\n報告: {rpt}")


if __name__ == "__main__":
    main()
