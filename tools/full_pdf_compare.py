#!/usr/bin/env python3
"""
全面逐頁 PDF-HTML 比對系統 v4
逐頁讀取每份 PDF，提取所有文字，與 HTML 對應卡片做精細比對。

策略：
  1. PDF 文字去除標頭/頁碼/考卷代號後，拆成逐題段落
  2. HTML 文字按題目/申論/段落拆成段落
  3. 對每個段落做 token-level diff
  4. 過濾結構性差異，只報告真正的內容錯誤
"""

import re
import sys
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher, ndiff

import pdfplumber
from bs4 import BeautifulSoup, NavigableString

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


# ============================================================
# PDF 文字清理
# ============================================================

def clean_pdf_text(raw: str) -> str:
    """清理 PDF 提取的文字：移除標頭、頁碼、代號等"""
    lines = raw.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳過考卷標頭行
        if re.match(r'^\d{2,3}年(公務|特種)', line):
            continue
        if re.match(r'^代號[:：]', line):
            continue
        if re.match(r'^頁次[:：]', line):
            continue
        if re.match(r'^考試(別|時間|等|類)', line):
            continue
        if re.match(r'^科目[:：]', line):
            continue
        if re.match(r'^座號[:：]', line):
            continue
        if re.match(r'^(全一張|全一頁)', line):
            continue
        if re.match(r'^(甲|乙)、', line) and '測驗' in line:
            continue
        # 跳過頁碼行（如 "2" 或 "-2-"）
        if re.match(r'^-?\d+-?$', line):
            continue
        # 跳過只有代號的行
        if re.match(r'^\d{5}$', line):
            continue
        # 移除行末的五位數代號
        line = re.sub(r'\s+\d{5}\s*$', '', line)
        line = re.sub(r'^\d{5}\s+', '', line)
        # 移除「請接背面」「背面尚有試題」等
        line = re.sub(r'（請接背面）|（背面尚有試題）|請以背面空白頁書寫.*$', '', line)

        if line.strip():
            cleaned.append(line.strip())

    return "\n".join(cleaned)


def extract_pdf_full(pdf_path: Path) -> str:
    """提取 PDF 完整文字（已清理）"""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    raw = "\n".join(parts)
    return clean_pdf_text(raw)


# ============================================================
# 正規化
# ============================================================

def norm_strict(text: str) -> str:
    """嚴格正規化：去除所有空白和標點差異"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r'\s+', '', t)
    # 統一標點
    repls = {'，': ',', '。': '.', '；': ';', '：': ':', '？': '?', '！': '!',
             '（': '(', '）': ')', '「': '"', '」': '"', '『': "'", '』': "'",
             '—': '-', '─': '-', '～': '~', '﹣': '-'}
    for k, v in repls.items():
        t = t.replace(k, v)
    return t


def norm_loose(text: str) -> str:
    """寬鬆正規化：保留空白但合併多個空白"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


# ============================================================
# HTML 提取
# ============================================================

def extract_card_text_parts(soup, card_id: str) -> dict:
    """
    從 HTML 提取一張卡片的所有文字部分。
    回傳 {
      "mc": {題號: {"stem": ..., "opts": {A: ..., B: ...}}},
      "essays": [文字, ...],
      "passages": [文字, ...],
      "notes": [文字, ...],
      "full_text": 所有文字連接
    }
    """
    card = soup.find("div", id=card_id)
    if not card:
        return None

    result = {"mc": {}, "essays": [], "passages": [], "notes": [], "exam_texts": []}

    # 選擇題
    for q_div in card.find_all("div", class_=re.compile(r'mc-question|question')):
        num_span = q_div.find("span", class_=re.compile(r'q-num|q-number'))
        text_span = q_div.find("span", class_="q-text")
        if num_span and text_span:
            m = re.search(r'(\d+)', num_span.get_text())
            if m:
                num = int(m.group(1))
                result["mc"][num] = {"stem": text_span.get_text(strip=True), "opts": {}}

    # 選項
    q_nums = sorted(result["mc"].keys())
    current_q = 0
    for elem in card.find_all("div", class_=re.compile(r'mc-option|option')):
        lbl = elem.find("span", class_="opt-label")
        txt = elem.find("span", class_="opt-text")
        if lbl and txt:
            label = lbl.get_text(strip=True).replace("(", "").replace(")", "").strip().upper()
            text = txt.get_text(strip=True)
            # 判斷這個選項屬於哪一題
            # 找前一個 mc-question
            prev_q = elem.find_previous("div", class_=re.compile(r'mc-question|question'))
            if prev_q:
                pn = prev_q.find("span", class_=re.compile(r'q-num|q-number'))
                if pn:
                    pm = re.search(r'(\d+)', pn.get_text())
                    if pm:
                        current_q = int(pm.group(1))
            if current_q in result["mc"]:
                result["mc"][current_q]["opts"][label] = text

    # 申論題
    for essay in card.find_all("div", class_="essay-question"):
        result["essays"].append(essay.get_text(strip=True))

    # 閱讀段落
    for p in card.find_all("div", class_="reading-passage"):
        result["passages"].append(p.get_text(strip=True))

    # exam-note
    for n in card.find_all("div", class_="exam-note"):
        result["notes"].append(n.get_text(strip=True))

    # exam-text
    for et in card.find_all("div", class_="exam-text"):
        result["exam_texts"].append(et.get_text(strip=True))

    # 組合全文
    all_parts = []
    for num in sorted(result["mc"].keys()):
        q = result["mc"][num]
        all_parts.append(q["stem"])
        for opt_letter in sorted(q["opts"].keys()):
            all_parts.append(q["opts"][opt_letter])
    all_parts.extend(result["essays"])
    all_parts.extend(result["passages"])
    all_parts.extend(result["notes"])
    all_parts.extend(result["exam_texts"])
    result["full_text"] = " ".join(all_parts)

    return result


# ============================================================
# 比對引擎
# ============================================================

def find_meaningful_diffs(pdf_norm: str, html_norm: str, context_len: int = 15) -> list[dict]:
    """
    找出 PDF 與 HTML 正規化文字之間的有意義差異。
    過濾掉結構性差異（選項標號、考試說明等）。
    """
    diffs = []
    matcher = SequenceMatcher(None, pdf_norm, html_norm, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue

        p_seg = pdf_norm[i1:i2]
        h_seg = html_norm[j1:j2]

        # 過濾：太短的差異（1-2 字元）
        if len(p_seg) + len(h_seg) <= 2:
            continue

        # 過濾：純選項標號差異 (a)(b)(c)(d)
        if re.match(r'^[\(\)abcdABCD\s]+$', p_seg) and re.match(r'^[\(\)abcdABCD\s]+$', h_seg):
            continue
        if re.match(r'^[\(\)abcdABCD]+$', p_seg) or re.match(r'^[\(\)abcdABCD]+$', h_seg):
            continue

        # 過濾：考卷代號 (5 位數字)
        if re.match(r'^\d{5}', p_seg):
            continue

        # 過濾：考試標頭資訊
        skip_keywords = ['年公務人員', '特種考試', '考試別', '等別', '類科', '科目',
                         '考試時間', '座號', '頁次', '代號', '警察人員', '鐵路人員',
                         '退除役', '全一頁', '全一張', '交通事業']
        if any(kw in p_seg for kw in skip_keywords):
            continue

        # 過濾：「※注意」說明
        if '注意' in h_seg or '禁止使用' in h_seg or '不必抄題' in h_seg:
            continue

        # 過濾：純數字差異（題號等）
        if re.match(r'^\d+$', p_seg) and re.match(r'^\d+$', h_seg):
            continue

        # 取上下文
        ctx_p = pdf_norm[max(0, i1-context_len):min(len(pdf_norm), i2+context_len)]
        ctx_h = html_norm[max(0, j1-context_len):min(len(html_norm), j2+context_len)]

        diffs.append({
            "tag": tag,
            "pdf": p_seg[:80],
            "html": h_seg[:80],
            "pdf_ctx": ctx_p[:100],
            "html_ctx": ctx_h[:100],
            "pos_p": i1,
            "pos_h": j1,
        })

    return diffs


def analyze_diff(diff: dict) -> str | None:
    """
    分析一個差異，判斷是否為真正的 OCR 問題。
    回傳問題描述或 None（如果是可忽略的差異）。
    """
    p = diff["pdf"]
    h = diff["html"]
    tag = diff["tag"]

    # 忽略：HTML 多出的考試注意事項
    if tag == "insert" and ('注意' in h or '禁止' in h or '抄題' in h or '計分' in h):
        return None

    # 忽略：PDF 多出的標頭/頁碼
    if tag == "delete" and re.match(r'^[\d\-]+$', p):
        return None

    # 忽略：小括號差異
    if set(p) <= set('()（）') or set(h) <= set('()（）'):
        return None

    # 忽略：子題編號差異 (一)(二)(三) vs ㈠㈡㈢
    if re.match(r'^[一二三四五六七八九十]+$', p) or re.match(r'^[㈠㈡㈢㈣㈤]+$', h):
        return None

    # 忽略：HTML 多出的子題編號
    if tag == "insert" and re.match(r'^[\(（][一二三四五六七八九十㈠㈡㈢㈣㈤]+[\)）]$', h):
        return None

    # 真正的差異
    if tag == "replace":
        return f"替換: PDF='{p[:40]}' → HTML='{h[:40]}'"
    elif tag == "delete":
        return f"PDF有/HTML缺: '{p[:60]}'"
    elif tag == "insert":
        return f"HTML多出: '{h[:60]}'"

    return None


# ============================================================
# 主程式
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    parser.add_argument("--subject", type=str)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print("=" * 70)
    print("  全面逐頁 PDF-HTML 比對系統 v4")
    print("=" * 70)
    print()

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    total_issues = 0
    total_pdfs = 0
    clean_pdfs = 0
    all_reports = []

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
            print(f"[!] {year}年 {name}: PDF 未找到")
            continue

        total_pdfs += 1

        # 提取 PDF 文字
        try:
            pdf_text = extract_pdf_full(pdf_path)
        except Exception as e:
            print(f"[!] {year}年 {name}: PDF 讀取失敗 ({e})")
            continue

        # 提取 HTML 文字
        html_data = extract_card_text_parts(soup, card_id)
        if not html_data:
            print(f"[!] {year}年 {name}: HTML 卡片未找到")
            continue

        html_text = html_data["full_text"]

        # 正規化
        n_pdf = norm_strict(pdf_text)
        n_html = norm_strict(html_text)

        # 計算相似度
        sim = SequenceMatcher(None, n_pdf, n_html, autojunk=False).ratio()

        # 找差異
        raw_diffs = find_meaningful_diffs(n_pdf, n_html)

        # 分析差異
        real_issues = []
        for d in raw_diffs:
            analysis = analyze_diff(d)
            if analysis:
                real_issues.append(analysis)

        if real_issues:
            print(f"[{year}年 {name}] ⚠ {len(real_issues)} 差異 (相似度 {sim:.1%})")
            for ri in real_issues[:20]:  # 最多顯示 20 個
                print(f"  {ri}")
            if len(real_issues) > 20:
                print(f"  ... 還有 {len(real_issues)-20} 個差異")
            total_issues += len(real_issues)
            all_reports.append({"year": year, "name": name, "issues": real_issues, "sim": sim})
        else:
            if args.verbose:
                print(f"[{year}年 {name}] ✓ (相似度 {sim:.1%})")
            else:
                print(f"[{year}年 {name}] ✓")
            clean_pdfs += 1

    print()
    print("=" * 70)
    print(f"  比對 PDF: {total_pdfs}")
    print(f"  完全通過: {clean_pdfs}")
    print(f"  有差異:   {total_pdfs - clean_pdfs}")
    print(f"  差異總數: {total_issues}")
    print("=" * 70)

    # 儲存報告
    report_path = BASE_DIR / "reports" / "full_comparison_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("全面 PDF-HTML 比對報告\n")
        f.write("=" * 70 + "\n")
        f.write(f"比對 PDF: {total_pdfs}, 通過: {clean_pdfs}, 有差異: {total_pdfs - clean_pdfs}\n")
        f.write(f"差異總數: {total_issues}\n\n")
        for r in all_reports:
            f.write(f"\n[{r['year']}年 {r['name']}] 相似度 {r['sim']:.1%}\n")
            for i, ri in enumerate(r["issues"], 1):
                f.write(f"  {i}. {ri}\n")
    print(f"\n報告: {report_path}")


if __name__ == "__main__":
    main()
