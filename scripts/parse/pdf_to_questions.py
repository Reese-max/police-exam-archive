# -*- coding: utf-8 -*-
"""
PDF → 結構化題目提取器
將考古題 PDF 自動轉成結構化的 JSON 題目資料
支援選擇題、申論題、閱讀測驗等題型

用法:
  python pdf_to_questions.py                     # 處理 考古題庫/ 下所有 PDF
  python pdf_to_questions.py --input 考古題庫/資訊管理學系  # 只處理資訊管理學系
  python pdf_to_questions.py --input path/to/試題.pdf   # 處理單一 PDF
"""

import os
import re
import json
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("需要安裝 pdfplumber: pip install pdfplumber")
    raise

# ===== 考卷標頭解析模式 =====
HEADER_PATTERNS = {
    'exam_type': re.compile(r'(\d{2,3})\s*年\s*(特種考試|公務人員特種考試)'),
    'exam_name': re.compile(r'(警察人員考試|一般警察人員考試)'),
    'level': re.compile(r'(三等|四等)考試'),
    'category': re.compile(r'類\s*科[：:]\s*(.+)'),
    'subject': re.compile(r'科\s*目[：:]\s*(.+)'),
    'exam_time': re.compile(r'考試時間[：:]\s*(.+)'),
    'code': re.compile(r'代號[：:]\s*(\d{5})'),
}

# ===== 結構解析模式 =====
# 選擇題題號: 1. / 1、/ 1 / ① 等
CHOICE_Q_PATTERN = re.compile(
    r'^[\s]*(\d{1,3})\s*[\.、．)\s]\s*(.+)', re.DOTALL
)

# 選項: (A) / （A）/ A. / A、等
OPTION_PATTERN = re.compile(
    r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=[\(（][A-Da-d][\)）]|$)',
    re.DOTALL
)

# 單行內多選項
INLINE_OPTIONS_PATTERN = re.compile(
    r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=\s*[\(（][A-Da-d][\)）]|\s*$)'
)

# 申論題題號: 一、 / 二、 / 三、等
ESSAY_Q_PATTERN = re.compile(
    r'^[\s]*([一二三四五六七八九十]+)\s*[、．.]\s*(.+)', re.DOTALL
)

# 考卷分段標記
SECTION_PATTERN = re.compile(
    r'^[\s]*(甲|乙)\s*[、．.]\s*(申論題|測驗題|選擇題)'
)

# 注意事項
NOTE_PATTERN = re.compile(
    r'^[\s]*[※＊\*]?\s*注意\s*[：:]'
)

# 考卷標頭行
HEADER_LINE_PATTERNS = [
    re.compile(r'^\d{2,3}年(公務|特種)'),
    re.compile(r'^代號[:：]'),
    re.compile(r'^頁次[:：]'),
    re.compile(r'^考試(別|時間)'),
    re.compile(r'^等\s*別[:：]'),
    re.compile(r'^類\s*科'),
    re.compile(r'^科\s*目[:：]'),
    re.compile(r'^座號'),
    re.compile(r'^(全一張|全一頁)'),
    re.compile(r'^-?\d+-?$'),
    re.compile(r'^\d{5}$'),
    re.compile(r'^(請接背面|請以背面)'),
    re.compile(r'^(背面尚有|請翻頁)'),
]


# ===== OCR 修復規則（簡化版，從 fix_ocr.py 提取核心規則）=====
OCR_FIXES = [
    # -tion 拆字
    (re.compile(r'(\w)ti on\b'), r'\1tion'),
    # -sion 拆字
    (re.compile(r'(\w)si on\b'), r'\1sion'),
    # th 系列
    (re.compile(r'\bth at\b'), 'that'),
    (re.compile(r'\bth is\b'), 'this'),
    (re.compile(r'\bth e\b'), 'the'),
    (re.compile(r'\bth ey\b'), 'they'),
    (re.compile(r'\bth eir\b'), 'their'),
    (re.compile(r'\bth ere\b'), 'there'),
    (re.compile(r'\bth ese\b'), 'these'),
    (re.compile(r'\bth ose\b'), 'those'),
    (re.compile(r'\bth rough\b'), 'through'),
    # wh 系列
    (re.compile(r'\bwh at\b'), 'what'),
    (re.compile(r'\bwh en\b'), 'when'),
    (re.compile(r'\bwh ere\b'), 'where'),
    (re.compile(r'\bwh ich\b'), 'which'),
    (re.compile(r'\bwh ile\b'), 'while'),
    # 常見
    (re.compile(r'\bf or\b'), 'for'),
    (re.compile(r'\bf rom\b'), 'from'),
    (re.compile(r'\bin to\b'), 'into'),
    (re.compile(r'\bhum an\b'), 'human'),
    (re.compile(r'\bpers on\b'), 'person'),
    (re.compile(r'\bpris on\b'), 'prison'),
    (re.compile(r'\breas on\b'), 'reason'),
    (re.compile(r'\bcomm on\b'), 'common'),
    (re.compile(r'\bmonit or\b'), 'monitor'),
]


def fix_ocr(text):
    """套用 OCR 修復規則"""
    for pattern, replacement in OCR_FIXES:
        text = pattern.sub(replacement, text)
    return text


def normalize_text(text):
    """正規化文字"""
    text = unicodedata.normalize('NFKC', text)
    # 移除考卷代號（5位數字）
    text = re.sub(r'\b\d{5}\b', '', text)
    text = fix_ocr(text)
    return text.strip()


def is_header_line(line):
    """判斷是否為考卷標頭行"""
    line = line.strip()
    if not line:
        return True
    for pat in HEADER_LINE_PATTERNS:
        if pat.match(line):
            return True
    if any(kw in line for kw in ['人員考試', '考試別', '退除役軍人']):
        if len(line) < 80:
            return True
    return False


def is_note_line(line):
    """判斷是否為注意事項"""
    line = line.strip()
    return bool(NOTE_PATTERN.match(line)) or \
        '不必抄題' in line or '不予計分' in line or \
        '禁止使用電子計算器' in line or \
        '本試題為單一選擇題' in line or \
        '鋼筆或原子筆' in line or \
        '2B鉛筆' in line or \
        '應使用本國文字' in line or \
        '可以使用電子計算器' in line


def extract_pdf_text(pdf_path):
    """從 PDF 提取文字"""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return pages_text


def parse_metadata(text):
    """從 PDF 文字中提取考卷元資料"""
    metadata = {}
    for key, pattern in HEADER_PATTERNS.items():
        match = pattern.search(text[:500])  # 只搜尋前500字元
        if match:
            metadata[key] = match.group(1) if match.lastindex else match.group(0)
    return metadata


def parse_questions(pages_text):
    """
    解析 PDF 文字為結構化題目
    Returns:
        dict: {
            'metadata': {...},
            'notes': [...],
            'sections': [...],
            'questions': [...]
        }
    """
    full_text = '\n'.join(pages_text)
    metadata = parse_metadata(full_text)

    # 收集所有內容行（排除標頭和注意事項）
    content_lines = []
    notes = []
    in_note = False

    for page_text in pages_text:
        for line in page_text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            if is_header_line(stripped):
                continue

            if is_note_line(stripped):
                notes.append(stripped)
                in_note = True
                continue

            if in_note and not CHOICE_Q_PATTERN.match(stripped) and \
               not ESSAY_Q_PATTERN.match(stripped) and \
               not SECTION_PATTERN.match(stripped):
                notes.append(stripped)
                continue

            in_note = False
            content_lines.append(stripped)

    # 解析內容行
    questions = []
    sections = []
    current_section = None

    i = 0
    while i < len(content_lines):
        line = content_lines[i]

        # 檢查分段標記
        section_match = SECTION_PATTERN.match(line)
        if section_match:
            current_section = f"{section_match.group(1)}、{section_match.group(2)}"
            sections.append(current_section)
            i += 1
            continue

        # 嘗試匹配申論題
        essay_match = ESSAY_Q_PATTERN.match(line)
        if essay_match:
            num_str = essay_match.group(1)
            stem = essay_match.group(2).strip()

            # 收集後續行（直到下一個題目或結束）
            i += 1
            while i < len(content_lines):
                next_line = content_lines[i]
                if ESSAY_Q_PATTERN.match(next_line) or \
                   CHOICE_Q_PATTERN.match(next_line) or \
                   SECTION_PATTERN.match(next_line):
                    break
                stem += '\n' + next_line
                i += 1

            questions.append({
                'number': num_str,
                'type': 'essay',
                'stem': normalize_text(stem),
                'section': current_section,
            })
            continue

        # 嘗試匹配選擇題
        choice_match = CHOICE_Q_PATTERN.match(line)
        if choice_match:
            num = int(choice_match.group(1))
            stem = choice_match.group(2).strip()

            # 收集題幹後續行和選項
            i += 1
            options_text = ''
            while i < len(content_lines):
                next_line = content_lines[i]
                # 到下一題了
                if CHOICE_Q_PATTERN.match(next_line) or \
                   ESSAY_Q_PATTERN.match(next_line) or \
                   SECTION_PATTERN.match(next_line):
                    break

                # 檢查是否為選項行
                if re.match(r'\s*[\(（][A-Da-d][\)）]', next_line):
                    options_text += ' ' + next_line
                elif options_text:
                    # 已經開始選項了，後續行也是選項的延續
                    options_text += ' ' + next_line
                else:
                    # 還是題幹的延續
                    stem += ' ' + next_line
                i += 1

            # 解析選項
            options = {}
            if options_text:
                opt_matches = INLINE_OPTIONS_PATTERN.findall(options_text)
                for label, text in opt_matches:
                    options[label.upper()] = normalize_text(text.strip())

            # 也嘗試從題幹末尾提取選項
            if not options:
                opt_matches = INLINE_OPTIONS_PATTERN.findall(stem)
                if opt_matches:
                    # 從題幹中移除選項部分
                    first_opt_pos = stem.find('(A)')
                    if first_opt_pos == -1:
                        first_opt_pos = stem.find('（A）')
                    if first_opt_pos > 0:
                        options_part = stem[first_opt_pos:]
                        stem = stem[:first_opt_pos].strip()
                        opt_matches = INLINE_OPTIONS_PATTERN.findall(options_part)
                        for label, text in opt_matches:
                            options[label.upper()] = normalize_text(text.strip())

            q = {
                'number': num,
                'type': 'choice',
                'stem': normalize_text(stem),
                'section': current_section,
            }
            if options:
                q['options'] = options
            questions.append(q)
            continue

        # 未識別的行，跳過
        i += 1

    return {
        'metadata': metadata,
        'notes': notes,
        'sections': sections,
        'questions': questions,
    }


# ===== Fallback: Y 座標間距偵測無編號申論題 =====
CN_NUMS = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
           '十一', '十二', '十三', '十四', '十五']

SCORE_PATTERN = re.compile(r'[（(]\s*\d+\s*分\s*[）)]')


def _collapse_spaced_cjk(text):
    """移除 CJK 字元間的多餘空格（PDF 排版造成的）"""
    # 例: "交 通 事 業" → "交通事業"（需多次替換直到穩定）
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
    return text


def _is_header_or_note(line):
    """結合 header/note 判斷，並處理 CJK 空格問題"""
    collapsed = _collapse_spaced_cjk(line)
    return is_header_line(collapsed) or is_note_line(collapsed)


def fallback_extract_essays(pdf_path):
    """
    Fallback: 用 Y 座標間距偵測無標準編號的申論題。
    適用於題目不以「一、」「二、」開頭的純申論考卷。
    """
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            all_lines = []  # [(y, text), ...]
            page_offset = 0
            for page in pdf.pages:
                words = page.extract_words(y_tolerance=3)
                if not words:
                    continue
                # 依 Y 座標分行
                current_words = [words[0]]
                for w in words[1:]:
                    if abs(w['top'] - current_words[-1]['top']) < 5:
                        current_words.append(w)
                    else:
                        text = ' '.join(cw['text'] for cw in current_words)
                        y = page_offset + current_words[0]['top']
                        all_lines.append((y, text))
                        current_words = [w]
                if current_words:
                    text = ' '.join(cw['text'] for cw in current_words)
                    y = page_offset + current_words[0]['top']
                    all_lines.append((y, text))
                page_offset += page.height
    except Exception:
        return []

    if not all_lines:
        return []

    # 過濾標頭/注意事項
    filtered = [(y, t) for y, t in all_lines if not _is_header_or_note(t)]
    if not filtered:
        return []

    # 計算行距中位數，設定段落門檻為 1.5 倍
    gaps = [filtered[i][0] - filtered[i - 1][0]
            for i in range(1, len(filtered))]
    if gaps:
        sorted_gaps = sorted(gaps)
        median_gap = sorted_gaps[len(sorted_gaps) // 2]
        threshold = max(median_gap * 1.5, 30)  # 至少 30
    else:
        threshold = 30

    # 依間距切割段落
    paragraphs = [[filtered[0][1]]]
    for i in range(1, len(filtered)):
        gap = filtered[i][0] - filtered[i - 1][0]
        if gap > threshold:
            paragraphs.append([])
        paragraphs[-1].append(filtered[i][1])

    # 每個含分數標記的段落視為一道申論題
    questions = []
    for para in paragraphs:
        stem = normalize_text('\n'.join(para))
        if stem and SCORE_PATTERN.search(stem):
            idx = len(questions)
            num_str = CN_NUMS[idx] if idx < len(CN_NUMS) else str(idx + 1)
            questions.append({
                'number': num_str,
                'type': 'essay',
                'stem': stem,
                'section': None,
            })

    return questions


def process_single_pdf(pdf_path, output_dir=None):
    """
    處理單一 PDF 檔案
    Args:
        pdf_path: PDF 檔案路徑
        output_dir: JSON 輸出目錄（None 則與 PDF 同目錄）
    Returns:
        dict: 解析結果
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"  找不到檔案: {pdf_path}")
        return None

    try:
        pages_text = extract_pdf_text(pdf_path)
    except Exception as e:
        print(f"  PDF 讀取失敗: {pdf_path.name} - {e}")
        return None

    if not pages_text:
        print(f"  PDF 無內容: {pdf_path.name}")
        return None

    result = parse_questions(pages_text)

    # Fallback: 若主解析器找不到題目，嘗試 Y 座標間距法
    if not result.get('questions') and pages_text:
        fallback_qs = fallback_extract_essays(pdf_path)
        if fallback_qs:
            result['questions'] = fallback_qs

    # 從目錄結構推斷年份、類科、科目
    parts = pdf_path.parts
    for i, part in enumerate(parts):
        if re.match(r'\d{3}年$', part):
            result['year'] = int(part.replace('年', ''))
        if i > 0 and any(cat in parts[i-1] for cat in [
            '行政警察學系', '外事警察學系', '刑事警察學系', '公共安全學系社安組',
            '犯罪防治學系預防組', '犯罪防治學系矯治組', '犯罪防治',
            '消防學系', '交通學系交通組', '交通學系電訊組', '交通警察',
            '資訊管理學系', '鑑識科學學系', '國境警察學系境管組',
            '水上警察學系', '法律學系', '行政管理學系'
        ]):
            result['category'] = parts[i-1]

    # 科目名稱取自父目錄
    result['subject'] = pdf_path.parent.name
    result['source_pdf'] = str(pdf_path)
    result['file_type'] = pdf_path.stem  # 試題/答案/更正答案

    # 輸出 JSON
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = pdf_path.parent

    os.makedirs(out_dir, exist_ok=True)
    json_path = out_dir / f"{pdf_path.stem}.json"

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def process_directory(input_dir, output_dir=None):
    """
    遞迴處理目錄下所有 PDF
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        print(f"目錄不存在: {input_dir}")
        return

    pdf_files = sorted(input_dir.rglob('試題.pdf'))
    if not pdf_files:
        pdf_files = sorted(input_dir.rglob('*.pdf'))

    print(f"找到 {len(pdf_files)} 個 PDF 檔案")
    print("-" * 60)

    stats = {
        'total': len(pdf_files),
        'success': 0,
        'failed': 0,
        'total_questions': 0,
        'choice_questions': 0,
        'essay_questions': 0,
    }

    for pdf_path in pdf_files:
        # 計算相對路徑
        try:
            rel = pdf_path.relative_to(input_dir)
        except ValueError:
            rel = pdf_path.name

        # 決定輸出目錄
        if output_dir:
            out = Path(output_dir) / rel.parent
        else:
            out = None

        result = process_single_pdf(pdf_path, out)
        if result and result.get('questions'):
            q_count = len(result['questions'])
            choice_count = sum(1 for q in result['questions'] if q['type'] == 'choice')
            essay_count = sum(1 for q in result['questions'] if q['type'] == 'essay')

            stats['success'] += 1
            stats['total_questions'] += q_count
            stats['choice_questions'] += choice_count
            stats['essay_questions'] += essay_count

            print(f"  {rel}: {q_count} 題 ({choice_count} 選擇 + {essay_count} 申論)")
        else:
            stats['failed'] += 1
            print(f"  {rel}: 解析失敗或無題目")

    # 統計報告
    print(f"\n{'=' * 60}")
    print("提取完成！")
    print(f"{'=' * 60}")
    print(f"處理: {stats['total']} 個 PDF")
    print(f"成功: {stats['success']} 個")
    print(f"失敗: {stats['failed']} 個")
    print(f"總題數: {stats['total_questions']}")
    print(f"  選擇題: {stats['choice_questions']}")
    print(f"  申論題: {stats['essay_questions']}")

    # 儲存統計
    if output_dir:
        stats_path = Path(output_dir) / 'extraction_stats.json'
    else:
        stats_path = input_dir / 'extraction_stats.json'

    stats['timestamp'] = datetime.now().isoformat()
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"統計報告: {stats_path}")


def main():
    parser = argparse.ArgumentParser(description='PDF → 結構化題目提取器')
    parser.add_argument('--input', '-i', type=str,
                        default=os.path.join(os.path.dirname(__file__), '考古題庫'),
                        help='輸入路徑（PDF 檔案或目錄）')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='輸出目錄（預設: 與輸入同目錄）')
    args = parser.parse_args()

    input_path = Path(args.input)

    print("=" * 60)
    print("  PDF → 結構化題目提取器")
    print("=" * 60)

    if input_path.is_file() and input_path.suffix.lower() == '.pdf':
        result = process_single_pdf(input_path, args.output)
        if result:
            q_count = len(result.get('questions', []))
            print(f"\n提取完成: {q_count} 題")
    elif input_path.is_dir():
        process_directory(input_path, args.output)
    else:
        print(f"無效的輸入路徑: {input_path}")


if __name__ == "__main__":
    main()
