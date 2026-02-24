# -*- coding: utf-8 -*-
"""
移民特考 PDF → JSON 轉換腳本
從 移民特考PDF/ 目錄讀取 PDF，解析為結構化 JSON 並輸出到 考古題庫/移民特考/

用法:
  python process_immigration.py
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime

# 重用現有的 PDF 解析器
from pdf_to_questions import (
    extract_pdf_text, parse_questions, fallback_extract_essays,
    normalize_text, SCORE_PATTERN
)

# 考選部 PDF 使用私有 Unicode 區域字元作為選項標記
PUA_OPTION_MAP = {
    '\ue18c': '(A)', '\ue18d': '(B)', '\ue18e': '(C)', '\ue18f': '(D)',
}
# 其他 PUA 字元（注意事項圓點等）→ 移除
PUA_STRIP = {'\ue129', '\ue12a', '\ue12b', '\ue0c6', '\ue0c7'}

def preprocess_immigration_text(pages_text):
    """將考選部 PDF 的私有 Unicode 選項標記轉換為標準 (A)(B)(C)(D) 格式"""
    result = []
    for page in pages_text:
        for old, new in PUA_OPTION_MAP.items():
            page = page.replace(old, new)
        for ch in PUA_STRIP:
            page = page.replace(ch, '')
        result.append(page)
    return result


PDF_DIR = Path(__file__).parent / '移民特考PDF'
OUTPUT_DIR = Path(__file__).parent / '考古題庫' / '移民特考'

# 跳過重複的 三等_英文組（與 三等 完全相同）
SKIP_LEVELS = {'三等_英文組'}

# 等級排序
LEVEL_ORDER = {'二等': 0, '三等': 1, '四等': 2}


def shorten_subject(name):
    """縮短過長的科目名稱，去掉括號內的冗長子法條列"""
    # 保留括號前的主名稱，若括號內容太長則縮短
    match = re.match(r'^(.+?)\s*[（(](.+)[）)]$', name)
    if match:
        main = match.group(1)
        detail = match.group(2)
        # 若括號內有超過 3 個頓號，代表列舉了很多法條
        if detail.count('、') > 3:
            # 取前兩項 + "等"
            items = detail.split('、')
            short = '、'.join(items[:2]) + '等'
            return f'{main}({short})'
    return name


def clean_bogus_questions(questions):
    """清除被錯誤解析為選擇題的假題目（年份/代號數字）"""
    cleaned = []
    for q in questions:
        if q.get('type') == 'choice' and isinstance(q.get('number'), int):
            # 無選項且題號異常高 → 假題目
            if not q.get('options') and q['number'] > 80:
                continue
        cleaned.append(q)
    return cleaned


# 用於從題幹中提取內嵌選項
INLINE_OPT_RE = re.compile(
    r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=\s*[\(（][A-Da-d][\)）]|\s*$)'
)


def fix_missing_options(questions):
    """修復選項未被提取的選擇題（從題幹中提取內嵌選項）"""
    for q in questions:
        if q.get('type') != 'choice':
            continue
        if q.get('options') and len(q['options']) >= 2:
            continue

        stem = q.get('stem', '')
        matches = INLINE_OPT_RE.findall(stem)
        if len(matches) >= 2:
            options = {}
            for label, text in matches:
                options[label.upper()] = text.strip()
            # 從題幹移除選項部分
            first_opt = stem.find('(A)')
            if first_opt == -1:
                first_opt = stem.find('（A）')
            if first_opt >= 0:
                remaining = stem[:first_opt].strip()
                if remaining:
                    q['stem'] = remaining
                else:
                    # 整個題幹就是選項（閱讀測驗填空）→ 保留空題幹
                    q['stem'] = ''
            q['options'] = options
    return questions


def merge_answer_data(questions, answer_pdf_path):
    """從答案 PDF 中提取答案並合併到題目中"""
    try:
        pages_text = extract_pdf_text(str(answer_pdf_path))
    except Exception:
        return questions

    if not pages_text:
        return questions

    full_text = '\n'.join(pages_text)
    answer_map = {}

    # 模式1: 表格式 — "題號 第1題 第2題 ..." + "答案 A D B ..."
    lines = full_text.split('\n')
    for i, line in enumerate(lines):
        if re.match(r'\s*題號\s+第\d+題', line):
            # 提取本行所有題號
            nums = [int(m.group(1)) for m in re.finditer(r'第(\d+)題', line)]
            # 找到緊接的答案行
            for j in range(i + 1, min(i + 3, len(lines))):
                ans_line = lines[j].strip()
                if ans_line.startswith('答案'):
                    answers = re.findall(r'[A-Ea-e]', ans_line)
                    for k, num in enumerate(nums):
                        if k < len(answers):
                            answer_map[num] = answers[k].upper()
                    break

    # 模式2: "1.A" 或 "1 A" 或 "1.(A)" 等（fallback）
    if not answer_map:
        for m in re.finditer(r'(\d{1,3})\s*[\.、．]?\s*[\(（]?([A-Ea-e])[\)）]?', full_text):
            num = int(m.group(1))
            ans = m.group(2).upper()
            answer_map[num] = ans

    # 模式3: 更正答案 "第X題答案更正為Y"
    for m in re.finditer(r'第\s*(\d+)\s*題.*?(?:更正為|答案[為是])\s*[\(（]?([A-Ea-e])[\)）]?', full_text):
        num = int(m.group(1))
        ans = m.group(2).upper()
        answer_map[num] = ans

    if not answer_map:
        return questions

    # 合併答案
    for q in questions:
        if q.get('type') == 'choice' and isinstance(q.get('number'), int):
            if q['number'] in answer_map:
                q['answer'] = answer_map[q['number']]

    return questions


def process_immigration_pdfs():
    """處理所有移民特考 PDF"""
    if not PDF_DIR.exists():
        print(f"找不到目錄: {PDF_DIR}")
        return

    stats = {
        'total': 0, 'success': 0, 'failed': 0,
        'total_questions': 0, 'choice_questions': 0, 'essay_questions': 0,
        'skipped_duplicate': 0,
    }

    seen_hashes = set()

    for year_dir in sorted(PDF_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        year_match = re.match(r'(\d{3})年$', year_dir.name)
        if not year_match:
            continue
        year = int(year_match.group(1))

        for level_dir in sorted(year_dir.iterdir()):
            if not level_dir.is_dir():
                continue
            level = level_dir.name

            if level in SKIP_LEVELS:
                continue

            for subject_dir in sorted(level_dir.iterdir()):
                if not subject_dir.is_dir():
                    continue

                pdf_path = subject_dir / '試題.pdf'
                if not pdf_path.exists():
                    continue

                # 跳過重複 PDF（用 hash 檢測）
                with open(pdf_path, 'rb') as f:
                    pdf_hash = hashlib.md5(f.read()).hexdigest()

                cache_key = f"{year}-{pdf_hash}"
                if cache_key in seen_hashes:
                    stats['skipped_duplicate'] += 1
                    continue
                seen_hashes.add(cache_key)

                stats['total'] += 1

                raw_subject = subject_dir.name
                subject_display = f"[{level}] {shorten_subject(raw_subject)}"

                # 輸出目錄
                out_dir = OUTPUT_DIR / f"{year}年" / subject_display
                os.makedirs(out_dir, exist_ok=True)

                try:
                    pages_text = extract_pdf_text(str(pdf_path))
                except Exception as e:
                    print(f"  [失敗] {year}年/{level}/{raw_subject}: PDF 讀取失敗 - {e}")
                    stats['failed'] += 1
                    continue

                if not pages_text:
                    print(f"  [失敗] {year}年/{level}/{raw_subject}: PDF 無內容")
                    stats['failed'] += 1
                    continue

                # 將私有 Unicode 選項標記轉換為標準格式
                pages_text = preprocess_immigration_text(pages_text)

                result = parse_questions(pages_text)

                # Fallback
                if not result.get('questions'):
                    fallback_qs = fallback_extract_essays(pdf_path)
                    if fallback_qs:
                        result['questions'] = fallback_qs

                if not result.get('questions'):
                    print(f"  [失敗] {year}年/{level}/{raw_subject}: 解析出 0 題")
                    stats['failed'] += 1
                    # 仍然輸出空 JSON 以便追蹤
                    result['questions'] = []

                # 清除假題目 + 修復缺失選項 + 重分類
                result['questions'] = clean_bogus_questions(result['questions'])
                result['questions'] = fix_missing_options(result['questions'])
                # 選擇題無選項→降級為申論題（避免網站顯示空選項）
                for q in result['questions']:
                    if (q.get('type') == 'choice' and
                            (not q.get('options') or len(q.get('options', {})) < 2)):
                        q['type'] = 'essay'

                # 嘗試合併答案
                answer_pdf = subject_dir / '答案.pdf'
                if answer_pdf.exists():
                    result['questions'] = merge_answer_data(
                        result['questions'], answer_pdf
                    )

                # 更正答案
                correction_pdf = subject_dir / '更正答案.pdf'
                if correction_pdf.exists():
                    result['questions'] = merge_answer_data(
                        result['questions'], correction_pdf
                    )

                # 補充 metadata
                result['year'] = year
                result['category'] = '移民特考'
                result['subject'] = subject_display
                result['level'] = level
                result['original_subject'] = raw_subject
                result['source_pdf'] = str(pdf_path)
                result['file_type'] = '試題'

                q_count = len(result['questions'])
                choice_count = sum(1 for q in result['questions'] if q.get('type') == 'choice')
                essay_count = sum(1 for q in result['questions'] if q.get('type') == 'essay')
                result['total_questions'] = q_count

                # 輸出 JSON
                json_path = out_dir / '試題.json'
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                stats['success'] += 1
                stats['total_questions'] += q_count
                stats['choice_questions'] += choice_count
                stats['essay_questions'] += essay_count

                answered = sum(1 for q in result['questions']
                             if q.get('type') == 'choice' and q.get('answer'))
                print(f"  {year}年/{level}/{shorten_subject(raw_subject)}: "
                      f"{q_count} 題 ({choice_count} 選擇/{essay_count} 申論) "
                      f"[答案: {answered}/{choice_count}]")

    # 統計報告
    print(f"\n{'=' * 60}")
    print("移民特考 PDF → JSON 轉換完成！")
    print(f"{'=' * 60}")
    print(f"處理: {stats['total']} 個 PDF")
    print(f"成功: {stats['success']} 個")
    print(f"失敗: {stats['failed']} 個")
    print(f"跳過重複: {stats['skipped_duplicate']} 個")
    print(f"總題數: {stats['total_questions']}")
    print(f"  選擇題: {stats['choice_questions']}")
    print(f"  申論題: {stats['essay_questions']}")

    stats['timestamp'] = datetime.now().isoformat()
    stats_path = OUTPUT_DIR / 'extraction_stats.json'
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"統計報告: {stats_path}")

    return stats


if __name__ == '__main__':
    process_immigration_pdfs()
