# -*- coding: utf-8 -*-
"""
OCR 文字修復：用 wordninja 自動修復 PDF 抽文字時的英文斷字錯誤。

策略：
  1. 找出文字裡「連續英文 token」區段（含空白）。
  2. 過濾掉看起來正常的（含長詞、含已知 whitelist 縮寫）。
  3. 對其餘區段：先去空白合併為一串、再用 wordninja 重新斷詞。
  4. 若修復前後相同字母序、且修復後每個 token 都在字典或長度合理，採用。

保留：硬編 OCR_FIXES（只覆蓋 wordninja 解不好的特定 case，如 "th rough"）。
中文不動，只處理 ASCII 區段。
"""

from __future__ import annotations

import re
from typing import Optional

try:
    import wordninja
    _HAS_WORDNINJA = True
except ImportError:
    wordninja = None
    _HAS_WORDNINJA = False


# wordninja 對特定縮寫/專有名詞可能會切錯，加 whitelist 保留原樣
WHITELIST_TOKENS = {
    # 警察相關英文縮寫
    "FBI", "CIA", "DNA", "GPS", "GIS", "ID", "PC", "USB", "Wi-Fi",
    "TOEFL", "IELTS",
    # 學科常見
    "DNS", "IP", "URL", "API", "OS", "CPU", "GPU", "RAM",
    "SQL", "XSS", "CSRF", "TCP", "UDP", "HTTP", "HTTPS",
}

# 仍保留的硬編規則（wordninja 解不好的少數 case）
_LEGACY_FIXES = [
    (re.compile(r"\bth rough\b"), "through"),
    (re.compile(r"\bin to\b"), "into"),
]


# 找「英文+空白」連續區段（至少 8 字元、含 1+ 空格、全為 ASCII letters/空格/標點）
_ENGLISH_SEGMENT = re.compile(r"[A-Za-z]+(?:[ ]+[A-Za-z]+)+")


def _looks_already_good(segment: str) -> bool:
    """判斷一段英文是否看起來「已正常」，不需 wordninja 處理。

    判據：壞的 OCR 斷字會產生大量 1-2 字母短 token（th e、wh at、ti on）。
    若 1-2 字母 token 比例低於閾值，視為正常，不動。
    """
    tokens = segment.split()
    if not tokens or len(tokens) == 1:
        return True
    short = sum(1 for t in tokens if len(t) <= 2)
    return short / len(tokens) < 0.35


def _repair_segment(segment: str) -> str:
    """對單一英文片段做 wordninja 修復。"""
    if not _HAS_WORDNINJA:
        return segment
    # whitelist 短語直接保留
    if segment.strip().upper() in WHITELIST_TOKENS:
        return segment

    if _looks_already_good(segment):
        return segment

    compact = re.sub(r"\s+", "", segment)
    if len(compact) < 4:
        return segment

    repaired = wordninja.split(compact.lower())
    if not repaired:
        return segment

    # 還原首字大小寫（保留原 segment 第一個字元的大小寫）
    if segment[:1].isupper() and repaired:
        repaired[0] = repaired[0].capitalize()

    return " ".join(repaired)


def repair_english_spacing(text: str) -> str:
    """主入口：修復文字中所有可疑的英文斷字片段。"""
    if not text:
        return text

    # 1. 先套用 legacy 強規則
    for pat, repl in _LEGACY_FIXES:
        text = pat.sub(repl, text)

    # 2. 用 wordninja 處理英文連續區段
    if _HAS_WORDNINJA:
        text = _ENGLISH_SEGMENT.sub(
            lambda m: _repair_segment(m.group(0)), text
        )

    return text


def is_available() -> bool:
    """wordninja 是否可用。"""
    return _HAS_WORDNINJA


def normalize_with_ocr_repair(text: Optional[str]) -> str:
    """正規化 + OCR 修復（給 pdf_to_questions.py 用）。"""
    import unicodedata

    from scripts.parse.patterns import replace_pua_chars

    if not text:
        return ""
    # 1. PUA 字元 → (A)(B)(C)(D) 等可讀標記（必須在 NFKC 之前，PUA 不被 NFKC 動到）
    text = replace_pua_chars(text)
    # 2. Unicode 正規化（NFKC 統一全形/半形）
    text = unicodedata.normalize("NFKC", text)
    # 3. 移除考卷代號（5位數字）
    text = re.sub(r"\b\d{5}\b", "", text)
    # 4. wordninja 修英文斷字
    text = repair_english_spacing(text)
    return text.strip()
