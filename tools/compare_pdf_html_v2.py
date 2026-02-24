#!/usr/bin/env python3
"""
PDF-HTML 全面比對系統 v2 — 精準版
策略：
  1. 從 HTML 逐題提取文字
  2. 從 PDF 逐題提取文字
  3. 以題號為錨點，逐題 fuzzy 比對
  4. 同時掃描 HTML 英文段落的空白/黏字問題

用法：
  python compare_pdf_html_v2.py                    # 全面比對
  python compare_pdf_html_v2.py --year 111         # 特定年份
  python compare_pdf_html_v2.py --subject 38157    # 特定科目
"""

import os
import re
import sys
import argparse
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

try:
    import pdfplumber
except ImportError:
    print("錯誤：需要 pdfplumber"); sys.exit(1)
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("錯誤：需要 beautifulsoup4"); sys.exit(1)

# ============================================================
# 路徑
# ============================================================
BASE_DIR = Path(r"C:\Users\User\Desktop\考古題下載\資管系考古題")
HTML_FILE = BASE_DIR / "資管系考古題總覽.html"

SUBJECT_CODE_TO_FOLDER = {
    "38157": "中華民國憲法與警察專業英文",
    "28884": "國文",
    "30930": "國文",
    "11008": "國文",
    "66628": "數位鑑識執法",
    "46543": "警察情境實務",
    "73897": "警察情境實務",
    "93826": "警察法規",
    "63567": "警察法規",
    "89699": "警政資訊管理學系與應用",
    "92248": "電腦犯罪偵查",
}

DISPLAY_NAME = {
    "38157": "憲法英文", "28884": "國文", "30930": "國文", "11008": "國文",
    "66628": "數位鑑識", "46543": "情境實務", "73897": "情境實務",
    "93826": "警察法規", "63567": "警察法規", "89699": "資訊管理學系", "92248": "電腦犯罪",
}

# ============================================================
# PDF 處理
# ============================================================

def find_pdf(year: int, code: str) -> Path | None:
    year_dir = BASE_DIR / f"{year}年"
    if not year_dir.exists():
        return None
    prefix = SUBJECT_CODE_TO_FOLDER.get(code, "")[:3]
    if not prefix:
        return None
    for folder in year_dir.iterdir():
        if folder.is_dir() and folder.name.startswith(prefix):
            pdf = folder / "試題.pdf"
            if pdf.exists():
                return pdf
    return None


def extract_pdf_full_text(pdf_path: Path) -> str:
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
    except Exception as e:
        return ""
    return "\n".join(parts)


def extract_pdf_questions_by_number(pdf_text: str) -> dict[int, str]:
    """
    從 PDF 全文中，以題號為錨點切割出每一題的完整文字。
    回傳 {題號: 完整原文（含題幹+選項）}
    """
    questions = {}
    # 找所有 "數字" 開頭的題目位置（中文考題通常是 "1、" 或 "1."）
    # 英文選擇題可能是 "41." 或 "41 "
    pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\s*[\.、）\)\s]', re.MULTILINE)
    matches = list(pattern.finditer(pdf_text))

    for i, m in enumerate(matches):
        q_num = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(pdf_text)
        q_text = pdf_text[start:end].strip()
        # 去除開頭的題號
        q_text = re.sub(r'^\d{1,2}\s*[\.、）\)]\s*', '', q_text)
        questions[q_num] = q_text

    return questions


# ============================================================
# HTML 處理
# ============================================================

def parse_html(html_path: Path) -> dict:
    """
    解析 HTML，回傳 {card_id: {title, mc_questions, essays, full_text}}
    mc_questions = [{num, stem, options: {A:..., B:...}, stem_raw, options_raw}]
    """
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    cards = {}
    for card in soup.find_all("div", class_="subject-card"):
        card_id = card.get("id", "")
        if not card_id:
            continue

        h3 = card.find("h3")
        title = h3.get_text(strip=True) if h3 else ""

        mc_questions = []
        for q_div in card.find_all("div", class_="question"):
            q = {}
            num_span = q_div.find("span", class_="q-num")
            if num_span:
                nm = re.search(r'(\d+)', num_span.get_text(strip=True))
                q["num"] = int(nm.group(1)) if nm else 0
            else:
                q["num"] = 0

            text_span = q_div.find("span", class_="q-text")
            q["stem"] = text_span.get_text(strip=True) if text_span else ""

            q["options"] = {}
            for opt in q_div.find_all("div", class_="option"):
                lbl = opt.find("span", class_="opt-label")
                txt = opt.find("span", class_="opt-text")
                if lbl and txt:
                    letter = lbl.get_text(strip=True).replace("(", "").replace(")", "").strip().upper()
                    q["options"][letter] = txt.get_text(strip=True)

            # 完整文字（題幹+所有選項）
            q["full_text"] = q["stem"] + " " + " ".join(q["options"].values())
            mc_questions.append(q)

        essays = []
        for essay in card.find_all("div", class_="essay-question"):
            essays.append(essay.get_text(strip=True))

        # 閱讀測驗段落
        passages = []
        for p in card.find_all("div", class_="reading-passage"):
            passages.append(p.get_text(strip=True))
        for p in card.find_all("div", class_="exam-note"):
            passages.append(p.get_text(strip=True))

        # 全部文字（含所有元素）
        all_text_parts = []
        for q in mc_questions:
            all_text_parts.append(q["full_text"])
        all_text_parts.extend(essays)
        all_text_parts.extend(passages)

        cards[card_id] = {
            "title": title,
            "mc_questions": mc_questions,
            "essays": essays,
            "passages": passages,
            "full_text": "\n".join(all_text_parts),
        }

    return cards


# ============================================================
# 正規化與比對工具
# ============================================================

def norm(text: str) -> str:
    """去除空白、標點差異"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r'\s+', '', t)
    t = t.replace('，', ',').replace('。', '.').replace('；', ';')
    t = t.replace('：', ':').replace('？', '?').replace('！', '!')
    t = t.replace('（', '(').replace('）', ')')
    return t.lower()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_diffs(a: str, b: str) -> list[dict]:
    """找出 a 與 b 之間的具體差異"""
    diffs = []
    matcher = SequenceMatcher(None, a, b)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        a_seg = a[i1:i2]
        b_seg = b[j1:j2]
        # 只報告有意義的差異（長度>0 的替換/增刪）
        if len(a_seg) + len(b_seg) < 2:
            continue
        # 過濾考卷代號
        if re.match(r'^\d{5}$', a_seg) or re.match(r'^\d{5}$', b_seg):
            continue

        ctx_a = a[max(0, i1-10):min(len(a), i2+10)]
        ctx_b = b[max(0, j1-10):min(len(b), j2+10)]
        diffs.append({
            "tag": tag,
            "pdf": a_seg[:60],
            "html": b_seg[:60],
            "pdf_ctx": ctx_a[:80],
            "html_ctx": ctx_b[:80],
        })
    return diffs


# ============================================================
# 英文品質掃描器（獨立於 PDF 比對）
# ============================================================

def scan_english_issues(text: str) -> list[str]:
    """掃描文字中的英文 OCR 問題"""
    issues = []

    # 1. 黏字：小寫英文連續 >18 字元且不是已知長字
    KNOWN_LONG_WORDS = {
        'responsibilities', 'telecommunications', 'unconstitutional',
        'internationalization', 'counterintelligence', 'disproportionate',
        'electromagnetic', 'interconnectedness', 'interdisciplinary',
        'nonprofessional', 'counterterrorism', 'professionalism',
        'professionalization', 'unprofessional', 'misdemeanor',
        'reconnaissance', 'acknowledgement', 'incomprehensible',
        'interrelationship', 'characterization', 'communications',
        'disruptiontheyseek',  # this one is actually glued!
        'representatives', 'recommendation', 'authentication',
        'correspondence', 'discrimination', 'administrative',
        'transportation', 'infrastructure', 'approximately',
        'vulnerabilities', 'implementation', 'communication',
        'organizational', 'identification', 'investigation',
        'accountability', 'understanding', 'pharmaceutical',
        'counterfeiting', 'cryptocurrency', 'simultaneously',
        'whistleblowing', 'whistleblower', 'whistleblowers',
        'confidentiality', 'rehabilitation', 'dissatisfaction',
        'decriminalization', 'nondiscrimination',
    }
    for m in re.finditer(r'\b([a-z]{18,})\b', text):
        word = m.group(1)
        if word not in KNOWN_LONG_WORDS:
            issues.append(f"疑似黏字: '{word}' (長度 {len(word)})")

    # 2. 特定已知黏字模式
    glued_patterns = [
        (r'[a-z]{2,}[A-Z][a-z]+(?:[A-Z][a-z]+)+', '駝峰式黏字'),  # camelCase in text
    ]
    for pat, desc in glued_patterns:
        for m in re.finditer(pat, text):
            word = m.group()
            # 排除正常的專有名詞 (如 iPhone, JavaScript)
            if word in ('iPhone', 'JavaScript', 'YouTube', 'LinkedIn',
                        'PowerPoint', 'WordPress', 'GitHub', 'IoT',
                        'MacBook', 'ChatGPT'):
                continue
            # 排除 of/and/the + Capital 的組合
            if re.match(r'^(of|and|the|in|on|at|to|for|by)[A-Z]', word):
                issues.append(f"黏字: '{word}' ({desc})")

    # 3. 英文逗號後缺空格（排除數字如 1,000）
    for m in re.finditer(r'([a-zA-Z]),([a-zA-Z])', text):
        ctx_start = max(0, m.start() - 15)
        ctx_end = min(len(text), m.end() + 15)
        ctx = text[ctx_start:ctx_end]
        issues.append(f"逗號後缺空格: '...{ctx}...'")

    # 4. 英文句號後缺空格（排除縮寫如 U.S., Dr., Mr., e.g., i.e.）
    for m in re.finditer(r'([a-z])\.([A-Z])', text):
        # 檢查前面是否是縮寫
        pre = text[max(0, m.start()-3):m.start()+1]
        if re.search(r'[A-Z]\.[A-Z]\.', pre):  # U.S.A. 等
            continue
        if re.search(r'\b(Mr|Ms|Dr|Jr|Sr|St|vs|etc|eg|ie)\.$', pre, re.I):
            continue
        ctx_start = max(0, m.start() - 15)
        ctx_end = min(len(text), m.end() + 15)
        ctx = text[ctx_start:ctx_end]
        issues.append(f"句號後缺空格: '...{ctx}...'")

    # 5. 常見的斷字模式
    split_checks = [
        (r'\bth at\b', 'th at → that'),
        (r'\bf or\b', 'f or → for'),
        (r'\bc an\b', 'c an → can'),
        (r'\bwh at\b', 'wh at → what'),
        (r'\bwh en\b', 'wh en → when'),
        (r'\bmin or\b', 'min or → minor'),
        (r'\bgr and\b', 'gr and → grand'),
        (r'\bsumm on\b', 'summ on → summon'),
        (r'\bhum an\b', 'hum an → human'),
        (r'\bmonit or\b', 'monit or → monitor'),
        (r'\bmilli on\b', 'milli on → million'),
        (r'\bsqu are\b', 'squ are → square'),
        (r'\bbe at\b', 'be at → beat'),
        (r'\bTaiw an\b', 'Taiw an → Taiwan'),
        (r'\b\w+\s+tion\b', '可能 -tion 斷字'),
        (r'\b\w+\s+sion\b', '可能 -sion 斷字'),
    ]
    for pat, desc in split_checks:
        for m in re.finditer(pat, text):
            matched = m.group()
            # -tion/-sion 的特殊處理：排除正常的詞組
            if 'tion' in desc or 'sion' in desc:
                # 檢查前面的部分是否是完整單字
                parts = matched.rsplit(None, 1)
                if len(parts) == 2:
                    prefix = parts[0]
                    # 如果前綴本身是個常見完整單字，跳過
                    common_words = {'no', 'the', 'a', 'an', 'in', 'on', 'at', 'to',
                                    'is', 'it', 'my', 'your', 'his', 'her', 'our',
                                    'their', 'this', 'that', 'one', 'two', 'old',
                                    'new', 'big', 'own', 'per', 'pro', 'non',
                                    'any', 'all', 'much', 'such', 'each', 'next',
                                    'self', 'full', 'well', 'long', 'high', 'low',
                                    'under', 'over', 'pre', 'post', 'out', 'sub',
                                    'first', 'second', 'third', 'fourth', 'every',
                                    'some', 'same', 'more', 'most', 'least', 'less',
                                    'top', 'best', 'last', 'past', 'good', 'bad',
                                    'real', 'true', 'false', 'main', 'key', 'due',
                                    'special', 'social', 'local', 'legal', 'general',
                                    'national', 'international', 'personal', 'public',
                                    'free', 'open', 'clear', 'common', 'direct',
                                    'total', 'final', 'basic', 'major', 'minor',
                                    'federal', 'central', 'mental', 'digital',
                                    'further', 'other', 'another', 'question',
                                    'position', 'situation', 'information',
                                    'communication', 'administration',
                                    'investigation', 'discrimination'}
                    if prefix.lower() in common_words:
                        continue
            issues.append(f"斷字: '{matched}' ({desc})")

    return issues


# ============================================================
# 逐題 PDF vs HTML 比對
# ============================================================

def compare_question_level(pdf_questions: dict, html_questions: list) -> list[dict]:
    """
    以題號為錨點逐題比對 PDF vs HTML。
    """
    issues = []

    for hq in html_questions:
        q_num = hq.get("num", 0)
        if q_num == 0:
            continue

        pdf_q = pdf_questions.get(q_num)
        if not pdf_q:
            continue

        # 正規化比對
        n_pdf = norm(pdf_q)
        n_html = norm(hq["full_text"])

        sim = similarity(n_pdf, n_html)

        if sim > 0.95:
            continue  # 幾乎一致，跳過

        if sim < 0.3:
            # 太不像，可能題號對不上
            continue

        # 找出具體差異
        diffs = find_diffs(n_pdf, n_html)
        for d in diffs:
            # 過濾掉結構性差異（如 (A)(B)(C)(D) 選項標號）
            if re.match(r'^[\(\)abcd]+$', d["pdf"]) or re.match(r'^[\(\)abcd]+$', d["html"]):
                continue
            if len(d["pdf"]) < 2 and len(d["html"]) < 2:
                continue

            issues.append({
                "q_num": q_num,
                "type": d["tag"],
                "pdf": d["pdf"],
                "html": d["html"],
                "pdf_ctx": d["pdf_ctx"],
                "html_ctx": d["html_ctx"],
                "similarity": sim,
            })

    return issues


# ============================================================
# 主程式
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="PDF-HTML 精準比對系統 v2")
    parser.add_argument("--year", type=int, help="只比對特定年份")
    parser.add_argument("--subject", type=str, help="只比對特定科目代號")
    args = parser.parse_args()

    print("=" * 70)
    print("  PDF ↔ HTML 精準比對系統 v2")
    print("=" * 70)
    print()

    # 載入 HTML
    print(f"解析 HTML...")
    html_cards = parse_html(HTML_FILE)
    print(f"  {len(html_cards)} 張科目卡片")
    print()

    total_real_issues = 0
    report_lines = []

    for card_id, card_data in sorted(html_cards.items()):
        m = re.match(r'y(\d+)-(\d+)', card_id)
        if not m:
            continue
        year = int(m.group(1))
        code = m.group(2)

        if args.year and year != args.year:
            continue
        if args.subject and code != args.subject:
            continue

        name = DISPLAY_NAME.get(code, code)
        header = f"[{year}年 {name}]"

        # 找 PDF
        pdf_path = find_pdf(year, code)

        card_issues = []

        # ========== 英文品質掃描 ==========
        full_text = card_data["full_text"]
        eng_issues = scan_english_issues(full_text)
        for ei in eng_issues:
            card_issues.append(f"  英文掃描: {ei}")

        # ========== 選項/題幹品質掃描 ==========
        for q in card_data["mc_questions"]:
            q_num = q["num"]
            # 逐個選項和題幹掃描
            for label, opt_text in q["options"].items():
                iss = scan_english_issues(opt_text)
                for i in iss:
                    card_issues.append(f"  Q{q_num} 選項{label}: {i}")
            stem_iss = scan_english_issues(q["stem"])
            for i in stem_iss:
                card_issues.append(f"  Q{q_num} 題幹: {i}")

        # ========== 申論題掃描 ==========
        for idx, essay in enumerate(card_data["essays"], 1):
            iss = scan_english_issues(essay)
            for i in iss:
                card_issues.append(f"  申論{idx}: {i}")

        # ========== 閱讀測驗段落掃描 ==========
        for idx, passage in enumerate(card_data["passages"], 1):
            iss = scan_english_issues(passage)
            for i in iss:
                card_issues.append(f"  段落{idx}: {i}")

        # ========== PDF 逐題比對（選擇題） ==========
        if pdf_path:
            pdf_text = extract_pdf_full_text(pdf_path)
            if pdf_text:
                pdf_qs = extract_pdf_questions_by_number(pdf_text)
                q_diffs = compare_question_level(pdf_qs, card_data["mc_questions"])
                for qd in q_diffs:
                    card_issues.append(
                        f"  Q{qd['q_num']} PDF差異 [{qd['type']}]: "
                        f"PDF='{qd['pdf']}' vs HTML='{qd['html']}' "
                        f"(相似度 {qd['similarity']:.0%})"
                    )

        # 去重
        card_issues = list(dict.fromkeys(card_issues))

        if card_issues:
            print(f"{header} ⚠ {len(card_issues)} 個問題")
            for ci in card_issues:
                print(ci)
            total_real_issues += len(card_issues)
            report_lines.append(f"\n{header}")
            report_lines.extend(card_issues)
        else:
            print(f"{header} ✓")

    print()
    print("=" * 70)
    print(f"  總計發現: {total_real_issues} 個問題")
    print("=" * 70)

    # 儲存報告
    report_path = BASE_DIR / "reports" / "comparison_report_v2.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("PDF ↔ HTML 精準比對報告 v2\n")
        f.write("=" * 70 + "\n")
        f.write(f"總計: {total_real_issues} 個問題\n")
        f.write("\n".join(report_lines))
    print(f"\n報告已儲存: {report_path}")


if __name__ == "__main__":
    main()
