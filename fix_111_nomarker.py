# -*- coding: utf-8 -*-
"""
修復 111年國境警察學系移民組 PDF 無 ABCD 標記問題

這些 PDF 的選項標記 (A)(B)(C)(D) 使用了 pdfplumber 無法提取的特殊字型編碼。
本腳本：
1. 使用字元級位置資料從 PDF 重新提取選項（2x2 格式：左欄=A/C，右欄=B/D）
2. 對無法提取的選項，從題幹嵌入文字中啟發式拆分
3. 所有阿拉伯數字題改為 choice 類型
4. 合併答案 PDF

用法:
  python fix_111_nomarker.py          # 預覽模式
  python fix_111_nomarker.py --apply  # 實際修改
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import pdfplumber

BASE = Path(__file__).parent
JSON_BASE = BASE / '考古題庫' / '國境警察學系移民組' / '111年'
PDF_BASE = BASE / '國境警察學系移民組PDF' / '111年'

# 左右欄分界 x 座標（根據實際 PDF 分析）
COL_SPLIT_X = 280

# 題幹起始 x 座標
STEM_X = 69.5
# 選項縮排 x 座標
OPT_INDENT_X = 83


def _normalize_brackets(s):
    """統一全形/半形括號以便匹配"""
    return s.replace('（', '(').replace('）', ')').replace('，', ',')


def find_pdf_for_json(json_dir_name):
    """根據 JSON 目錄名找到對應的 PDF 路徑"""
    # JSON 目錄格式: "[等級] 科目名"
    m = re.match(r'\[(.+?)\]\s+(.+)', json_dir_name)
    if not m:
        return None, None
    level = m.group(1)
    subj_name = m.group(2)

    level_dir = PDF_BASE / level
    if not level_dir.exists():
        return None, None

    # 正規化後匹配
    norm_subj = _normalize_brackets(subj_name)

    for subj_dir in level_dir.iterdir():
        if not subj_dir.is_dir():
            continue
        trial_pdf = subj_dir / '試題.pdf'
        answer_pdf = subj_dir / '答案.pdf'
        if trial_pdf.exists():
            norm_pdf = _normalize_brackets(subj_dir.name)
            # 前 10 字元匹配（忽略括號差異）
            if norm_pdf[:10] in norm_subj or norm_subj[:10] in norm_pdf:
                return trial_pdf, answer_pdf if answer_pdf.exists() else None

    return None, None


def extract_chars_by_page(pdf_path):
    """從 PDF 提取所有字元的位置資訊"""
    all_chars = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        y_offset = 0
        for page in pdf.pages:
            for c in page.chars:
                all_chars.append({
                    'x0': c['x0'],
                    'top': c['top'] + y_offset,
                    'text': c['text'],
                    'font': c.get('fontname', ''),
                })
            y_offset += page.height
    return all_chars


def group_chars_to_lines(all_chars, y_tolerance=2.0):
    """將字元按 y 座標分組為行"""
    if not all_chars:
        return {}

    sorted_chars = sorted(all_chars, key=lambda c: c['top'])
    lines = {}
    current_y = sorted_chars[0]['top']
    current_group = [sorted_chars[0]]

    for c in sorted_chars[1:]:
        if abs(c['top'] - current_y) <= y_tolerance:
            current_group.append(c)
        else:
            avg_y = sum(ch['top'] for ch in current_group) / len(current_group)
            lines[avg_y] = sorted(current_group, key=lambda ch: ch['x0'])
            current_y = c['top']
            current_group = [c]

    if current_group:
        avg_y = sum(ch['top'] for ch in current_group) / len(current_group)
        lines[avg_y] = sorted(current_group, key=lambda ch: ch['x0'])

    return lines


def find_question_boundaries(lines):
    """從行資料中找出每題的 y 座標邊界"""
    q_starts = {}  # q_num -> y_position

    for y in sorted(lines.keys()):
        chars = lines[y]
        # 找行首的數字字元（x < 60，題號位置）
        left_digits = [c for c in chars if c['x0'] < 60 and c['text'].isdigit()]
        if left_digits:
            num_str = ''.join(c['text'] for c in left_digits)
            if num_str.isdigit():
                num = int(num_str)
                if 1 <= num <= 80 and num not in q_starts:
                    q_starts[num] = y

    return q_starts


def extract_options_from_chars(lines, q_start_y, q_end_y):
    """使用字元位置從兩欄格式提取 ABCD 選項"""
    # 找出題幹結尾（最後一行有 x≈69 起始字元的行）
    stem_end_y = q_start_y
    for y in sorted(lines.keys()):
        if q_start_y <= y < q_end_y:
            chars = lines[y]
            has_stem_char = any(65 <= c['x0'] <= 75 for c in chars if c['text'].strip())
            if has_stem_char:
                stem_end_y = y

    # 在題幹之後、下一題之前的區域找選項行
    option_rows = []  # [(y, left_text, right_text)]

    for y in sorted(lines.keys()):
        if y <= stem_end_y + 5 or y >= q_end_y - 5:
            continue

        chars = lines[y]
        non_space = [c for c in chars if c['text'].strip()]
        if not non_space:
            continue

        # 按左右欄分組
        left_chars = [c for c in non_space if c['x0'] < COL_SPLIT_X]
        right_chars = [c for c in non_space if c['x0'] >= COL_SPLIT_X]

        left_text = ''.join(c['text'] for c in sorted(left_chars, key=lambda c: c['x0'])).strip()
        right_text = ''.join(c['text'] for c in sorted(right_chars, key=lambda c: c['x0'])).strip()

        if left_text or right_text:
            option_rows.append((y, left_text, right_text))

    if not option_rows:
        return None

    # 合併相鄰行（同一選項可能跨兩行，數字和中文分開提取）
    merged_rows = []
    i = 0
    while i < len(option_rows):
        y1, l1, r1 = option_rows[i]
        # 檢查下一行是否緊鄰（y 差 < 5，通常是數字和中文分開的行）
        if i + 1 < len(option_rows):
            y2, l2, r2 = option_rows[i + 1]
            if abs(y2 - y1) < 5:
                # 合併：嘗試智能合併數字和中文
                merged_l = _merge_text_fragments(l1, l2)
                merged_r = _merge_text_fragments(r1, r2)
                merged_rows.append((y1, merged_l, merged_r))
                i += 2
                continue
        merged_rows.append((y1, l1, r1))
        i += 1

    if not merged_rows:
        return None

    # 2x2 佈局: 第1行=A/B，第2行=C/D
    options = {}
    if len(merged_rows) >= 1:
        if merged_rows[0][1]:
            options['A'] = merged_rows[0][1]
        if merged_rows[0][2]:
            options['B'] = merged_rows[0][2]
    if len(merged_rows) >= 2:
        if merged_rows[1][1]:
            options['C'] = merged_rows[1][1]
        if merged_rows[1][2]:
            options['D'] = merged_rows[1][2]

    # 也處理 4x1 佈局（4 行各一個選項）
    if len(merged_rows) >= 4 and not any(r[2] for r in merged_rows):
        options = {}
        labels = ['A', 'B', 'C', 'D']
        for idx, (_, text, _) in enumerate(merged_rows[:4]):
            if text:
                options[labels[idx]] = text

    return options if len(options) >= 2 else None


def _merge_text_fragments(t1, t2):
    """合併同一選項的文字片段（數字 + 中文在不同 y 行提取）"""
    if not t1:
        return t2
    if not t2:
        return t1

    # 如果一個全是數字/空格、另一個有中文 → 數字在前
    t1_is_num = all(c.isdigit() or c in ' .' for c in t1)
    t2_is_num = all(c.isdigit() or c in ' .' for c in t2)

    if t1_is_num and not t2_is_num:
        return t1 + t2
    elif t2_is_num and not t1_is_num:
        return t2 + t1
    else:
        return t1 + t2


def split_options_from_stem(stem):
    """從題幹中啟發式分離嵌入的選項文字"""
    if not stem:
        return stem, None

    # 找最後一個問號
    last_q = max(stem.rfind('？'), stem.rfind('?'))
    if last_q < 0 or last_q >= len(stem) - 3:
        return stem, None

    question_part = stem[:last_q + 1].strip()
    option_part = stem[last_q + 1:].strip()

    if not option_part or len(option_part) < 4:
        return stem, None

    # 嘗試拆分選項
    # 模式1: 選項之間有明顯間距（多個空格）
    segments = re.split(r'\s{2,}', option_part)
    if len(segments) >= 4:
        options = {}
        labels = ['A', 'B', 'C', 'D']
        for i, seg in enumerate(segments[:4]):
            if seg.strip():
                options[labels[i]] = seg.strip()
        if len(options) >= 3:
            return question_part, options

    # 模式2: 4 個短選項用空格分開（如 "1年 2年 3年 5年"）
    segments = option_part.split()
    if 4 <= len(segments) <= 8:
        # 看是否每個片段長度相近（典型的短選項）
        lens = [len(s) for s in segments]
        if max(lens) - min(lens) <= 5 and max(lens) <= 20:
            if len(segments) == 4:
                return question_part, {
                    'A': segments[0], 'B': segments[1],
                    'C': segments[2], 'D': segments[3]
                }
            # 6-8 段：可能是 2x2 佈局的 2 段合併
            # 嘗試兩兩合併
            if len(segments) == 8:
                return question_part, {
                    'A': ' '.join(segments[0:2]),
                    'B': ' '.join(segments[2:4]),
                    'C': ' '.join(segments[4:6]),
                    'D': ' '.join(segments[6:8]),
                }

    return stem, None


def extract_answers_from_pdf(answer_pdf_path):
    """從答案 PDF 提取答案"""
    try:
        with pdfplumber.open(str(answer_pdf_path)) as pdf:
            full_text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
    except Exception:
        return {}

    if not full_text:
        return {}

    answer_map = {}

    # 模式1: 表格式
    lines = full_text.split('\n')
    for i, line in enumerate(lines):
        if re.match(r'\s*題號\s+第\d+題', line):
            nums = [int(m.group(1)) for m in re.finditer(r'第(\d+)題', line)]
            for j in range(i + 1, min(i + 3, len(lines))):
                ans_line = lines[j].strip()
                if ans_line.startswith('答案'):
                    answers = re.findall(r'[A-Ea-e]', ans_line)
                    for k, num in enumerate(nums):
                        if k < len(answers):
                            answer_map[num] = answers[k].upper()
                    break

    # 模式2: "1.A" 等
    if not answer_map:
        for m in re.finditer(r'(\d{1,3})\s*[\.、．]?\s*[\(（]?([A-Ea-e])[\)）]?', full_text):
            num = int(m.group(1))
            ans = m.group(2).upper()
            if 1 <= num <= 80:
                answer_map[num] = ans

    # 模式3: 更正答案
    for m in re.finditer(r'第\s*(\d+)\s*題.*?(?:更正為|答案[為是])\s*[\(（]?([A-Ea-e])[\)）]?', full_text):
        num = int(m.group(1))
        ans = m.group(2).upper()
        answer_map[num] = ans

    return answer_map


def is_genuine_essay_subject(json_dir_name):
    """判斷是否為真正的申論題科目（二等的專業科目通常是純申論）"""
    if '[二等]' in json_dir_name:
        # 二等的入出國及移民法規、國土安全、移民情勢、行政法研究 → 純申論
        if any(kw in json_dir_name for kw in ['入出國', '國土安全', '移民情勢', '行政法研究']):
            return True
    return False


def fix_subject(json_dir, apply=False):
    """修復單一科目的 JSON 資料"""
    json_path = json_dir / '試題.json'
    if not json_path.exists():
        return None

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    questions = data.get('questions', [])
    if not questions:
        return None

    dir_name = json_dir.name

    # 跳過真正的申論題科目
    if is_genuine_essay_subject(dir_name):
        return None

    # 檢查是否有問題（0 選擇題 + 大量申論題）
    choice_count = sum(1 for q in questions if q.get('type') == 'choice')
    essay_count = sum(1 for q in questions if q.get('type') == 'essay')

    if choice_count > 0:
        return None  # 已有選擇題，跳過

    # 區分真申論（中文數字）和假申論（阿拉伯數字）
    arabic_qs = [q for q in questions if isinstance(q.get('number'), int)]
    chinese_qs = [q for q in questions if isinstance(q.get('number'), str)]

    if not arabic_qs:
        return None  # 全是中文數字 → 真申論

    # 找對應的 PDF
    trial_pdf, answer_pdf = find_pdf_for_json(dir_name)

    # 從 PDF 提取字元位置資料
    char_options = {}  # q_num -> options dict
    if trial_pdf and trial_pdf.exists():
        try:
            all_chars = extract_chars_by_page(trial_pdf)
            lines = group_chars_to_lines(all_chars)
            q_starts = find_question_boundaries(lines)

            q_nums = sorted(q_starts.keys())
            for i, qn in enumerate(q_nums):
                q_end_y = q_starts[q_nums[i + 1]] if i + 1 < len(q_nums) else q_starts[qn] + 200
                opts = extract_options_from_chars(lines, q_starts[qn], q_end_y)
                if opts:
                    char_options[qn] = opts
        except Exception as e:
            print(f"    PDF 字元提取失敗: {e}")

    # 提取答案
    answer_map = {}
    if answer_pdf:
        answer_map = extract_answers_from_pdf(answer_pdf)

    # 也檢查更正答案
    if trial_pdf:
        correction_pdf = trial_pdf.parent / '更正答案.pdf'
        if correction_pdf.exists():
            corrections = extract_answers_from_pdf(correction_pdf)
            answer_map.update(corrections)

    # 修復每一題
    fixes = {'type_changed': 0, 'opts_from_chars': 0, 'opts_from_stem': 0,
             'answers_merged': 0, 'stem_cleaned': 0}

    for q in questions:
        if not isinstance(q.get('number'), int):
            continue  # 跳過中文編號的真申論題

        qn = q['number']

        # 1. 改為選擇題
        if q.get('type') != 'choice':
            q['type'] = 'choice'
            fixes['type_changed'] += 1

        # 2. 嘗試從字元位置提取選項
        if qn in char_options and (not q.get('options') or len(q.get('options', {})) < 2):
            q['options'] = char_options[qn]
            fixes['opts_from_chars'] += 1
        elif not q.get('options') or len(q.get('options', {})) < 2:
            # 3. 嘗試從題幹拆分選項
            new_stem, opts = split_options_from_stem(q.get('stem', ''))
            if opts and len(opts) >= 2:
                q['stem'] = new_stem
                q['options'] = opts
                fixes['opts_from_stem'] += 1
                fixes['stem_cleaned'] += 1

        # 4. 合併答案
        if qn in answer_map and not q.get('answer'):
            q['answer'] = answer_map[qn]
            fixes['answers_merged'] += 1

    if fixes['type_changed'] == 0:
        return None

    # 更新統計
    choice_new = sum(1 for q in questions if q.get('type') == 'choice')
    essay_new = sum(1 for q in questions if q.get('type') == 'essay')
    data['total_questions'] = len(questions)

    result = {
        'dir': dir_name,
        'fixes': fixes,
        'before': f'{choice_count}選/{essay_count}申',
        'after': f'{choice_new}選/{essay_new}申',
    }

    if apply:
        # 備份
        backup = json_path.with_suffix('.json.bak_111')
        if not backup.exists():
            shutil.copy2(json_path, backup)

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return result


def main():
    apply = '--apply' in sys.argv

    if not JSON_BASE.exists():
        print(f"找不到目錄: {JSON_BASE}")
        return

    print(f"{'=' * 60}")
    print(f"修復 111年國境警察學系移民組無標記選擇題")
    print(f"模式: {'實際修改' if apply else '預覽（加 --apply 執行）'}")
    print(f"{'=' * 60}\n")

    total_fixes = {'type_changed': 0, 'opts_from_chars': 0, 'opts_from_stem': 0,
                   'answers_merged': 0, 'stem_cleaned': 0}
    fixed_subjects = 0

    for subj_dir in sorted(JSON_BASE.iterdir()):
        if not subj_dir.is_dir():
            continue

        result = fix_subject(subj_dir, apply=apply)
        if result:
            fixed_subjects += 1
            fixes = result['fixes']
            for k in total_fixes:
                total_fixes[k] += fixes[k]

            print(f"  {result['dir'][:60]}")
            print(f"    {result['before']} → {result['after']}")
            print(f"    類型修正: {fixes['type_changed']}, "
                  f"字元提取選項: {fixes['opts_from_chars']}, "
                  f"題幹拆分選項: {fixes['opts_from_stem']}, "
                  f"答案合併: {fixes['answers_merged']}")
            print()

    print(f"\n{'=' * 60}")
    print(f"修復總結")
    print(f"{'=' * 60}")
    print(f"修復科目數: {fixed_subjects}")
    print(f"類型修正: {total_fixes['type_changed']} 題")
    print(f"字元提取選項: {total_fixes['opts_from_chars']} 題")
    print(f"題幹拆分選項: {total_fixes['opts_from_stem']} 題")
    print(f"答案合併: {total_fixes['answers_merged']} 題")
    print(f"題幹清理: {total_fixes['stem_cleaned']} 題")

    if not apply and fixed_subjects > 0:
        print(f"\n加 --apply 參數以實際執行修改")


if __name__ == '__main__':
    main()
