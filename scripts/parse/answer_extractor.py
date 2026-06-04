# -*- coding: utf-8 -*-
"""
解析「答案.pdf」「更正答案.pdf」 → {題號: 答案}。

考選部標準答案 PDF 格式（規律）：
    題號 第1題 第2題 第3題 ... 第10題
    答案 A B C A B C D C C B
    題號 第11題 ...
    答案 ...

特殊值處理（README 說明）：
  * 「送分」 — 該題所有考生均給分
  * 「A或B」 / 「A,B」 / 「AB」 — 多答案皆給分
  * 空白 — 該題未公布
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# 題號行：「題號 第1題 第2題 ...」或「題號 第 1 題 第 2 題 ...」
_QUESTION_NUM_RE = re.compile(r"第\s*(\d{1,3})\s*題")
# 答案 token：「A」/「B」/「送分」/「A或B」/「A,B」/「AB」
_ANSWER_TOKEN_RE = re.compile(r"送分|[A-D](?:[,、或][A-D])?|[A-D]{2,}")

# 多答案標記：A或B、A,B、A、B、AB
_MULTI_ANSWER_SPLIT_RE = re.compile(r"[,、或]")


AnswerValue = Union[str, List[str], None]


def normalize_answer(raw: str) -> AnswerValue:
    """把答案 raw token 標準化。

    規則：
      * 「送分」 → None（送分等於該題作廢，沒有正確答案）
      * 「A或B」 / 「A,B」 / 「A、B」 → ["A", "B"]
      * 「AB」 / 「AC」 → ["A", "B"] / ["A", "C"]
      * 「A」 → "A"（單一答案保留 str）
    """
    if not raw:
        return None
    raw = raw.strip()
    if raw == "送分":
        return None
    # 用分隔符切
    if any(sep in raw for sep in (",", "、", "或")):
        parts = [p.strip() for p in _MULTI_ANSWER_SPLIT_RE.split(raw)]
        labels = [p for p in parts if p in {"A", "B", "C", "D"}]
        return labels if len(labels) > 1 else (labels[0] if labels else None)
    # 連寫多答案如「AB」「ACD」
    if len(raw) > 1 and all(c in "ABCD" for c in raw):
        return list(raw)
    if raw in {"A", "B", "C", "D"}:
        return raw
    return raw  # 未知格式保留 raw（避免資料丟失）


def parse_answer_pdf(pdf_path: str | Path, normalize: bool = True) -> Dict[int, Any]:
    """從答案 PDF 抽出 {題號: 答案} 對應表。

    Args:
        normalize: True 則套用 normalize_answer（送分→None, AB→list）
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {}

    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber 未安裝，無法解析答案 PDF")
        return {}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            full_text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            )
    except Exception as e:
        logger.warning(f"答案 PDF 讀取失敗 {pdf_path}: {e}")
        return {}

    raw = parse_answer_text(full_text)
    if normalize:
        return {k: normalize_answer(v) for k, v in raw.items()}
    return raw


def parse_answer_text(text: str) -> Dict[int, str]:
    """從 raw text 抽出 {題號: 答案}（給單元測試）。"""
    if not text:
        return {}

    answers: Dict[int, str] = {}
    lines = text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 找「題號 第X題 ...」行
        nums = _QUESTION_NUM_RE.findall(line)
        if nums and line.startswith("題號"):
            question_nums = [int(n) for n in nums]
            # 下一個「答案 ...」行
            if i + 1 < len(lines):
                ans_line = lines[i + 1].strip()
                if ans_line.startswith("答案"):
                    # 去掉開頭「答案」並取 token
                    body = ans_line[len("答案"):].strip()
                    tokens = _ANSWER_TOKEN_RE.findall(body)
                    for q_num, ans in zip(question_nums, tokens):
                        answers[q_num] = ans
                    i += 2
                    continue
        i += 1

    return answers


def find_answer_pdf(
    question_pdf_path: Path,
    prefer_corrected: bool = True,
) -> Optional[Path]:
    """從 試題.pdf 路徑找同目錄的答案 PDF。

    優先順序（prefer_corrected=True 時）：
      1. 更正答案.pdf（官方公布勘誤後版本）
      2. 答案.pdf
    """
    parent = Path(question_pdf_path).parent
    if prefer_corrected:
        corrected = parent / "更正答案.pdf"
        if corrected.exists():
            return corrected
    answer = parent / "答案.pdf"
    if answer.exists():
        return answer
    return None


def merge_answers_into_questions(
    questions: list, answers: Dict[int, str]
) -> int:
    """把答案 merge 到 questions[].answer。回傳合併數量。"""
    merged = 0
    for q in questions:
        if q.get("type") != "choice":
            continue
        num = q.get("number")
        if isinstance(num, int) and num in answers:
            q["answer"] = answers[num]
            merged += 1
    return merged
