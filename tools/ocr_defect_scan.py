#!/usr/bin/env python3
"""
OCR 瑕疵全面掃描腳本
掃描所有 909 個試題 JSON 的文字內容，偵測 9 類 OCR 常見瑕疵。

瑕疵類型：
  1. 英文單字被拆開（如 "ti on", "si on"）
  2. 五位數代號汙染（如 "arrest51250"）
  3. Unicode replacement character (\ufffd)
  4. 全形/半形括號混用
  5. 連續空白（>2個）
  6. 中文亂碼特徵
  7. 數學符號被破壞
  8. 選項標記缺失
  9. 頁首/頁碼殘留
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(r"C:\Users\User\Desktop\考古題下載")
EXAM_DIR = BASE_DIR / "考古題庫"
REPORT_DIR = BASE_DIR / "reports"

# ============================================================
# 瑕疵偵測器
# ============================================================

class DefectDetector:
    """OCR 瑕疵偵測器"""

    def __init__(self):
        self.results = defaultdict(list)  # {defect_type: [(location, text_snippet, detail), ...]}
        self.counts = defaultdict(int)

    # --- 1. 英文單字被拆開 ---
    def check_split_words(self, text, location):
        """偵測英文單字被 OCR 空格拆開的模式"""
        patterns = [
            # -tion 被拆開: Xti on
            (r'[a-zA-Z]ti\s+on\b', 'tion 被拆開'),
            # -sion 被拆開: Xsi on
            (r'[a-zA-Z]si\s+on\b', 'sion 被拆開'),
            # -ment 被拆開: X ment (排除常見片語如 "in ment")
            (r'[a-zA-Z]\s+ment\b(?!\s+(?:of|in|on|is|are|was|were|for|and|the|to|a))', 'ment 被拆開'),
            # -ness 被拆開
            (r'[a-zA-Z]\s+ness\b', 'ness 被拆開'),
            # -able/-ible 被拆開 (排除 "be able", "are able", "is able" 等正常用法)
            (r'[a-zA-Z]{3,}\s+able\b(?!\s+to)', 'able 被拆開'),
            (r'[a-zA-Z]{3,}\s+ible\b', 'ible 被拆開'),
            # -ing 被拆開 (小心排除 "some thing" 等正常片語)
            (r'[a-zA-Z]{3,}i\s+ng\b', 'ing 被拆開'),
            # -ence/-ance 被拆開
            (r'[a-zA-Z]\s+ence\b', 'ence 被拆開'),
            (r'[a-zA-Z]\s+ance\b', 'ance 被拆開'),
            # 常見單字被拆: th e, th at, wh en, f or, c an 等
            (r'\bth\s+e\b', 'the 被拆開'),
            (r'\bth\s+at\b', 'that 被拆開'),
            (r'\bth\s+is\b', 'this 被拆開'),
            (r'\bth\s+an\b', 'than 被拆開'),
            (r'\bwh\s+en\b', 'when 被拆開'),
            (r'\bwh\s+ich\b', 'which 被拆開'),
            (r'\bwh\s+at\b', 'what 被拆開'),
            (r'\bf\s+or\b', 'for 被拆開'),
            (r'\bc\s+an\b', 'can 被拆開'),
            (r'\bw\s+ith\b', 'with 被拆開'),
            # -or 被拆開: monit or, indicat or (排除 "prevent or X", "exit or X" 等正常用法)
            (r'[a-zA-Z]{3,}t\s+or\b(?!\s+[a-zA-Z])', 'tor 被拆開'),
            # -er 被拆開: oth er, togeth er
            (r'[a-zA-Z]{3,}th\s+er\b', 'ther 被拆開'),
            # hum an, wom an
            (r'\b[hHwW]um\s+an\b', 'human/woman 被拆開'),
            (r'\b[wW]om\s+an\b', 'woman 被拆開'),
            # softw are
            (r'\bsoftw\s+are\b', 'software 被拆開'),
            # Taiw an
            (r'\bTaiw\s+an\b', 'Taiwan 被拆開'),
        ]
        for pat, desc in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                snippet = text[max(0, m.start()-20):m.end()+20]
                self.results['1_split_words'].append((location, snippet.strip(), desc))
                self.counts['1_split_words'] += 1

    # --- 2. 五位數代號汙染 ---
    def check_code_contamination(self, text, location):
        """偵測考卷五位數代號黏在文字中"""
        # 模式: 英文/中文字後面直接接五位數字
        for m in re.finditer(r'([a-zA-Z\u4e00-\u9fff])(\d{5})(?!\d)(?!年|月|日|人|元|分|時|題|頁|條|款|項|號|次|萬|千|百|億|個|位|筆|件|組)', text):
            num = m.group(2)
            n = int(num)
            # 排除合理的數字: 年份如 2024, 法規條號等
            if 1900 <= n <= 2030:
                continue
            # 排除在 metadata 區域的代號
            if '代號' in text[max(0, m.start()-10):m.start()]:
                continue
            # 排除 ISO 標準編號（如 ISO27110, ISO27043）
            before_ctx = text[max(0, m.start()-5):m.start()+1]
            if re.search(r'ISO[/\s]?(?:IEC)?', before_ctx, re.IGNORECASE):
                continue
            snippet = text[max(0, m.start()-15):m.end()+15]
            self.results['2_code_contamination'].append((location, snippet.strip(), f'五位數代號: {num}'))
            self.counts['2_code_contamination'] += 1

        # 模式: 五位數+、+五位數 (連續代號)
        for m in re.finditer(r'\d{5}、\d{5}', text):
            snippet = text[max(0, m.start()-15):m.end()+15]
            # 排除元資料
            if '代號' in text[max(0, m.start()-20):m.start()]:
                continue
            self.results['2_code_contamination'].append((location, snippet.strip(), '連續代號格式'))
            self.counts['2_code_contamination'] += 1

    # --- 3. Unicode replacement character ---
    def check_replacement_char(self, text, location):
        """偵測 Unicode replacement character \ufffd"""
        for m in re.finditer('\ufffd', text):
            snippet = text[max(0, m.start()-20):m.end()+20]
            self.results['3_replacement_char'].append((location, snippet.strip(), 'Unicode \ufffd'))
            self.counts['3_replacement_char'] += 1

    # --- 4. 全形/半形括號混用 ---
    def check_bracket_mixing(self, text, location):
        """偵測同一題中全形/半形括號混用"""
        has_half = bool(re.search(r'\([A-Da-d]\)', text))
        has_full = bool(re.search(r'（[A-Da-dＡＢＣＤ]）', text))
        if has_half and has_full:
            # 找出混用的例子
            half_examples = re.findall(r'\([A-Da-d]\)', text)[:3]
            full_examples = re.findall(r'（[A-Da-dＡＢＣＤ]）', text)[:3]
            detail = f'半形: {half_examples}, 全形: {full_examples}'
            self.results['4_bracket_mixing'].append((location, text[:80], detail))
            self.counts['4_bracket_mixing'] += 1

    # --- 5. 連續空白 ---
    def check_consecutive_spaces(self, text, location):
        """偵測超過 2 個連續空白"""
        for m in re.finditer(r' {3,}', text):
            # 排除明顯的排版空白（行首）和填空題底線
            before = text[max(0, m.start()-5):m.start()]
            after = text[m.end():m.end()+5]
            # 排除前後是換行的情況
            if before.endswith('\n') or after.startswith('\n'):
                continue
            snippet = text[max(0, m.start()-15):m.end()+15]
            n_spaces = m.end() - m.start()
            self.results['5_consecutive_spaces'].append((location, snippet.strip(), f'{n_spaces} 個連續空白'))
            self.counts['5_consecutive_spaces'] += 1

    # --- 6a. PUA 字型字符殘留 ---
    def check_pua_glyphs(self, text, location):
        """偵測 Private Use Area 字型字符殘留（PDF 自訂字型映射）"""
        # 常見 PUA 映射:
        #   U+E18C~E18F: 選項標記 (A)(B)(C)(D) (最常見，約 64K 次)
        #   U+E129~E12D: 圈數字標記 ①②③④⑤
        #   U+E0C6~E0CF: 其他圈數字或符號
        #   U+F028~F0EF: Symbol 字型映射 (=, +, -, 等)
        # 這些不是亂碼，而是 PDF 自訂字型的 Unicode 映射未被正確轉換
        pua_found = []
        for m in re.finditer(r'[\ue000-\uf8ff]', text):
            pua_found.append(m)

        if pua_found:
            # 只記錄一筆彙總，不要每個字元都記一筆
            char_set = set(hex(ord(text[m.start()])) for m in pua_found)
            snippet = text[max(0, pua_found[0].start()-15):pua_found[0].end()+30]
            detail = f'{len(pua_found)} 個 PUA 字元，碼位: {", ".join(sorted(char_set)[:5])}{"..." if len(char_set) > 5 else ""}'
            self.results['6a_pua_glyphs'].append((location, snippet.strip(), detail))
            self.counts['6a_pua_glyphs'] += len(pua_found)

    # --- 6b. 中文亂碼特徵 ---
    def check_chinese_garble(self, text, location):
        """偵測真正的中文亂碼特徵（排除 PUA）"""
        # 罕見 CJK 相容表意文字區 (U+F900-U+FAFF)
        for m in re.finditer(r'[\uf900-\ufaff]{2,}', text):
            snippet = text[max(0, m.start()-10):m.end()+10]
            self.results['6b_chinese_garble'].append((location, snippet.strip(), 'CJK 相容區連續字元'))
            self.counts['6b_chinese_garble'] += 1

        # 控制字元 (非正常的)
        for m in re.finditer(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
            snippet = text[max(0, m.start()-10):m.end()+10]
            char_code = hex(ord(m.group()))
            self.results['6b_chinese_garble'].append((location, repr(snippet.strip()), f'控制字元 {char_code}'))
            self.counts['6b_chinese_garble'] += 1

        # 連續的罕用漢字（CJK Extension B+，U+20000 以上）
        for m in re.finditer(r'[\U00020000-\U0002FA1F]{2,}', text):
            snippet = text[max(0, m.start()-10):m.end()+10]
            self.results['6b_chinese_garble'].append((location, snippet.strip(), 'CJK Extension 連續字元'))
            self.counts['6b_chinese_garble'] += 1

    # --- 7. 數學符號被破壞 ---
    def check_math_symbols(self, text, location):
        """偵測數學符號可能被 OCR 破壞"""
        # 常見的數學符號替換問題
        patterns = [
            # ≧ 或 ≦ 被替換成 ? 或其他（排除 "=?" 求解格式）
            (r'[><]\s*\?', '比較符號+問號（可能原為 ≧ ≦）'),
            (r'\?\s*[><]', '問號+比較符號'),
            # 根號、積分等被破壞
            (r'[√∫∑∏].*\?', '數學符號後接問號'),
            # 上下標可能被破壞: X^2 -> X?2, X_i -> X?i
            (r'[A-Za-z]\?[0-9]', '可能的上下標破壞'),
            # 分數被破壞
            (r'\d+\s*/\s*\?', '分數符號破壞'),
            (r'\?\s*/\s*\d+', '分數符號破壞'),
        ]
        for pat, desc in patterns:
            for m in re.finditer(pat, text):
                snippet = text[max(0, m.start()-15):m.end()+15]
                self.results['7_math_symbols'].append((location, snippet.strip(), desc))
                self.counts['7_math_symbols'] += 1

        # 孤立的 replacement 模式（非 \ufffd 但可能是亂碼替換）
        # 例如連續的 ?? 在數學語境中
        for m in re.finditer(r'\?\?+', text):
            context = text[max(0, m.start()-20):m.end()+20]
            # 只在有數學語境時報告
            if re.search(r'[\d+\-*/=≧≦≥≤∑∫√πα-ω]', context):
                self.results['7_math_symbols'].append((location, context.strip(), '連續問號（數學語境）'))
                self.counts['7_math_symbols'] += 1

    # --- 8. 選項標記缺失 ---
    def check_missing_option_markers(self, text, location, question):
        """偵測選擇題中選項標記缺失"""
        q_type = question.get('type', '')
        options = question.get('options', {})

        if q_type == 'choice' and options:
            # 檢查是否有標準選項標記
            expected_keys = {'A', 'B', 'C', 'D'}
            actual_keys = set(options.keys())
            missing = expected_keys - actual_keys
            if missing and len(actual_keys) < 3:
                detail = f'缺少選項: {sorted(missing)}, 現有: {sorted(actual_keys)}'
                self.results['8_missing_options'].append((location, text[:80], detail))
                self.counts['8_missing_options'] += 1

        # 檢查題幹中是否包含選項文字（選項沒被正確分離）
        if q_type == 'choice':
            # 如果題幹中包含 (A) (B) (C) (D) 的模式，可能選項沒被正確拆分
            embedded = re.findall(r'\([A-D]\)', text)
            if len(embedded) >= 3 and not options:
                self.results['8_missing_options'].append(
                    (location, text[:100], f'題幹中有 {len(embedded)} 個選項標記但 options 為空'))
                self.counts['8_missing_options'] += 1

    # --- 9. 頁首/頁碼殘留 ---
    def check_page_residue(self, text, location):
        """偵測頁首或頁碼殘留在題目文字中"""
        patterns = [
            # 第X頁 / 共X頁
            (r'第\s*\d+\s*頁', '頁碼殘留'),
            (r'共\s*\d+\s*頁', '頁碼殘留'),
            # 代號：XXXXX（在題目中而非 metadata）
            (r'代號[：:]\s*\d{4,5}', '代號殘留'),
            # 考試名稱殘留
            (r'等別[：:]', '考試資訊殘留（等別）'),
            (r'類科[：:]', '考試資訊殘留（類科）'),
            (r'科目[：:]', '考試資訊殘留（科目）'),
            # 「請接背面」、「背面尚有題目」
            (r'請接背面', '翻頁提示殘留'),
            (r'背面尚有題目', '翻頁提示殘留'),
            (r'背面還有題目', '翻頁提示殘留'),
            # 頁碼 -X- 或 X/Y
            (r'-\s*\d+\s*-', '頁碼格式殘留'),
        ]
        for pat, desc in patterns:
            for m in re.finditer(pat, text):
                snippet = text[max(0, m.start()-15):m.end()+15]
                self.results['9_page_residue'].append((location, snippet.strip(), desc))
                self.counts['9_page_residue'] += 1


# ============================================================
# 主掃描邏輯
# ============================================================

def extract_all_texts(data):
    """從 JSON 資料中提取所有文字欄位"""
    texts = []  # [(field_path, text, question_obj_or_None), ...]

    # notes
    for i, note in enumerate(data.get('notes', [])):
        if note:
            texts.append((f'notes[{i}]', note, None))

    # sections
    for i, sec in enumerate(data.get('sections', [])):
        if isinstance(sec, str) and sec:
            texts.append((f'sections[{i}]', sec, None))
        elif isinstance(sec, dict):
            for k, v in sec.items():
                if isinstance(v, str) and v:
                    texts.append((f'sections[{i}].{k}', v, None))

    # questions
    for q in data.get('questions', []):
        q_num = q.get('number', '?')
        q_type = q.get('type', 'unknown')
        prefix = f'Q{q_num}'

        # stem
        stem = q.get('stem', '')
        if stem:
            texts.append((f'{prefix}.stem', stem, q))

        # options
        options = q.get('options', {})
        if isinstance(options, dict):
            for opt_key, opt_val in options.items():
                if isinstance(opt_val, str) and opt_val:
                    texts.append((f'{prefix}.options.{opt_key}', opt_val, None))
                elif isinstance(opt_val, dict):
                    opt_text = opt_val.get('text', '')
                    if opt_text:
                        texts.append((f'{prefix}.options.{opt_key}', opt_text, None))

        # sub_questions
        for j, sub in enumerate(q.get('sub_questions', [])):
            if isinstance(sub, str) and sub:
                texts.append((f'{prefix}.sub[{j}]', sub, None))
            elif isinstance(sub, dict):
                sub_stem = sub.get('stem', '')
                if sub_stem:
                    texts.append((f'{prefix}.sub[{j}].stem', sub_stem, None))

        # explanation / answer_text
        for field in ('explanation', 'answer_text', 'passage'):
            val = q.get(field, '')
            if val:
                texts.append((f'{prefix}.{field}', val, None))

    return texts


def scan_file(filepath, detector):
    """掃描單一 JSON 檔案"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        detector.results['0_file_error'].append((str(filepath), str(e), '檔案讀取錯誤'))
        detector.counts['0_file_error'] += 1
        return

    category = data.get('category', '未知')
    year = data.get('year', '?')
    subject = data.get('subject', '未知')
    loc_prefix = f'{category}/{year}年/{subject}'

    texts = extract_all_texts(data)

    for field_path, text, q_obj in texts:
        location = f'{loc_prefix}/{field_path}'

        # 跑所有偵測器
        detector.check_split_words(text, location)
        detector.check_code_contamination(text, location)
        detector.check_replacement_char(text, location)
        detector.check_bracket_mixing(text, location)
        detector.check_consecutive_spaces(text, location)
        detector.check_pua_glyphs(text, location)
        detector.check_chinese_garble(text, location)
        detector.check_math_symbols(text, location)
        detector.check_page_residue(text, location)

        # 選項標記缺失需要 question 物件
        if q_obj is not None:
            detector.check_missing_option_markers(text, location, q_obj)


def generate_report(detector, total_files, output_path):
    """產生報告"""
    DEFECT_INFO = {
        '0_file_error': {
            'name': '檔案讀取錯誤',
            'severity': 'Critical',
            'fix': '檢查檔案編碼和 JSON 格式',
        },
        '1_split_words': {
            'name': '英文單字被拆開',
            'severity': 'Major',
            'fix': '使用 regex 合併被空格拆開的英文後綴（-tion, -sion, -ment 等），'
                   '參考 tools/fix_ocr.py 的修復規則',
        },
        '2_code_contamination': {
            'name': '五位數代號汙染',
            'severity': 'Critical',
            'fix': '用 regex 移除文字尾端黏著的五位數代號（如 r"\\d{5}(?:、\\d{5})*$"），'
                   '注意區分代號和正常數字',
        },
        '3_replacement_char': {
            'name': 'Unicode replacement character',
            'severity': 'Critical',
            'fix': '回溯 PDF 原文確認原始字元，用正確字元替換 \\ufffd',
        },
        '4_bracket_mixing': {
            'name': '全形/半形括號混用',
            'severity': 'Minor',
            'fix': '統一為半形 (A)(B)(C)(D) 或全形 （A）（B）（C）（D），'
                   '建議統一為半形格式',
        },
        '5_consecutive_spaces': {
            'name': '連續空白（>2個）',
            'severity': 'Minor',
            'fix': '將超過 2 個的連續空白壓縮為單一空格',
        },
        '6a_pua_glyphs': {
            'name': 'PUA 字型字符殘留（PDF 自訂字型映射）',
            'severity': 'Major',
            'fix': '建立 PUA 碼位對照表，將 U+E18C~E18F 映射回 (A)(B)(C)(D)，'
                   'U+E129~E12D 映射回 ①②③④⑤，U+F0xx 映射回 Symbol 字型符號',
        },
        '6b_chinese_garble': {
            'name': '中文亂碼特徵',
            'severity': 'Critical',
            'fix': '回溯 PDF 原文，重新 OCR 或手動修正亂碼段落',
        },
        '7_math_symbols': {
            'name': '數學符號被破壞',
            'severity': 'Major',
            'fix': '回溯 PDF 原文，修正被替換的數學符號（≧→?, ≦→? 等）',
        },
        '8_missing_options': {
            'name': '選項標記缺失',
            'severity': 'Major',
            'fix': '檢查 OCR 解析邏輯，確保選項 (A)(B)(C)(D) 被正確分離',
        },
        '9_page_residue': {
            'name': '頁首/頁碼殘留',
            'severity': 'Minor',
            'fix': '在 OCR 後處理中過濾「第X頁」「請接背面」等頁面提示文字',
        },
    }

    lines = []
    lines.append('=' * 78)
    lines.append('  OCR 瑕疵全面掃描報告')
    lines.append(f'  掃描時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'  掃描檔案數: {total_files}')
    lines.append('=' * 78)
    lines.append('')

    # 總覽
    total_defects = sum(detector.counts.values())
    lines.append(f'瑕疵總數: {total_defects}')
    lines.append('')

    # 按嚴重度統計
    severity_counts = {'Critical': 0, 'Major': 0, 'Minor': 0}
    lines.append('--- 各類瑕疵統計 ---')
    lines.append(f'{"類型":<35} {"嚴重度":<10} {"數量":>8}')
    lines.append('-' * 58)

    for key in sorted(detector.counts.keys()):
        info = DEFECT_INFO.get(key, {'name': key, 'severity': '?', 'fix': ''})
        count = detector.counts[key]
        sev = info['severity']
        severity_counts[sev] = severity_counts.get(sev, 0) + count
        lines.append(f'{info["name"]:<32}   {sev:<10} {count:>8}')

    lines.append('-' * 58)
    lines.append(f'{"Critical 嚴重瑕疵:":<45} {severity_counts.get("Critical", 0):>8}')
    lines.append(f'{"Major 重要瑕疵:":<45} {severity_counts.get("Major", 0):>8}')
    lines.append(f'{"Minor 輕微瑕疵:":<45} {severity_counts.get("Minor", 0):>8}')
    lines.append(f'{"合計:":<45} {total_defects:>8}')
    lines.append('')

    # 各類瑕疵詳細實例（前 10 個）
    for key in sorted(detector.results.keys()):
        info = DEFECT_INFO.get(key, {'name': key, 'severity': '?', 'fix': ''})
        items = detector.results[key]
        if not items:
            continue

        lines.append('=' * 78)
        lines.append(f'[{info["severity"]}] {info["name"]} (共 {len(items)} 個)')
        lines.append(f'修復建議: {info["fix"]}')
        lines.append('-' * 78)

        for i, (location, snippet, detail) in enumerate(items[:10]):
            lines.append(f'  {i+1}. 位置: {location}')
            lines.append(f'     內容: {snippet[:120]}')
            lines.append(f'     說明: {detail}')
            lines.append('')

        if len(items) > 10:
            lines.append(f'  ... 還有 {len(items) - 10} 個同類瑕疵（已省略）')
            lines.append('')

    # 修復優先順序建議
    lines.append('=' * 78)
    lines.append('修復優先順序建議')
    lines.append('=' * 78)
    lines.append('')
    priority = 1
    for sev in ['Critical', 'Major', 'Minor']:
        for key in sorted(detector.counts.keys()):
            info = DEFECT_INFO.get(key, {'name': key, 'severity': '?', 'fix': ''})
            if info['severity'] == sev and detector.counts[key] > 0:
                lines.append(f'  {priority}. [{sev}] {info["name"]} ({detector.counts[key]} 個)')
                lines.append(f'     {info["fix"]}')
                lines.append('')
                priority += 1

    return '\n'.join(lines)


def main():
    print('=' * 60)
    print('  OCR 瑕疵全面掃描')
    print('=' * 60)
    print()

    detector = DefectDetector()

    # 收集所有 JSON 檔案
    json_files = sorted(EXAM_DIR.rglob('試題.json'))
    total = len(json_files)
    print(f'找到 {total} 個試題 JSON 檔案')
    print()

    # 掃描每個檔案
    for i, fp in enumerate(json_files, 1):
        if i % 100 == 0 or i == total:
            print(f'  進度: {i}/{total} ({i*100//total}%)')
        scan_file(fp, detector)

    print()
    print(f'掃描完成。瑕疵總數: {sum(detector.counts.values())}')
    print()

    # 輸出統計摘要到 console
    print('--- 各類瑕疵統計 ---')
    NAMES = {
        '0_file_error': '檔案讀取錯誤',
        '1_split_words': '英文單字被拆開',
        '2_code_contamination': '五位數代號汙染',
        '3_replacement_char': 'Unicode replacement',
        '4_bracket_mixing': '全形/半形括號混用',
        '5_consecutive_spaces': '連續空白',
        '6a_pua_glyphs': 'PUA 字型字符殘留',
        '6b_chinese_garble': '中文亂碼特徵',
        '7_math_symbols': '數學符號破壞',
        '8_missing_options': '選項標記缺失',
        '9_page_residue': '頁首/頁碼殘留',
    }
    for key in sorted(detector.counts.keys()):
        name = NAMES.get(key, key)
        print(f'  {name}: {detector.counts[key]}')

    # 產生完整報告
    report = generate_report(detector, total, REPORT_DIR / 'ocr_defect_report.txt')
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / 'ocr_defect_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\n完整報告已儲存: {report_path}')


if __name__ == '__main__':
    main()
