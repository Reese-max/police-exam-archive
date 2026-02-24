#!/usr/bin/env python3
"""
PDF-HTML 全面比對系統
自動提取所有 70 份 PDF 的文字，與 HTML 中的考題內容逐題比對，
找出所有 OCR 瑕疵（黏字、斷字、缺字、錯字等）。

用法：
  python compare_pdf_html.py                    # 執行全面比對
  python compare_pdf_html.py --year 114         # 只比對特定年份
  python compare_pdf_html.py --subject 38157    # 只比對特定科目
  python compare_pdf_html.py --report report.txt # 輸出報告到檔案
"""

import os
import re
import sys
import argparse
import unicodedata
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher

try:
    import pdfplumber
except ImportError:
    print("錯誤：需要 pdfplumber。請執行 pip install pdfplumber")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("錯誤：需要 beautifulsoup4。請執行 pip install beautifulsoup4")
    sys.exit(1)

# ============================================================
# 路徑與對應關係
# ============================================================

BASE_DIR = Path(r"C:\Users\User\Desktop\考古題下載\資管系考古題")
HTML_FILE = BASE_DIR / "資管系考古題總覽.html"

# 科目代號 → 資料夾名稱的對應（某些年份的資料夾名稱和代號不同）
# 注意：106年的警察情境實務和警察法規用了不同代號
SUBJECT_CODE_TO_FOLDER = {
    "38157": "中華民國憲法與警察專業英文",
    "28884": "國文(作文與測驗)",      # 112-114
    "30930": "國文（作文、公文與測驗）",  # 105-109, 111
    "11008": "國文(作文、公文與測驗)",   # 110
    "66628": "數位鑑識執法",
    "46543": "警察情境實務",           # 括號部分省略，靠模糊匹配
    "73897": "警察情境實務",           # 106年代號
    "93826": "警察法規",              # 括號部分省略，靠模糊匹配
    "63567": "警察法規",              # 106年代號
    "89699": "警政資訊管理學系與應用",
    "92248": "電腦犯罪偵查",
}

SUBJECT_DISPLAY_NAME = {
    "38157": "憲法與警察專業英文",
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


def find_pdf_path(year: int, subject_code: str) -> Path | None:
    """根據年份和科目代號找到 PDF 檔案路徑"""
    year_dir = BASE_DIR / f"{year}年"
    if not year_dir.exists():
        return None

    # 取得基本資料夾名稱
    base_name = SUBJECT_CODE_TO_FOLDER.get(subject_code, "")
    if not base_name:
        return None

    # 嘗試直接匹配
    for folder in year_dir.iterdir():
        if folder.is_dir():
            folder_name = folder.name
            # 精確匹配或前綴匹配（處理括號差異）
            if folder_name == base_name or folder_name.startswith(base_name):
                pdf = folder / "試題.pdf"
                if pdf.exists():
                    return pdf

    # 模糊匹配：取前3個字做匹配
    prefix = base_name[:3]
    for folder in year_dir.iterdir():
        if folder.is_dir() and folder.name.startswith(prefix):
            pdf = folder / "試題.pdf"
            if pdf.exists():
                return pdf

    return None


# ============================================================
# PDF 文字提取
# ============================================================

def extract_pdf_text(pdf_path: Path) -> str:
    """從 PDF 提取完整文字"""
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception as e:
        return f"[PDF 讀取錯誤: {e}]"
    return "\n".join(text_parts)


def extract_pdf_questions(pdf_text: str) -> dict:
    """
    從 PDF 文字中提取逐題內容。
    回傳: {題號: {"stem": 題幹文字, "options": {"A": ..., "B": ..., ...}}}
    """
    questions = {}
    lines = pdf_text.split("\n")

    # 合併所有文字為一個大字串，方便正則匹配
    full_text = "\n".join(lines)

    # 匹配選擇題：數字. 或 數字、 或 Q數字 開頭
    # 先嘗試找出所有題號位置
    q_pattern = re.compile(
        r'(?:^|\n)\s*(\d{1,2})\s*[\.、）\)]\s*(.+?)(?=\n\s*\d{1,2}\s*[\.、）\)]|\n\s*[一二三四五六七八九十]+\s*[、\.．]|\Z)',
        re.DOTALL
    )

    for m in q_pattern.finditer(full_text):
        q_num = int(m.group(1))
        q_body = m.group(2).strip()

        # 從題目內容中分離選項
        opts = {}
        opt_pattern = re.compile(
            r'[\(（]?\s*([A-Da-d])\s*[\)）]?\s*(.+?)(?=[\(（]?\s*[A-Da-d]\s*[\)）]|\Z)',
            re.DOTALL
        )
        opt_matches = list(opt_pattern.finditer(q_body))

        if opt_matches:
            stem = q_body[:opt_matches[0].start()].strip()
            for om in opt_matches:
                opt_letter = om.group(1).upper()
                opt_text = om.group(2).strip()
                opts[opt_letter] = opt_text
        else:
            stem = q_body

        questions[q_num] = {"stem": stem, "options": opts}

    return questions


# ============================================================
# HTML 文字提取
# ============================================================

def parse_html_cards(html_path: Path) -> dict:
    """
    解析 HTML，提取每張科目卡片的內容。
    回傳: {"y{年}-{代號}": {"title": 科目名, "questions": [...], "raw_text": 完整文字}}
    """
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    cards = {}
    for card in soup.find_all("div", class_="subject-card"):
        card_id = card.get("id", "")
        if not card_id:
            continue

        # 取得科目標題
        h3 = card.find("h3")
        title = h3.get_text(strip=True) if h3 else ""

        # 提取所有題目文字
        questions = []
        raw_texts = []

        # 選擇題
        for q_div in card.find_all("div", class_="question"):
            q_data = {}
            # 題號
            q_num_span = q_div.find("span", class_="q-num")
            if q_num_span:
                num_text = q_num_span.get_text(strip=True)
                num_match = re.search(r'(\d+)', num_text)
                q_data["num"] = int(num_match.group(1)) if num_match else 0

            # 題幹
            q_text_span = q_div.find("span", class_="q-text")
            if q_text_span:
                q_data["stem"] = q_text_span.get_text(strip=True)
                raw_texts.append(q_data["stem"])

            # 選項
            q_data["options"] = {}
            for opt in q_div.find_all("div", class_="option"):
                opt_label_span = opt.find("span", class_="opt-label")
                opt_text_span = opt.find("span", class_="opt-text")
                if opt_label_span and opt_text_span:
                    label = opt_label_span.get_text(strip=True).replace("(", "").replace(")", "").strip()
                    text = opt_text_span.get_text(strip=True)
                    q_data["options"][label] = text
                    raw_texts.append(text)

            questions.append(q_data)

        # 申論題
        for essay in card.find_all("div", class_="essay-question"):
            text = essay.get_text(strip=True)
            raw_texts.append(text)
            questions.append({"type": "essay", "text": text})

        # 閱讀測驗段落
        for passage in card.find_all("div", class_="reading-passage"):
            text = passage.get_text(strip=True)
            raw_texts.append(text)

        # exam-text (考試說明)
        for et in card.find_all("div", class_="exam-text"):
            text = et.get_text(strip=True)
            raw_texts.append(text)

        # exam-note
        for en in card.find_all("div", class_="exam-note"):
            text = en.get_text(strip=True)
            raw_texts.append(text)

        cards[card_id] = {
            "title": title,
            "questions": questions,
            "raw_text": "\n".join(raw_texts),
        }

    return cards


# ============================================================
# 文字正規化（用於比對）
# ============================================================

def normalize_text(text: str) -> str:
    """正規化文字以利比對：移除空白、標點差異等"""
    # 統一全形/半形
    text = unicodedata.normalize("NFKC", text)
    # 移除所有空白
    text = re.sub(r'\s+', '', text)
    # 統一標點
    text = text.replace('，', ',').replace('。', '.').replace('；', ';')
    text = text.replace('：', ':').replace('？', '?').replace('！', '!')
    text = text.replace('（', '(').replace('）', ')')
    text = text.replace('「', '"').replace('」', '"')
    text = text.replace('『', '"').replace('』', '"')
    text = text.replace('—', '-').replace('─', '-')
    return text.lower()


def normalize_for_english(text: str) -> str:
    """正規化英文文字：保留空白（用於偵測黏字/斷字）"""
    text = unicodedata.normalize("NFKC", text)
    # 合併連續空白為單一空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================================
# 比對引擎
# ============================================================

def find_english_segments(text: str) -> list[str]:
    """從文字中提取所有連續英文片段"""
    # 匹配連續的英文字母+空白+標點序列
    return re.findall(r'[A-Za-z][A-Za-z\s\',\.\-\(\)]{5,}', text)


def detect_glued_words(text: str) -> list[str]:
    """偵測黏在一起的英文單字"""
    issues = []
    # 找出所有英文片段
    eng_segments = find_english_segments(text)
    for seg in eng_segments:
        # 檢查是否有小寫+大寫黏在一起（如 communityPolicing 不算，但 communitypolicing 有問題）
        # 偵測常見的黏字模式：兩個以上的英文單字黏在一起
        words = seg.split()
        for word in words:
            # 長度超過 15 且全小寫的英文字串很可能是黏字
            if len(word) > 15 and word.isalpha() and word.islower():
                issues.append(f"可能黏字: '{word}'")
            # 小寫字母接大寫（非首字母）如 policeOfficers
            if re.search(r'[a-z][A-Z]', word) and not word[0].isupper():
                issues.append(f"大小寫交界可能黏字: '{word}'")
    return issues


def detect_split_words(text: str) -> list[str]:
    """偵測被拆開的英文單字"""
    issues = []
    # 常見的被拆開模式
    split_patterns = [
        (r'\b(\w+)\s+(tion)\b', 'tion 斷字'),
        (r'\b(\w+)\s+(sion)\b', 'sion 斷字'),
        (r'\b(\w+)\s+(ment)\b', 'ment 斷字'),
        (r'\b(\w+)\s+(ness)\b', 'ness 斷字'),
        (r'\b(\w+)\s+(ance)\b', 'ance 斷字'),
        (r'\b(\w+)\s+(ence)\b', 'ence 斷字'),
        (r'\b(\w+)\s+(able)\b', 'able 斷字'),
        (r'\b(\w+)\s+(ible)\b', 'ible 斷字'),
        (r'\bth\s+at\b', 'th at → that'),
        (r'\bf\s+or\b', 'f or → for'),
        (r'\bc\s+an\b', 'c an → can'),
        (r'\bwh\s+at\b', 'wh at → what'),
        (r'\bwh\s+en\b', 'wh en → when'),
        (r'\bmin\s+or\b', 'min or → minor'),
        (r'\bgr\s+and\b', 'gr and → grand'),
        (r'\bsumm\s+on\b', 'summ on → summon'),
        (r'\bhum\s+an\b', 'hum an → human'),
        (r'\bmonit\s+or\b', 'monit or → monitor'),
        (r'\bmilli\s+on\b', 'milli on → million'),
        (r'\bsqu\s+are\b', 'squ are → square'),
        (r'\bbe\s+at\b', 'be at → beat'),
    ]

    for pattern, desc in split_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            issues.append(f"{desc}: '{m.group()}'")

    return issues


def compare_texts_detailed(pdf_text: str, html_text: str) -> list[dict]:
    """
    逐段比對 PDF 與 HTML 文字，找出所有差異。
    """
    issues = []

    # 1. 先做正規化比對：移除所有空白後比較
    norm_pdf = normalize_text(pdf_text)
    norm_html = normalize_text(html_text)

    if norm_pdf == norm_html:
        return []  # 文字完全相同，無問題

    # 2. 找出差異的位置
    matcher = SequenceMatcher(None, norm_pdf, norm_html)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != 'equal':
            pdf_segment = norm_pdf[max(0, i1-20):i2+20]
            html_segment = norm_html[max(0, j1-20):j2+20]

            if tag == 'replace':
                issues.append({
                    "type": "替換",
                    "pdf": norm_pdf[i1:i2],
                    "html": norm_html[j1:j2],
                    "pdf_context": pdf_segment,
                    "html_context": html_segment,
                })
            elif tag == 'delete':
                issues.append({
                    "type": "PDF 有但 HTML 缺少",
                    "pdf": norm_pdf[i1:i2],
                    "pdf_context": pdf_segment,
                })
            elif tag == 'insert':
                issues.append({
                    "type": "HTML 多出",
                    "html": norm_html[j1:j2],
                    "html_context": html_segment,
                })

    return issues


def compare_question_by_question(pdf_text: str, html_questions: list) -> list[dict]:
    """
    嘗試逐題比對。從 PDF 文字中定位每道題目，與 HTML 題目比對。
    """
    issues = []

    for q in html_questions:
        if q.get("type") == "essay":
            continue  # 申論題另外處理

        q_num = q.get("num", 0)
        if q_num == 0:
            continue

        stem = q.get("stem", "")
        if not stem:
            continue

        # 在 HTML 的題幹和選項中偵測黏字/斷字
        glued = detect_glued_words(stem)
        split = detect_split_words(stem)

        for g in glued:
            issues.append({
                "question": q_num,
                "location": "題幹",
                "issue": g,
                "text": stem[:100],
            })
        for s in split:
            issues.append({
                "question": q_num,
                "location": "題幹",
                "issue": s,
                "text": stem[:100],
            })

        # 檢查選項
        for label, opt_text in q.get("options", {}).items():
            glued = detect_glued_words(opt_text)
            split = detect_split_words(opt_text)
            for g in glued:
                issues.append({
                    "question": q_num,
                    "location": f"選項 {label}",
                    "issue": g,
                    "text": opt_text[:100],
                })
            for s in split:
                issues.append({
                    "question": q_num,
                    "location": f"選項 {label}",
                    "issue": s,
                    "text": opt_text[:100],
                })

    return issues


def check_english_spacing(html_text: str) -> list[dict]:
    """
    檢查英文文字中的空白問題：
    - 標點後缺少空格
    - 英文單字黏在一起
    - 逗號/句號前有多餘空格
    """
    issues = []

    # 英文句子中逗號後沒有空格
    for m in re.finditer(r'[a-zA-Z],[a-zA-Z]', html_text):
        context_start = max(0, m.start() - 20)
        context_end = min(len(html_text), m.end() + 20)
        issues.append({
            "type": "逗號後缺空格",
            "text": html_text[context_start:context_end],
            "position": m.start(),
        })

    # 英文句子中句號後沒有空格（排除小數點和縮寫）
    for m in re.finditer(r'[a-z]\.[A-Z]', html_text):
        context_start = max(0, m.start() - 20)
        context_end = min(len(html_text), m.end() + 20)
        issues.append({
            "type": "句號後缺空格",
            "text": html_text[context_start:context_end],
            "position": m.start(),
        })

    return issues


def deep_compare_with_pdf(pdf_text: str, html_text: str, subject_name: str) -> list[dict]:
    """
    深度比對：將 PDF 文字和 HTML 文字都拆成 token，
    用 SequenceMatcher 找出具體差異。
    """
    issues = []

    # 正規化後逐字比對
    norm_pdf = normalize_text(pdf_text)
    norm_html = normalize_text(html_text)

    # 跳過太短的文字
    if len(norm_pdf) < 10 or len(norm_html) < 10:
        return issues

    # 計算相似度
    ratio = SequenceMatcher(None, norm_pdf, norm_html).ratio()

    if ratio < 0.5:
        # 如果相似度太低，可能是完全不同的內容，跳過
        issues.append({
            "type": "警告",
            "detail": f"PDF 與 HTML 文字相似度極低 ({ratio:.2%})，可能結構不對應",
        })
        return issues

    if ratio > 0.99:
        return issues  # 幾乎完全相同

    # 找出有差異的地方
    matcher = SequenceMatcher(None, norm_pdf, norm_html)
    diff_count = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != 'equal' and (i2 - i1 > 1 or j2 - j1 > 1):
            pdf_diff = norm_pdf[i1:i2]
            html_diff = norm_html[j1:j2]

            # 過濾掉考卷代號等無意義差異
            if re.match(r'^\d{5}$', pdf_diff) or re.match(r'^\d{5}$', html_diff):
                continue

            # 提供上下文
            ctx_start_p = max(0, i1 - 15)
            ctx_end_p = min(len(norm_pdf), i2 + 15)
            ctx_start_h = max(0, j1 - 15)
            ctx_end_h = min(len(norm_html), j2 + 15)

            issues.append({
                "type": tag,
                "pdf_text": pdf_diff[:80],
                "html_text": html_diff[:80],
                "pdf_context": norm_pdf[ctx_start_p:ctx_end_p],
                "html_context": norm_html[ctx_start_h:ctx_end_h],
            })
            diff_count += 1

            if diff_count > 50:
                issues.append({"type": "警告", "detail": "差異過多（>50），僅顯示前50個"})
                break

    return issues


# ============================================================
# 主程式
# ============================================================

def run_comparison(year_filter=None, subject_filter=None):
    """執行全面比對"""
    print("=" * 70)
    print("  PDF ↔ HTML 全面比對系統")
    print("=" * 70)
    print()

    # 載入 HTML
    print(f"正在解析 HTML: {HTML_FILE}")
    html_cards = parse_html_cards(HTML_FILE)
    print(f"  找到 {len(html_cards)} 張科目卡片")
    print()

    # 統計
    total_issues = 0
    total_pdfs = 0
    total_pdfs_ok = 0
    all_issues = []

    # 遍歷所有卡片
    for card_id, card_data in sorted(html_cards.items()):
        # 解析 card_id: y{年}-{代號}
        m = re.match(r'y(\d+)-(\d+)', card_id)
        if not m:
            continue
        year = int(m.group(1))
        code = m.group(2)

        # 篩選
        if year_filter and year != year_filter:
            continue
        if subject_filter and code != subject_filter:
            continue

        subject_name = SUBJECT_DISPLAY_NAME.get(code, code)

        # 找到對應 PDF
        pdf_path = find_pdf_path(year, code)
        if not pdf_path:
            print(f"[!] {year}年 {subject_name} ({code}): 找不到 PDF")
            continue

        total_pdfs += 1
        print(f"--- {year}年 {subject_name} ({code}) ---")
        print(f"    PDF: {pdf_path.name}")

        # 提取 PDF 文字
        pdf_text = extract_pdf_text(pdf_path)
        if pdf_text.startswith("[PDF 讀取錯誤"):
            print(f"    {pdf_text}")
            continue

        # 取得 HTML 文字
        html_raw = card_data["raw_text"]
        html_questions = card_data["questions"]

        # === 比對 1：HTML 內部的黏字/斷字偵測 ===
        card_issues = []

        q_issues = compare_question_by_question(pdf_text, html_questions)
        card_issues.extend(q_issues)

        # === 比對 2：英文空白問題偵測 ===
        spacing_issues = check_english_spacing(html_raw)
        for si in spacing_issues:
            card_issues.append({
                "question": "全文",
                "location": "英文空白",
                "issue": f"{si['type']}: ...{si['text']}...",
            })

        # === 比對 3：HTML raw text 中偵測黏字/斷字 ===
        glued_in_raw = detect_glued_words(html_raw)
        split_in_raw = detect_split_words(html_raw)
        for g in glued_in_raw:
            card_issues.append({
                "question": "全文",
                "location": "全文掃描",
                "issue": g,
            })
        for s in split_in_raw:
            card_issues.append({
                "question": "全文",
                "location": "全文掃描",
                "issue": s,
            })

        # === 比對 4：PDF vs HTML 深度比對 ===
        deep_issues = deep_compare_with_pdf(pdf_text, html_raw, subject_name)
        for di in deep_issues:
            if di.get("type") == "警告":
                card_issues.append({
                    "question": "全文",
                    "location": "深度比對",
                    "issue": di["detail"],
                })
            else:
                pdf_t = di.get("pdf_text", "")
                html_t = di.get("html_text", "")
                if pdf_t or html_t:
                    card_issues.append({
                        "question": "全文",
                        "location": "深度比對",
                        "issue": f"差異 [{di['type']}] PDF:'{pdf_t}' vs HTML:'{html_t}'",
                        "pdf_context": di.get("pdf_context", ""),
                        "html_context": di.get("html_context", ""),
                    })

        # 報告
        if card_issues:
            print(f"    ⚠ 發現 {len(card_issues)} 個問題：")
            for ci in card_issues:
                q = ci.get("question", "?")
                loc = ci.get("location", "")
                iss = ci.get("issue", "")
                print(f"      Q{q} [{loc}] {iss}")
            total_issues += len(card_issues)
            all_issues.append({
                "year": year,
                "code": code,
                "subject": subject_name,
                "issues": card_issues,
            })
        else:
            print("    ✓ 無問題")
            total_pdfs_ok += 1

        print()

    # 總結
    print("=" * 70)
    print(f"  比對完成")
    print(f"  檢查 PDF 數: {total_pdfs}")
    print(f"  無問題數: {total_pdfs_ok}")
    print(f"  有問題數: {total_pdfs - total_pdfs_ok}")
    print(f"  總問題數: {total_issues}")
    print("=" * 70)

    return all_issues


def generate_report(all_issues: list, output_path: Path):
    """產生詳細報告檔案"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("PDF ↔ HTML 比對報告\n")
        f.write("=" * 70 + "\n\n")

        for entry in all_issues:
            year = entry["year"]
            subject = entry["subject"]
            code = entry["code"]
            issues = entry["issues"]

            f.write(f"【{year}年 {subject} ({code})】\n")
            f.write(f"  問題數: {len(issues)}\n\n")

            for i, ci in enumerate(issues, 1):
                q = ci.get("question", "?")
                loc = ci.get("location", "")
                iss = ci.get("issue", "")
                f.write(f"  {i}. Q{q} [{loc}] {iss}\n")
                if "pdf_context" in ci:
                    f.write(f"     PDF 上下文: {ci['pdf_context']}\n")
                if "html_context" in ci:
                    f.write(f"     HTML 上下文: {ci['html_context']}\n")
                if "text" in ci:
                    f.write(f"     原文: {ci['text']}\n")
            f.write("\n" + "-" * 50 + "\n\n")

        f.write(f"\n總計: {sum(len(e['issues']) for e in all_issues)} 個問題\n")

    print(f"\n報告已儲存至: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="PDF-HTML 全面比對系統")
    parser.add_argument("--year", type=int, help="只比對特定年份 (105-114)")
    parser.add_argument("--subject", type=str, help="只比對特定科目代號")
    parser.add_argument("--report", type=str, default="comparison_report.txt",
                        help="輸出報告路徑 (預設: comparison_report.txt)")
    args = parser.parse_args()

    all_issues = run_comparison(
        year_filter=args.year,
        subject_filter=args.subject,
    )

    if all_issues:
        report_path = Path(BASE_DIR) / "reports" / args.report
        generate_report(all_issues, report_path)


if __name__ == "__main__":
    main()
