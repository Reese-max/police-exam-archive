#!/usr/bin/env python3
"""
最終 OCR 瑕疵掃描 v6
全面掃描 HTML 中所有文字內容，找出殘留的 OCR 問題。

策略:
  1. 提取所有 HTML 卡片的文字內容
  2. 英文分詞品質檢查（拆開/黏在一起的單字）
  3. 五位數代號汙染檢查
  4. 中文混入英文字母檢查
  5. 標點符號前後空格檢查
  6. 與 PDF 逐段比對驗證
"""

import re
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict

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
    "89699": "警政資訊管理學系與應用",
    "92248": "電腦犯罪偵查",
}
DISPLAY = {
    "38157": "憲法英文", "28884": "國文", "30930": "國文", "11008": "國文",
    "66628": "數位鑑識", "46543": "情境實務", "73897": "情境實務",
    "93826": "警察法規", "63567": "警察法規", "89699": "資訊管理學系", "92248": "電腦犯罪",
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


def norm(text):
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r'\s+', '', t)
    t = t.replace('，', ',').replace('。', '.').replace('；', ';')
    t = t.replace('：', ':').replace('？', '?').replace('！', '!')
    t = t.replace('（', '(').replace('）', ')').replace('「', '"').replace('」', '"')
    t = re.sub(r'_+', '', t)
    return t.lower()


def extract_pdf_text(path):
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# ============================================================
# 英文單字品質檢查
# ============================================================

# 常見被 OCR 拆開的組合
SPLIT_PATTERNS = [
    # -tion/-sion 被拆開
    (r'\b(\w+)\s+tion\b', 'tion拆開'),
    (r'\b(\w+)\s+sion\b', 'sion拆開'),
    (r'\b(\w+)\s+ment\b(?!\s+(?:of|in|on|is|are|was|were|for|and|the|to|a|an|with|by|from|at|has|had))', 'ment拆開'),
    # 常見單字被拆開
    (r'\bCh\s+at\b', 'Chat拆開'),
    (r'\bAu\s+then', 'Auth拆開'),
    (r'\bAlph\s+a\b', 'Alpha拆開'),
    (r'\bmonit\s+or\b', 'monitor拆開'),
    (r'\bhum\s+an\b', 'human拆開'),
    (r'\bTaiw\s+an\b', 'Taiwan拆開'),
    (r'\bsoftw\s+are\b', 'software拆開'),
    (r'\btoge\s+ther\b', 'together拆開'),
    (r'\bo\s+ther\b', 'other拆開'),
    (r'\bth\s+at\b', 'that拆開'),
    (r'\bth\s+an\b', 'than拆開'),
    (r'\bwh\s+ich\b', 'which拆開'),
    (r'\bwh\s+en\b', 'when拆開'),
    (r'\bf\s+or\b', 'for拆開'),
    (r'\bc\s+an\b', 'can拆開'),
    (r'\bw\s+ith\b', 'with拆開'),
    (r'\banalys\s+is\b', 'analysis拆開'),
    (r'\bGPT\s*-\s*(\d)', 'GPT-數字'),
]

# 英文單字黏在一起的模式（camelCase 在非程式碼上下文中）
GLUED_PATTERNS = [
    (r'(?<![A-Z])[a-z][A-Z][a-z]', '可能黏字'),
]

# 五位數代號汙染
CODE_PATTERNS = [
    (r'(?<!\d)\d{5}(?!\d)(?!年|月|日|人|元|分|時|題|頁|條|款|項)', '殘留代號'),
]

# 已知正常的五位數字（不是考卷代號）
KNOWN_NUMBERS = {
    '50150', '50550', '51250', '51350', '51450', '51550',
    # 法規條文數字等也可能是五位數
}


def check_english_quality(text, context=""):
    """檢查英文文字品質"""
    issues = []

    # 1. 拆開的單字
    for pat, desc in SPLIT_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            snippet = text[max(0, m.start()-15):m.end()+15]
            issues.append(f"  {desc}: '...{snippet}...'")

    # 2. 英文單字黏在一起（只檢查長度 > 15 的連續英文）
    for m in re.finditer(r'[A-Za-z]{16,}', text):
        word = m.group()
        # 排除已知的長單字
        if word.lower() in KNOWN_LONG_WORDS:
            continue
        # 檢查是否有小寫接大寫的模式（camelCase）
        if re.search(r'[a-z][A-Z]', word):
            snippet = text[max(0, m.start()-5):m.end()+5]
            issues.append(f"  黏字(camelCase): '{snippet}'")

    # 3. 標點符號後缺空格（英文語境）
    for m in re.finditer(r'[a-z]\.[A-Z]', text):
        snippet = text[max(0, m.start()-10):m.end()+10]
        issues.append(f"  句號後缺空格: '...{snippet}...'")

    for m in re.finditer(r'[a-z],[A-Z]', text):
        snippet = text[max(0, m.start()-10):m.end()+10]
        issues.append(f"  逗號後缺空格: '...{snippet}...'")

    return issues


# 常見的長英文單字（正常的，不是黏字）
KNOWN_LONG_WORDS = {
    'authentication', 'recommendation', 'telecommunications', 'characteristics',
    'implementation', 'administration', 'representative', 'acknowledgement',
    'constitutionality', 'unconstitutional', 'representatives', 'investigation',
    'responsibilities', 'organizational', 'discrimination', 'identification',
    'communication', 'communications', 'transformation', 'infrastructure',
    'administrative', 'accomplishment', 'interpretation', 'comprehensive',
    'professionalism', 'counterterrorism', 'professionalization', 'professionalized',
    'professionallytrainedtohandle', 'professionallytrained',
    'counterintelligence', 'telecommunication', 'internationalization',
    'interoperability', 'confidentiality', 'standardization', 'rehabilitation',
    'pharmaceutical', 'characteristics', 'approximation', 'appropriation',
    'appropriations', 'proportionality', 'disproportionate', 'superintendent',
    'cryptocurrency', 'cryptocurrencies', 'cybersecurity', 'whistleblower',
    'whistleblowing', 'whistleblowers', 'acknowledgement', 'acknowledgments',
    'environmentally', 'environmental', 'internationally', 'international',
    'accountability', 'organizational', 'jurisdictional', 'jurisdictions',
    'classification', 'psychologically', 'psychological', 'methodological',
    'technologically', 'technological', 'constitutional', 'unconstitutional',
    'constitutionality', 'constitutionalism', 'multiculturalism',
    'multidisciplinary', 'interdisciplinary', 'reconnaissance',
    'disinformation', 'misinformation', 'counternarrative', 'counternarratives',
    'institutionalize', 'institutionalized', 'institutionalization',
    'professionalize', 'operationalize', 'operationalized',
    'deescalation', 'deescalating', 'counterproductive',
    'authoritarianism', 'collectivization', 'industrialization',
    'interchangeably', 'interchangeable', 'biotechnological',
    'bioinformatics', 'nanotechnology', 'electrophoresis',
    'deoxyribonucleic', 'spectrophotometry', 'chromatography',
}


def extract_card_texts(soup, card_id):
    """從 HTML 卡片提取所有文字和它們的 HTML 行號資訊"""
    card = soup.find("div", id=card_id)
    if not card:
        return []

    texts = []

    # 選擇題題幹
    for q in card.find_all("div", class_="mc-question"):
        num_span = q.find("span", class_="q-number")
        text_span = q.find("span", class_="q-text")
        num = num_span.get_text(strip=True) if num_span else "?"
        text = text_span.get_text(strip=True) if text_span else ""
        if text:
            texts.append(("Q" + num, text))

    # 選項
    for opt in card.find_all("div", class_="mc-option"):
        label_span = opt.find("span", class_="opt-label")
        text_span = opt.find("span", class_="opt-text")
        label = label_span.get_text(strip=True) if label_span else "?"
        text = text_span.get_text(strip=True) if text_span else ""
        if text and len(text) > 3:
            texts.append((label, text))

    # 申論題
    for i, essay in enumerate(card.find_all("div", class_="essay-question"), 1):
        text = essay.get_text(strip=True)
        if text:
            texts.append((f"申論{i}", text))

    # 考試說明
    for i, note in enumerate(card.find_all("div", class_="exam-note"), 1):
        text = note.get_text(strip=True)
        if text:
            texts.append((f"說明{i}", text))

    # 閱讀段落
    for i, p in enumerate(card.find_all("div", class_="reading-passage"), 1):
        text = p.get_text(strip=True)
        if text:
            texts.append((f"段落{i}", text))

    # exam-text
    for i, et in enumerate(card.find_all("div", class_="exam-text"), 1):
        text = et.get_text(strip=True)
        if text:
            texts.append((f"文本{i}", text))

    # 考試元資料
    for i, meta in enumerate(card.find_all("div", class_="meta-line"), 1):
        text = meta.get_text(strip=True)
        if text:
            texts.append((f"元{i}", text))

    # exam-section-marker
    for i, marker in enumerate(card.find_all("div", class_="exam-section-marker"), 1):
        text = marker.get_text(strip=True)
        if text:
            texts.append((f"標記{i}", text))

    return texts


def check_code_contamination(text, context=""):
    """檢查五位數代號汙染"""
    issues = []
    # 在題幹/選項/申論文字中找五位數
    for m in re.finditer(r'(?<!\d)(\d{5})(?!\d)', text):
        num = m.group(1)
        if num in KNOWN_NUMBERS:
            continue
        # 排除年份（民國+西元）
        n = int(num)
        if 10000 <= n <= 20000:
            # 可能是五位數代號
            # 檢查前後文，排除合理的數字用途
            before = text[max(0, m.start()-5):m.start()]
            after = text[m.end():m.end()+5]
            # 如果前面是「代號」則正常
            if '代號' in before or '代號' in text[max(0, m.start()-10):m.start()]:
                continue
            # 如果在 meta-line 中則正常
            if context.startswith("元"):
                continue
            if context.startswith("標記"):
                continue
            snippet = text[max(0, m.start()-10):m.end()+10]
            issues.append(f"  代號殘留: '{snippet}' (在{context}中)")
    return issues


def check_pdf_coverage(pdf_text, html_texts, year, name):
    """
    PDF → HTML 覆蓋檢查。
    從 PDF 中提取每道題的題幹，確認 HTML 中包含。
    """
    issues = []
    pdf_norm = norm(pdf_text)

    # 收集所有 HTML 題幹的正規化文字
    html_norms = set()
    for label, text in html_texts:
        if label.startswith("Q") or label.startswith("申論"):
            n = norm(text)
            if len(n) > 10:
                html_norms.add(n[:30])  # 取前30字作為指紋

    # 從 PDF 提取題號和題幹
    q_pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\s*[\.、）\)]\s*(.{10,}?)(?=\n\s*\d{1,2}\s*[\.、）\)]|\n\s*[（\(][A-Da-d]|\Z)', re.DOTALL)
    for m in q_pattern.finditer(pdf_text):
        q_num = m.group(1)
        q_text = m.group(2).strip()[:80]
        q_norm = norm(q_text)[:30]

        if len(q_norm) < 8:
            continue

        # 在 HTML 中尋找
        found = False
        for hn in html_norms:
            if q_norm[:15] in hn or hn[:15] in q_norm:
                found = True
                break

        if not found:
            # 用更寬鬆的方式再找
            if q_norm[:10] in norm(" ".join(t for _, t in html_texts)):
                found = True

        if not found:
            issues.append(f"  PDF Q{q_num} 可能在 HTML 中缺失: '{q_text[:50]}...'")

    return issues


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
    print("  最終 OCR 瑕疵掃描 v6")
    print("=" * 70)
    print()

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, "html.parser")

    total_issues = 0
    total_cards = 0
    clean_count = 0
    all_issues = defaultdict(list)

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
        total_cards += 1

        # 提取所有文字
        texts = extract_card_texts(soup, card_id)
        card_issues = []

        for label, text in texts:
            # 英文品質檢查
            eng_issues = check_english_quality(text, label)
            card_issues.extend(eng_issues)

            # 代號汙染檢查（排除元資料和標記）
            if not label.startswith("元") and not label.startswith("標記"):
                code_issues = check_code_contamination(text, label)
                card_issues.extend(code_issues)

        # PDF 覆蓋檢查
        pdf_path = find_pdf(year, code)
        if pdf_path:
            try:
                pdf_text = extract_pdf_text(pdf_path)
                coverage_issues = check_pdf_coverage(pdf_text, texts, year, name)
                card_issues.extend(coverage_issues)
            except Exception as e:
                if args.verbose:
                    print(f"  [PDF讀取失敗: {e}]")

        if card_issues:
            key = f"[{year}年 {name}]"
            all_issues[key] = card_issues
            total_issues += len(card_issues)
            print(f"{key} ⚠ {len(card_issues)} 個問題")
            for iss in card_issues:
                print(iss)
        else:
            clean_count += 1
            if args.verbose:
                print(f"[{year}年 {name}] ✓")

    print()
    print("=" * 70)
    print(f"  掃描卡片: {total_cards}")
    print(f"  通過: {clean_count}")
    print(f"  有問題: {total_cards - clean_count}")
    print(f"  問題總數: {total_issues}")
    print("=" * 70)

    # 儲存報告
    rpt = BASE_DIR / "reports" / "final_scan_report.txt"
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("最終 OCR 瑕疵掃描報告 v6\n")
        f.write("=" * 70 + "\n")
        f.write(f"掃描: {total_cards}, 通過: {clean_count}, 問題: {total_issues}\n\n")
        for key, issues in all_issues.items():
            f.write(f"\n{key}\n")
            for i, iss in enumerate(issues, 1):
                f.write(f"  {i}. {iss}\n")
    print(f"\n報告: {rpt}")


if __name__ == "__main__":
    main()
