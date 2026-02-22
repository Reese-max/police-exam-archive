#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repair_missing_options.py - 修復 197 道選項遺失的考古題

分類:
  C 類: 107年 5 份考卷, PDF 無選項標記, 選項以換行分隔 (~120 題)
  B 類: PDF 有 PUA 標記但提取時部分遺失 (~46 題)
  A 類: 英文閱讀測驗段落片段, 非真正缺選項 (~24 題)
  D 類: 題幹在 PDF 提取時嚴重截斷 (~7 題)

用法:
  python tools/repair_missing_options.py              # 完整修復
  python tools/repair_missing_options.py --dry-run    # 預覽變更
  python tools/repair_missing_options.py --validate   # 僅驗證
"""

import json
import glob
import os
import re
import sys
import shutil
import hashlib
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from itertools import combinations

try:
    import pdfplumber
except ImportError:
    sys.exit("需要安裝 pdfplumber: pip install pdfplumber")

BASE_DIR = Path(__file__).resolve().parent.parent
QUIZ_DIR = BASE_DIR / '考古題庫'

PUA_MAP = {
    '\ue18c': '(A)', '\ue18d': '(B)', '\ue18e': '(C)', '\ue18f': '(D)',
    '\ue129': '①', '\ue12a': '②', '\ue12b': '③', '\ue12c': '④',
    '\ue12d': '⑤', '\ue12e': '⑥', '\ue12f': '⑦', '\ue130': '⑧',
    '\ue131': '⑨', '\ue132': '⑩', '\ue133': '⑪', '\ue134': '⑫',
    '\ue1c0': '㈠', '\ue1c1': '㈡', '\ue1c2': '㈢', '\ue1c3': '㈣',
    '\ue0c6': '', '\ue0c7': '', '\ue0c8': '', '\ue0c9': '', '\ue0ca': '',
    '\ue0cb': '', '\ue0cc': '', '\ue0cd': '', '\ue0ce': '', '\ue0cf': '',
}

# 考卷標頭/頁尾/注意事項模式
HEADER_LINE_PATTERNS = [
    re.compile(r'^\d{2,3}\s*年\s*(公務|特種)'),
    re.compile(r'^代號'),
    re.compile(r'^頁次'),
    re.compile(r'^考\s*試\s*(別|時間)'),
    re.compile(r'^等\s*(別|\s)'),
    re.compile(r'^類\s*科'),
    re.compile(r'^科\s*目'),
    re.compile(r'^座號'),
    re.compile(r'^(全一張|全一頁)'),
    re.compile(r'^-?\s*\d+\s*-?\s*$'),
    re.compile(r'^\d{5}([-、]\d{5})*\s*$'),
    re.compile(r'^\d{5}\s*$'),
    re.compile(r'^(請接背面|請以背面|背面尚有|請翻頁|\(請接)'),
    re.compile(r'^(人員考試|鐵路人員考試)'),
]

NOTE_KEYWORDS = [
    '不必抄題', '不予計分', '禁止使用', '鋼筆或原子筆',
    '2B鉛筆', '本試題為單一選擇題', '本測驗試題為單一選擇題',
    '共25題', '共20題', '共50題', '應使用本國文字',
    '可以使用電子計算器',
]

# OCR 修復規則 (簡化版)
OCR_FIXES = [
    (re.compile(r'(\w)ti on\b'), r'\1tion'),
    (re.compile(r'(\w)si on\b'), r'\1sion'),
    (re.compile(r'\bth at\b'), 'that'),
    (re.compile(r'\bth is\b'), 'this'),
    (re.compile(r'\bth e\b'), 'the'),
    (re.compile(r'\bth ey\b'), 'they'),
    (re.compile(r'\bwh at\b'), 'what'),
    (re.compile(r'\bwh en\b'), 'when'),
    (re.compile(r'\bwh ere\b'), 'where'),
    (re.compile(r'\bwh ich\b'), 'which'),
    (re.compile(r'\bf or\b'), 'for'),
    (re.compile(r'\bf rom\b'), 'from'),
    (re.compile(r'\bin to\b'), 'into'),
]

# ── 日誌 ──────────────────────────────────────

class Logger:
    def __init__(self):
        self.entries = []
        self.stats = defaultdict(int)

    def info(self, msg):
        self.entries.append(('INFO', msg))
        print(f"  [INFO] {msg}")

    def ok(self, msg):
        self.entries.append(('OK', msg))
        print(f"  [OK]   {msg}")

    def warn(self, msg):
        self.entries.append(('WARN', msg))
        print(f"  [WARN] {msg}")

    def err(self, msg):
        self.entries.append(('ERR', msg))
        print(f"  [ERR]  {msg}")

    def count(self, key, n=1):
        self.stats[key] += n

log = Logger()

# ── 工具函式 ─────────────────────────────────

def normalize_text(text):
    """與 pdf_to_questions.py 相同的正規化"""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\b\d{5}\b', '', text)
    for pat, repl in OCR_FIXES:
        text = pat.sub(repl, text)
    return text.strip()


def is_header_or_note(line):
    """判斷是否為標頭/頁尾/注意事項"""
    s = line.strip()
    if not s:
        return True
    for pat in HEADER_LINE_PATTERNS:
        if pat.match(s):
            return True
    if any(kw in s for kw in NOTE_KEYWORDS):
        return True
    if '注意' in s and ('：' in s or ':' in s) and len(s) < 80:
        return True
    if any(kw in s for kw in ['人員考試', '退除役軍人']) and len(s) < 80:
        return True
    return False


def file_hash(path):
    """計算檔案 SHA256"""
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()[:16]


def short_path(p):
    """縮短路徑以利顯示"""
    s = str(p).replace(str(BASE_DIR) + os.sep, '').replace('\\', '/')
    return s

# ── 掃描 ─────────────────────────────────────

def scan_all_affected():
    """掃描所有受影響的題目並分類"""
    affected = defaultdict(list)  # json_path → list of (qnum, category, info)

    for json_path in sorted(QUIZ_DIR.glob('**/試題.json')):
        data = json.loads(json_path.read_text(encoding='utf-8'))
        for q in data.get('questions', []):
            if q.get('type') != 'choice':
                continue
            stem = q.get('stem', '')
            has = [L for L in 'ABCD' if f'({L})' in stem]
            if len(has) == 4:
                continue

            # 分類
            if len(has) > 0:
                cat = 'b_class'
            elif _is_passage_fragment(stem, q):
                cat = 'a_class'
            elif _is_truncated(stem, q):
                cat = 'd_class'
            else:
                cat = 'c_class'

            affected[str(json_path)].append({
                'qnum': q.get('number'),
                'category': cat,
                'has_options': has,
                'missing': [L for L in 'ABCD' if L not in has],
                'stem_preview': stem[:80],
                'answer': q.get('answer', ''),
            })

    return affected


def _is_passage_fragment(stem, q):
    """判斷是否為英文閱讀測驗段落片段"""
    ascii_alpha = sum(1 for c in stem if c.isascii() and c.isalpha())
    ratio = ascii_alpha / max(len(stem), 1)
    if ratio > 0.5 and '?' not in stem and '？' not in stem:
        return True
    return False


def _is_truncated(stem, q):
    """判斷題幹是否被截斷"""
    if len(stem) < 80 and '?' not in stem and '？' not in stem:
        return True
    # 申論題被誤標為 choice
    if q.get('section') and '申論' in q.get('section', ''):
        return True
    return False

# ── PDF 提取 ──────────────────────────────────

def extract_pdf_lines(pdf_path):
    """從 PDF 提取所有非標頭行, 保留行結構"""
    lines = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                for line in text.split('\n'):
                    s = line.strip()
                    if s and not is_header_or_note(s):
                        lines.append(s)
    except Exception as e:
        log.err(f"PDF 讀取失敗 {pdf_path}: {e}")
    return lines


def extract_choice_questions_by_line(pdf_path):
    """
    從 PDF 提取選擇題, 保留每題的行結構。
    Returns: dict[int, list[str]]  題號 → 行列表 (不含題號本身)
    """
    lines = extract_pdf_lines(pdf_path)

    # 跳到選擇題區段 (乙、測驗題)
    start = 0
    for i, line in enumerate(lines):
        if re.match(r'^[乙]\s*[、．.]', line):
            start = i + 1
            break

    q_pattern = re.compile(r'^(\d{1,2})\s+(.+)')
    questions = {}
    current_num = None
    current_lines = []

    for line in lines[start:]:
        # 跳過分段標記
        if re.match(r'^[甲乙丙]\s*[、．.]', line):
            continue

        m = q_pattern.match(line)
        if m:
            num = int(m.group(1))
            # 驗證是否為合理題號 (1-60, 且遞增)
            if 1 <= num <= 60:
                if current_num is not None:
                    questions[current_num] = current_lines
                current_num = num
                current_lines = [m.group(2)]
                continue

        if current_num is not None:
            current_lines.append(line)

    if current_num is not None:
        questions[current_num] = current_lines

    return questions


def extract_question_raw_with_pua(pdf_path, qnum):
    """
    從 PDF 提取單題原始文字 (含 PUA 字元), 用於 B 類修復。
    Returns: str 或 None
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_lines = []
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                for line in text.split('\n'):
                    s = line.strip()
                    if s:
                        all_lines.append(s)
    except Exception as e:
        log.err(f"PDF 讀取失敗 {pdf_path}: {e}")
        return None

    # 找到指定題號
    q_start = re.compile(rf'^{qnum}\s+(.+)')
    q_next = re.compile(rf'^{qnum + 1}\s+')

    found = False
    q_lines = []

    for line in all_lines:
        if is_header_or_note(line) and not found:
            continue
        if not found:
            m = q_start.match(line)
            if m:
                found = True
                q_lines.append(m.group(1))
        else:
            # 遇到下一題就停
            if q_next.match(line):
                break
            # 跳過頁面標頭
            skip = False
            for pat in HEADER_LINE_PATTERNS:
                if pat.match(line.strip()):
                    skip = True
                    break
            if skip:
                continue
            q_lines.append(line)

    if not q_lines:
        return None

    # 合併行, 替換 PUA
    full_text = ' '.join(q_lines)
    for pua, label in PUA_MAP.items():
        full_text = full_text.replace(pua, label)

    return normalize_text(full_text)

# ── C 類修復 ──────────────────────────────────

def find_stem_end_idx(lines):
    """
    找到題幹結尾行索引。
    優先尋找問號 (？/?)，其次冒號 (：/:) 後跟選項文字。
    """
    # 優先: 最後一個問號
    last_qm = -1
    for i, line in enumerate(lines):
        if '？' in line or '?' in line:
            last_qm = i

    if last_qm >= 0:
        return last_qm, '?'

    # 其次: 冒號 (常見於「請選出正確者：」)
    for i, line in enumerate(lines):
        if ('：' in line or ':' in line) and ('正確' in line or '錯誤' in line):
            return i, ':'

    return -1, None


def group_into_4_options(lines):
    """
    將選項行分成恰好 4 組。
    使用「最短邊界行」啟發式: 選項結尾行通常較短, 而斷行續行通常填滿整行。
    """
    n = len(lines)
    if n == 0:
        return None

    # 少於 4 行: 嘗試用空格拆分
    if n < 4:
        all_text = ' '.join(lines)
        parts = all_text.split()
        if len(parts) >= 4:
            # 拆成 4 段: 短選項格式 (如 "甲 乙 丙 丁")
            if len(parts) == 4:
                return [[p] for p in parts]
            # 嘗試用多空格拆分
            parts2 = re.split(r'\s{2,}', all_text)
            if len(parts2) == 4:
                return [[p] for p in parts2]
        return None

    if n == 4:
        return [[l] for l in lines]

    # 多於 4 行: 找最佳分組
    max_len = max(len(l) for l in lines)
    if max_len == 0:
        return None

    best_score = -float('inf')
    best_groups = None

    for splits in combinations(range(1, n), 3):
        i, j, k = splits
        groups = [lines[:i], lines[i:j], lines[j:k], lines[k:]]

        score = 0
        valid = True
        for g_idx, g in enumerate(groups):
            merged = ''.join(g)
            # 太短的組不太可能是獨立選項 (斷行片段如「分之一」)
            if len(merged) < 2:
                valid = False
                break
            if len(merged) < 5:
                score -= 200  # 重罰: 過短的組很可能是續行片段
            # 前 3 組的最後一行越短 → 越可能是選項自然結尾
            if g_idx < 3:
                score += max_len - len(g[-1])

        if valid and score > best_score:
            best_score = score
            best_groups = groups

    return best_groups


def detect_combo_line(line):
    """
    偵測是否為組合答案行 (如 '③④ ②③ ①③④ ①②③④')。
    Returns: list of tokens 或 None
    """
    normalized = unicodedata.normalize('NFKC', line.strip())
    tokens = normalized.split()
    if len(tokens) < 2:
        return None
    for token in tokens:
        if not re.match(r'^[1-6]+$', token):
            return None
    return tokens


def has_circled_number_subitems(lines):
    """檢查行列表中是否含有 ①②③④ 等圓圈數字子項 (≥3 個)"""
    circled_nums = set('①②③④⑤⑥⑦⑧⑨⑩')
    text = ' '.join(lines)
    count = sum(1 for c in text if c in circled_nums)
    return count >= 3


# ── 新增: 4-ITEM / INLINE / COMBO 回退修復 ────────

def _find_last_delimiter(text):
    """
    找到 stem 中最後一個分隔符 (？?：:) 的位置。
    Returns: (delim_pos, before_text, after_text) 或 (None, None, None)
    """
    best_pos = -1
    for delim in ['？', '?']:
        pos = text.rfind(delim)
        if pos > best_pos:
            best_pos = pos
    if best_pos < 0:
        # 嘗試冒號
        for delim in ['：', ':']:
            pos = text.rfind(delim)
            if pos > 0:
                # 驗證冒號前面有選擇相關的詞
                pre = text[max(0, pos - 15):pos]
                if any(kw in pre for kw in ['正確', '錯誤', '適當', '包括', '者', '項',
                                             '設備', '情形', '何者', '安排']):
                    best_pos = pos
                    break
    if best_pos >= 0:
        after = text[best_pos + 1:].strip()
        # 若 after 以句號開始的續行文字, 取句號後的部分作為選項區
        period_pos = after.find('。')
        if period_pos > 0 and period_pos < len(after) - 4:
            # 句號後有足夠文字 → 可能是 "其中...半數。 5名 6名 7名 8名" 形式
            after_period = after[period_pos + 1:].strip()
            if after_period:
                # 用句號重新分割: before 包含到句號, after 從句號後開始
                return best_pos, text[:best_pos + 1] + ' ' + after[:period_pos + 1], after_period
        return best_pos, text[:best_pos + 1], after
    return None, None, None


def _parse_numbered_items(text):
    """
    解析文字中的編號子項 (1xxx 2xxx 3xxx 4xxx ...)。
    NFKC 正規化後 ①→1, ②→2, ..., 所以用數字匹配。
    Returns: dict{num: item_text} 或 None (若找不到連續編號)
    """
    # 找所有可能的子項起始位置
    # 模式: (行首或空白) + 數字 + 非數字非空白字元
    candidates = []
    for m in re.finditer(r'(?:^|\s)([1-6])(?=[^\d\s])', text):
        num = int(m.group(1))
        digit_pos = m.start(1)
        candidates.append((num, digit_pos))

    if not candidates:
        return None

    # 貪心匹配: 依序找 1, 2, 3, 4 (可選 5, 6)
    items = {}
    search_from = 0
    for target in range(1, 7):
        found = False
        for num, pos in candidates:
            if num == target and pos >= search_from:
                items[target] = pos
                search_from = pos + 2
                found = True
                break
        if not found:
            break  # 中斷序列

    # 至少需要 4 個連續編號
    if not all(n in items for n in [1, 2, 3, 4]):
        return None

    max_item = max(items.keys())

    # 提取每個子項的文字
    result = {}
    for num in sorted(items.keys()):
        text_start = items[num] + 1  # 跳過數字本身
        if num < max_item and num + 1 in items:
            # 到下一個子項之前的空白
            text_end = items[num + 1]
        else:
            text_end = len(text)
        item_text = text[text_start:text_end].strip()
        result[num] = item_text

    return result


def repair_4item_as_abcd(stem):
    """
    偵測 stem 中恰好有 4 個編號子項 (1xxx 2xxx 3xxx 4xxx)，
    這些子項直接就是 ABCD 選項。
    若有 5+ 子項或有 4 個 combo tokens，則不適用此函數。
    Returns: 修復後的 stem 或 None
    """
    norm = unicodedata.normalize('NFKC', stem)
    delim_pos, before, after = _find_last_delimiter(norm)
    if not after:
        return None

    items = _parse_numbered_items(after)
    if not items:
        return None

    # 若有 5+ 子項 → 不是 4-ITEM 類型
    if max(items.keys()) > 4:
        return None

    # 若恰好 4 項
    if len(items) != 4:
        return None

    # 清除最後一項結尾的 combo tokens 殘留 (如 "23" "134 123")
    last_text = items[4]
    cleaned = re.sub(r'(\s+\d{1,6})+\s*$', '', last_text).strip()
    if len(cleaned) >= 2:
        items[4] = cleaned
    elif len(cleaned) == 0:
        return None

    # 組裝: before + (A)item1 (B)item2 (C)item3 (D)item4
    result = before
    for i in range(1, 5):
        label = chr(ord('A') + i - 1)
        result += f' ({label}){items[i]}'

    return normalize_text(result)


def repair_combo_from_stem(stem):
    """
    偵測 stem 中有 4+ 編號子項且 4 個 combo tokens 在結尾。
    子項留在題幹中, combo tokens 作為 (A)(B)(C)(D) 選項。
    Returns: 修復後的 stem 或 None
    """
    norm = unicodedata.normalize('NFKC', stem)
    delim_pos, before, after = _find_last_delimiter(norm)
    if not after:
        return None

    items = _parse_numbered_items(after)
    if not items or len(items) < 4:
        return None

    # 在最後一項的文字末尾找 combo tokens
    last_num = max(items.keys())
    last_text = items[last_num]

    # 匹配 4 個 combo tokens (由數字組成的 tokens)
    combo_match = re.search(r'\s+((?:[1-6]+\s+){3}[1-6]+)\s*$', last_text)
    if not combo_match:
        return None

    combo_str = combo_match.group(1).strip()
    combo_tokens = combo_str.split()
    if len(combo_tokens) != 4:
        return None

    # 清除最後一項中的 combo tokens
    items[last_num] = last_text[:combo_match.start()].strip()

    # 組裝: before + 子項描述 + (A)combo1 (B)combo2 (C)combo3 (D)combo4
    stem_part = before
    for num in sorted(items.keys()):
        stem_part += f' {num}{items[num]}'
    opts_text = ' '.join(f'({L}){tok}' for L, tok in zip('ABCD', combo_tokens))
    result = stem_part + ' ' + opts_text

    return normalize_text(result)


def repair_inline_options(stem, pdf_full_text=None):
    """
    分隔符之後的文字包含 4 個純文字選項, 需拆分並加 (A)(B)(C)(D) 標記。
    優先使用 pdf_full_text (完整), 備用 stem (可能截斷)。
    Returns: 修復後的 stem 或 None
    """
    # 選擇最佳文字來源
    for text_source in [pdf_full_text, stem]:
        if not text_source:
            continue
        norm = unicodedata.normalize('NFKC', text_source)
        delim_pos, before, after = _find_last_delimiter(norm)
        if not after or len(after) < 4:
            continue

        # 跳過有編號子項的 (那些由 4-ITEM 或 COMBO 處理)
        if _parse_numbered_items(after):
            continue

        # 嘗試多種分割策略
        parts = _try_split_inline(after)
        if parts and len(parts) == 4:
            # 組裝
            result = before
            for i, part in enumerate(parts):
                label = chr(ord('A') + i)
                result += f' ({label}){part.strip()}'
            return normalize_text(result)

    # 備用: 無明確分隔符, 嘗試在全文中用冒號或句號分割
    for text_source in [pdf_full_text, stem]:
        if not text_source:
            continue
        norm = unicodedata.normalize('NFKC', text_source)
        # 嘗試任何冒號/句號作為分隔 (不需要關鍵字)
        for delim in ['：', ':']:
            pos = norm.rfind(delim)
            if pos > 10:
                after = norm[pos + 1:].strip()
                if after and not _parse_numbered_items(after):
                    parts = _try_split_inline(after)
                    if parts and len(parts) == 4:
                        before = norm[:pos + 1]
                        result = before
                        for i, part in enumerate(parts):
                            label = chr(ord('A') + i)
                            result += f' ({label}){part.strip()}'
                        return normalize_text(result)

    return None


def _try_split_inline(text):
    """
    嘗試多種策略將 inline 文字分割為恰好 4 段。
    Returns: list of 4 strings 或 None
    """
    text = text.strip()
    if not text:
        return None

    # 策略 1: 雙空格分隔
    parts = re.split(r'\s{2,}', text)
    if len(parts) == 4 and all(len(p.strip()) >= 1 for p in parts):
        return [p.strip() for p in parts]

    # 策略 2: 結構性重複前綴
    # 偵測反覆出現的前綴模式 (如 "處其管理權人", "往南", "第一", "查獲")
    result = _split_by_repeated_prefix(text)
    if result:
        return result

    # 策略 3: 科學方法名稱 (中文名 + 括號英文) 分割
    # 如 "微粒子試劑（small particle reagent） 濕性指紋粉末法（wet powder method）"
    result = _split_by_paren_method(text)
    if result:
        return result

    # 策略 4: 排列題 (數字序列：描述)
    # 如 "312:引子定位、... 321:引子定位、..."
    result = _split_by_ordering_pattern(text)
    if result:
        return result

    # 策略 5: 數學公式 (逗號分隔的子表達式, 空格分隔選項)
    result = _split_math_formulas(text)
    if result:
        return result

    # 策略 6: 短選項 (每個 ≤ 8 字) - 如 "5名 6名 7名 8名"
    words = text.split()
    if len(words) == 4 and all(len(w) <= 10 for w in words):
        return words

    # 策略 7: 尋找 4 段相似長度的文字, 用單空格分割後重組
    result = _split_by_equal_segments(text)
    if result:
        return result

    return None


def _split_by_repeated_prefix(text):
    """依重複前綴分割。如 '處其管理權人... 處其管理權人...'"""
    # 找 2+ 字元的前綴在文字中出現 3-4 次
    for prefix_len in range(6, 1, -1):
        # 用正規表達式找前綴出現位置
        # 前綴: 文字開頭或空白後的 N 個字元
        prefix_positions = {}
        for m in re.finditer(r'(?:^|\s)(\S{' + str(prefix_len) + r'})', text):
            prefix = m.group(1)
            if prefix not in prefix_positions:
                prefix_positions[prefix] = []
            prefix_positions[prefix].append(m.start())

        for prefix, positions in prefix_positions.items():
            if len(positions) == 4:
                # 用前綴位置分割
                parts = []
                for i, pos in enumerate(positions):
                    # 跳過前導空白
                    start = pos if pos == 0 else pos + 1
                    end = positions[i + 1] if i + 1 < len(positions) else len(text)
                    parts.append(text[start:end].strip())
                if len(parts) == 4 and all(len(p) >= 2 for p in parts):
                    return parts
            elif len(positions) == 3:
                # 3+1 模式: 3 次前綴 + 1 個不同開頭 (如 "第一..第二..第三.. 交通...")
                # 找到 3 個前綴的位置, 推斷第 4 段
                all_positions = list(positions)
                # 第 4 段的開始: 第 3 個前綴之後到文字結尾中的空白邊界
                last_prefix_pos = positions[-1]
                # 找第 3 個前綴項的結尾 (下一個空白)
                last_prefix_start = last_prefix_pos if last_prefix_pos == 0 else last_prefix_pos + 1
                # 尋找第 3 項結束、第 4 項開始的位置
                # 在第 3 項後的文字中找不匹配前綴的部分
                after_last = text[last_prefix_start:]
                # 找到第 3 個前綴項匹配的內容結尾
                rest_words = after_last.split()
                if len(rest_words) >= 2:
                    # 第 3 項佔一些詞, 之後是第 4 項
                    for split_at in range(1, len(rest_words)):
                        w = rest_words[split_at]
                        if not w.startswith(prefix[:2]):
                            # 此處開始第 4 項
                            third_item = ' '.join(rest_words[:split_at])
                            fourth_item = ' '.join(rest_words[split_at:])
                            # 組裝全部 4 段
                            parts = []
                            for i in range(2):
                                start = positions[i] if positions[i] == 0 else positions[i] + 1
                                end = positions[i + 1]
                                parts.append(text[start:end].strip())
                            parts.append(third_item)
                            parts.append(fourth_item)
                            if len(parts) == 4 and all(len(p) >= 2 for p in parts):
                                return parts
                            break
    return None


def _split_by_paren_method(text):
    """
    分割科學方法名稱: "中文名（英文名） 中文名（英文名）..."
    在 ）或) 後面跟著空格和中文字元處分割
    """
    parts = re.split(r'(?<=[）)])\s+(?=[\u4e00-\u9fffA-Z])', text)
    if len(parts) == 4 and all(len(p.strip()) >= 3 for p in parts):
        return [p.strip() for p in parts]
    return None


def _split_by_ordering_pattern(text):
    """
    分割排列題: "312:引子定位... 321:引子定位..."
    或 "312：引子定位..."
    """
    parts = re.split(r'\s+(?=\d{3,}[：:])', text)
    if len(parts) == 4:
        return [p.strip() for p in parts]
    return None


def _split_math_formulas(text):
    """
    分割數學公式選項: "2a, 2bc, 2de  a2, bc, de" 等
    每個選項內部用逗號分隔, 選項之間用雙空格或特殊分隔
    """
    # 先嘗試雙空格
    parts = re.split(r'\s{2,}', text)
    if len(parts) == 4:
        return [p.strip() for p in parts]

    # 嘗試找到重複的逗號模式 (每個選項有 N 個逗號)
    commas = [i for i, c in enumerate(text) if c == ',']
    if len(commas) >= 8:  # 4 options * 2+ commas each
        # 嘗試分成 4 組等數量逗號
        per_group = len(commas) // 4
        if per_group >= 2 and len(commas) % 4 == 0:
            boundaries = []
            for g in range(1, 4):
                idx = commas[g * per_group - 1]
                # 找此逗號後的空格
                space_pos = text.find(' ', idx + 1)
                if space_pos > 0:
                    boundaries.append(space_pos)
            if len(boundaries) == 3:
                parts = [
                    text[:boundaries[0]].strip(),
                    text[boundaries[0]:boundaries[1]].strip(),
                    text[boundaries[1]:boundaries[2]].strip(),
                    text[boundaries[2]:].strip(),
                ]
                if all(len(p) >= 2 for p in parts):
                    return parts
    return None


def _split_by_equal_segments(text):
    """
    嘗試將文字分成 4 段長度相近的片段。
    用單空格位置作為可能的分割點。
    """
    words = text.split()
    n = len(words)
    if n < 4 or n > 40:
        return None

    # 計算每個詞的累計長度
    cum_len = [0]
    for w in words:
        cum_len.append(cum_len[-1] + len(w))
    total = cum_len[-1]
    target = total / 4

    # 找 3 個最佳分割點, 使 4 段長度最接近 target
    best_score = float('inf')
    best_splits = None

    for i in range(1, n - 2):
        for j in range(i + 1, n - 1):
            for k in range(j + 1, n):
                lens = [
                    cum_len[i],
                    cum_len[j] - cum_len[i],
                    cum_len[k] - cum_len[j],
                    cum_len[n] - cum_len[k],
                ]
                if any(l < 2 for l in lens):
                    continue
                score = sum((l - target) ** 2 for l in lens)
                if score < best_score:
                    best_score = score
                    best_splits = (i, j, k)

    if best_splits is None:
        return None

    i, j, k = best_splits
    parts = [
        ' '.join(words[:i]),
        ' '.join(words[i:j]),
        ' '.join(words[j:k]),
        ' '.join(words[k:]),
    ]

    # 驗證: 4 段長度差異不能太大 (最長不超過最短的 5 倍)
    lens = [len(p) for p in parts]
    if max(lens) > min(lens) * 5:
        return None

    return parts


def repair_incomplete_fallback(json_stem, pdf_lines_dict=None, qnum=None):
    """
    對 repair_c_class_stem 失敗的題目, 嘗試回退修復策略。
    依序嘗試: combo_from_stem → 4item_as_abcd → inline_options
    Returns: 修復後的 stem 或 None
    """
    # 策略 1: stem 中有完整 combo tokens (如 "13 124 134 1234")
    result = repair_combo_from_stem(json_stem)
    if result:
        log.info("  → combo_from_stem 成功")
        return result

    # 策略 2: 4 個編號子項直接作為 ABCD
    result = repair_4item_as_abcd(json_stem)
    if result:
        log.info("  → 4item_as_abcd 成功")
        return result

    # 策略 3: inline 選項分割
    pdf_full = None
    if pdf_lines_dict and qnum and qnum in pdf_lines_dict:
        raw_lines = pdf_lines_dict[qnum]
        pdf_full = ' '.join(raw_lines)
        # 替換 PUA 字元
        for pua, label in PUA_MAP.items():
            pdf_full = pdf_full.replace(pua, label)
        pdf_full = normalize_text(pdf_full)

    result = repair_inline_options(json_stem, pdf_full)
    if result:
        log.info("  → inline_options 成功")
        return result

    return None


def repair_c_class_stem(pdf_lines_dict, qnum):
    """
    修復 C 類選擇題: 從 PDF 行結構識別選項邊界並插入標記。
    組合題型 (①②③④ 子項 + 組合答案) 另外處理。
    Returns: 修復後的 stem 或 None
    """
    if qnum not in pdf_lines_dict:
        return None

    lines = pdf_lines_dict[qnum]
    if not lines:
        return None

    # 找到題幹結尾邊界
    end_idx, delim_type = find_stem_end_idx(lines)
    if end_idx < 0:
        return None

    # 分割題幹行 / 選項行
    stem_lines = lines[:end_idx + 1]
    option_lines = lines[end_idx + 1:]

    # 處理結尾行後面可能有選項文字的情況
    end_line = stem_lines[-1]
    if delim_type == '?':
        pos_zw = end_line.rfind('？')
        pos_hw = end_line.rfind('?')
        delim_pos = max(pos_zw, pos_hw)
    else:  # ':'
        pos_zw = end_line.rfind('：')
        pos_hw = end_line.rfind(':')
        delim_pos = max(pos_zw, pos_hw)

    after_delim = end_line[delim_pos + 1:].strip() if delim_pos >= 0 else ''
    if after_delim:
        option_lines.insert(0, after_delim)
        stem_lines[-1] = end_line[:delim_pos + 1]

    if not option_lines:
        return None

    # ── 組合題偵測 ──
    # 檢查最後一行是否為組合答案行 (如 "③④ ②③ ①③④ ①②③④")
    combo_tokens = detect_combo_line(option_lines[-1])

    if combo_tokens:
        if len(combo_tokens) == 4:
            # 完美: 4 個組合答案 → 子項文字留在題幹, 組合答案作為 ABCD
            all_text = ' '.join(stem_lines + option_lines[:-1])
            normalized_stem = normalize_text(all_text)
            opts_text = ' '.join(
                f'({L}){tok}' for L, tok in zip('ABCD', combo_tokens)
            )
            return normalized_stem + ' ' + opts_text
        else:
            # 部分組合答案 (不足 4 個) → 無法重建
            return None

    # 檢查是否為組合題但缺少組合答案行 (有 ①②③④ 子項)
    if has_circled_number_subitems(option_lines):
        return None  # 組合題但答案行缺失 → 標記 incomplete

    # ── 普通選擇題: 用分組演算法 ──
    groups = group_into_4_options(option_lines)
    if groups is None or len(groups) != 4:
        return None

    # 組裝修復後的 stem
    stem_text = ' '.join(stem_lines)
    parts = [stem_text]
    for i, group in enumerate(groups):
        label = chr(ord('A') + i)
        opt_text = ' '.join(group)
        parts.append(f'({label}){opt_text}')

    repaired = ' '.join(parts)
    return normalize_text(repaired)

# ── B 類修復 ──────────────────────────────────

def repair_b_class_stem(pdf_path, qnum):
    """
    修復 B 類選擇題: 從 PDF 重新提取完整選項 (含 PUA 映射)。
    Returns: 修復後的 stem 或 None
    """
    new_stem = extract_question_raw_with_pua(pdf_path, qnum)
    if not new_stem:
        return None

    # 驗證 4 個選項標記都在
    has = [L for L in 'ABCD' if f'({L})' in new_stem]
    if len(has) < 4:
        return None

    return new_stem

# ── 主流程 ────────────────────────────────────

def backup_files(json_paths, backup_dir):
    """備份所有受影響的 JSON 檔案"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    for jp in json_paths:
        src = Path(jp)
        # 保留目錄結構
        rel = src.relative_to(QUIZ_DIR)
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    log.info(f"已備份 {len(json_paths)} 個檔案到 {backup_dir}")


def apply_repairs(affected, dry_run=False):
    """對所有受影響的 JSON 檔案套用修復"""

    # 先按 json_path 分組, 每個檔案只讀寫一次
    for json_path, items in sorted(affected.items()):
        jp = Path(json_path)
        pdf_path = jp.parent / '試題.pdf'

        data = json.loads(jp.read_text(encoding='utf-8'))
        modified = False

        # 分類此檔案中的受影響題目
        c_items = [it for it in items if it['category'] == 'c_class']
        b_items = [it for it in items if it['category'] == 'b_class']
        a_items = [it for it in items if it['category'] == 'a_class']
        d_items = [it for it in items if it['category'] == 'd_class']

        # ── C 類修復 ──
        if c_items and pdf_path.exists():
            pdf_lines = extract_choice_questions_by_line(str(pdf_path))
            for it in c_items:
                qnum = it['qnum']
                new_stem = repair_c_class_stem(pdf_lines, qnum)
                if new_stem:
                    # 找到對應題目並更新
                    for q in data['questions']:
                        if q.get('number') == qnum and q.get('type') == 'choice':
                            old_stem = q['stem']
                            q['stem'] = new_stem
                            modified = True
                            log.ok(f"C 類修復 {short_path(jp)} Q{qnum}")
                            log.count('c_repaired')
                            break
                    else:
                        log.warn(f"C 類找不到 Q{qnum} in {short_path(jp)}")
                        log.count('c_not_found')
                else:
                    # C 類修復失敗 → 嘗試回退策略
                    for q in data['questions']:
                        if q.get('number') == qnum and q.get('type') == 'choice':
                            fallback_stem = repair_incomplete_fallback(
                                q['stem'], pdf_lines, qnum
                            )
                            if fallback_stem:
                                q['stem'] = fallback_stem
                                # 移除 incomplete 標記
                                if 'subtype' in q:
                                    del q['subtype']
                                modified = True
                                log.ok(f"C 類回退修復 {short_path(jp)} Q{qnum}")
                                log.count('c_fallback_repaired')
                            else:
                                if q.get('subtype') != 'incomplete':
                                    q['subtype'] = 'incomplete'
                                    modified = True
                                log.warn(f"C 類標記 incomplete {short_path(jp)} Q{qnum}")
                                log.count('c_incomplete')
                            break

        # ── B 類修復 ──
        if b_items and pdf_path.exists():
            for it in b_items:
                qnum = it['qnum']
                new_stem = repair_b_class_stem(str(pdf_path), qnum)
                if new_stem:
                    for q in data['questions']:
                        if q.get('number') == qnum and q.get('type') == 'choice':
                            old_stem = q['stem']
                            q['stem'] = new_stem
                            modified = True
                            log.ok(f"B 類修復 {short_path(jp)} Q{qnum}")
                            log.count('b_repaired')
                            break
                    else:
                        log.warn(f"B 類找不到 Q{qnum} in {short_path(jp)}")
                        log.count('b_not_found')
                else:
                    log.warn(f"B 類無法修復 {short_path(jp)} Q{qnum}")
                    log.count('b_failed')

        # ── A 類標記 ──
        for it in a_items:
            qnum = it['qnum']
            for q in data['questions']:
                if q.get('number') == qnum and q.get('type') == 'choice':
                    if q.get('subtype') != 'passage_fragment':
                        q['subtype'] = 'passage_fragment'
                        modified = True
                        log.ok(f"A 類標記 {short_path(jp)} Q{qnum}")
                        log.count('a_marked')
                    break

        # ── D 類修復 ──
        if d_items and pdf_path.exists():
            for it in d_items:
                qnum = it['qnum']
                # 嘗試從 PDF 重新提取
                new_stem = extract_question_raw_with_pua(str(pdf_path), qnum)
                if new_stem and len(new_stem) > len(it['stem_preview']):
                    has_opts = [L for L in 'ABCD' if f'({L})' in new_stem]
                    if len(has_opts) == 4:
                        for q in data['questions']:
                            if q.get('number') == qnum and q.get('type') == 'choice':
                                q['stem'] = new_stem
                                modified = True
                                log.ok(f"D 類修復 {short_path(jp)} Q{qnum}")
                                log.count('d_repaired')
                                break
                    else:
                        # 有更完整的文字但仍缺選項
                        for q in data['questions']:
                            if q.get('number') == qnum and q.get('type') == 'choice':
                                if q.get('subtype') != 'incomplete':
                                    q['subtype'] = 'incomplete'
                                    modified = True
                                    log.ok(f"D 類標記 incomplete {short_path(jp)} Q{qnum}")
                                    log.count('d_marked')
                                break
                else:
                    for q in data['questions']:
                        if q.get('number') == qnum and q.get('type') == 'choice':
                            if q.get('subtype') != 'incomplete':
                                q['subtype'] = 'incomplete'
                                modified = True
                                log.count('d_marked')
                            break

        # 寫回 JSON
        if modified and not dry_run:
            jp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8'
            )


def validate_all():
    """驗證所有選擇題的選項完整性"""
    total = 0
    missing = 0
    marked = 0
    details = []

    for json_path in sorted(QUIZ_DIR.glob('**/試題.json')):
        data = json.loads(json_path.read_text(encoding='utf-8'))
        for q in data.get('questions', []):
            if q.get('type') != 'choice':
                continue
            total += 1

            # 跳過已標記的特殊題目
            if q.get('subtype') in ('passage_fragment', 'incomplete'):
                marked += 1
                continue

            stem = q.get('stem', '')
            has = [L for L in 'ABCD' if f'({L})' in stem]
            if len(has) < 4:
                missing += 1
                details.append({
                    'file': short_path(json_path),
                    'qnum': q.get('number'),
                    'has': has,
                    'missing': [L for L in 'ABCD' if L not in has],
                })

    return total, missing, marked, details


def main():
    parser = argparse.ArgumentParser(description='修復選項遺失的考古題')
    parser.add_argument('--dry-run', action='store_true',
                        help='預覽變更, 不修改檔案')
    parser.add_argument('--validate', action='store_true',
                        help='僅驗證, 不修復')
    args = parser.parse_args()

    print("=" * 60)
    print("  修復選項遺失的考古題")
    print("=" * 60)

    # ── 驗證模式 ──
    if args.validate:
        print("\n[驗證模式]")
        total, missing, marked, details = validate_all()
        print(f"\n  選擇題總數: {total}")
        print(f"  已標記特殊: {marked} (passage_fragment / incomplete)")
        print(f"  仍缺選項:   {missing}")
        if details:
            print(f"\n  缺選項明細:")
            for d in details[:30]:
                print(f"    {d['file']} Q{d['qnum']}: has={d['has']} missing={d['missing']}")
            if len(details) > 30:
                print(f"    ...及另外 {len(details) - 30} 題")
        return

    # ── 掃描 ──
    print("\n[1/5] 掃描受影響的題目...")
    affected = scan_all_affected()

    total_items = sum(len(v) for v in affected.values())
    cats = defaultdict(int)
    for items in affected.values():
        for it in items:
            cats[it['category']] += 1

    print(f"\n  發現 {total_items} 題受影響, 分布於 {len(affected)} 個檔案:")
    print(f"    C 類 (無標記):   {cats['c_class']}")
    print(f"    B 類 (部分標記): {cats['b_class']}")
    print(f"    A 類 (段落片段): {cats['a_class']}")
    print(f"    D 類 (截斷):     {cats['d_class']}")

    if total_items == 0:
        print("\n  沒有需要修復的題目!")
        return

    # ── 備份 ──
    if not args.dry_run:
        print("\n[2/5] 備份受影響的 JSON 檔案...")
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = BASE_DIR / 'backups' / f'repair_{ts}'
        backup_files(list(affected.keys()), backup_dir)
    else:
        print("\n[2/5] 備份 (跳過 - dry-run 模式)")

    # ── 修復 ──
    mode_str = "(dry-run)" if args.dry_run else ""
    print(f"\n[3/5] 套用修復 {mode_str}...")
    apply_repairs(affected, dry_run=args.dry_run)

    # ── 驗證 ──
    print(f"\n[4/5] 驗證修復結果...")
    total, missing, marked, details = validate_all()

    # ── 報告 ──
    print(f"\n[5/5] 修復報告")
    print("=" * 60)
    print(f"  C 類修復: {log.stats['c_repaired']} 成功, {log.stats['c_fallback_repaired']} 回退修復, {log.stats['c_incomplete']} 標記incomplete")
    print(f"  B 類修復: {log.stats['b_repaired']} 成功, {log.stats['b_failed']} 失敗")
    print(f"  A 類標記: {log.stats['a_marked']}")
    print(f"  D 類修復: {log.stats['d_repaired']} 修復, {log.stats['d_marked']} 標記")
    print(f"  ─────────────────────────")
    print(f"  選擇題總數:   {total}")
    print(f"  仍缺選項:     {missing}")
    print(f"  已標記特殊:   {marked}")
    if missing > 0:
        print(f"\n  仍缺選項的題目:")
        for d in details[:20]:
            print(f"    {d['file']} Q{d['qnum']}: missing={d['missing']}")
        if len(details) > 20:
            print(f"    ...及另外 {len(details) - 20} 題")
    print("=" * 60)


if __name__ == '__main__':
    main()
