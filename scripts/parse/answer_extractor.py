# -*- coding: utf-8 -*-
"""解析考選部「答案.pdf」「更正答案.pdf」並合併至題目資料。

支援：
- 標準答案表格（題號列／答案列）
- pdfplumber 表格抽取結果
- 更正答案文字，例如「第4題答Ａ或Ｃ者均給分」
- 送分與多答案，統一輸出為資料庫既有字串格式
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

_QUESTION_NUM_RE = re.compile(r"第\s*(\d{1,3})\s*題")
_ANSWER_TOKEN_RE = re.compile(
    r"送分|[A-DＡ-Ｄ](?:(?:\s*[或、,，/／]\s*|\s*)[A-DＡ-Ｄ]){0,3}"
)
_FULLWIDTH_TRANS = str.maketrans({
    "Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D",
    "，": ",", "／": "/",
})


def _unique_labels(raw: str) -> List[str]:
    labels: List[str] = []
    for label in re.findall(r"[A-D]", raw):
        if label not in labels:
            labels.append(label)
    return labels


def normalize_answer(raw: object) -> Optional[str]:
    """將答案正規化為 A/B/C/D、A或C、A或C或D 或「送分」。"""
    if raw is None:
        return None
    text = str(raw).translate(_FULLWIDTH_TRANS).strip().upper()
    text = re.sub(r"\s+", "", text)
    if not text:
        return None
    if "送分" in text or "一律給分" in text:
        return "送分"

    labels = _unique_labels(text)
    if not labels:
        return None
    return "或".join(labels)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _numbers_from_cells(cells: Iterable[object]) -> List[int]:
    numbers: List[int] = []
    for cell in cells:
        text = _cell_text(cell)
        found = _QUESTION_NUM_RE.findall(text)
        if found:
            numbers.extend(int(n) for n in found)
            continue
        if re.fullmatch(r"\d{1,3}", text):
            numbers.append(int(text))
    return numbers


def _answers_from_cells(cells: Iterable[object]) -> List[str]:
    answers: List[str] = []
    for cell in cells:
        text = _cell_text(cell)
        if not text:
            continue
        normalized = normalize_answer(text)
        if normalized:
            answers.append(normalized)
    return answers


def parse_answer_table(rows: Iterable[Iterable[object]]) -> Dict[int, str]:
    """解析 pdfplumber.extract_tables() 回傳的單一表格。"""
    normalized_rows = [list(row) for row in rows if row]
    answers: Dict[int, str] = {}

    # 常見格式：題號列的下一列是答案列。
    for index, row in enumerate(normalized_rows):
        joined = " ".join(_cell_text(c) for c in row)
        if "題號" not in joined:
            continue
        numbers = _numbers_from_cells(row)
        if not numbers:
            continue
        for answer_row in normalized_rows[index + 1:index + 3]:
            answer_joined = " ".join(_cell_text(c) for c in answer_row)
            if "答案" not in answer_joined:
                continue
            values = _answers_from_cells(answer_row[1:] if len(answer_row) > 1 else answer_row)
            for number, value in zip(numbers, values):
                answers[number] = value
            break

    # 備援格式：每列直接是「題號、答案」。
    for row in normalized_rows:
        if len(row) < 2:
            continue
        numbers = _numbers_from_cells(row[:1])
        values = _answers_from_cells(row[1:])
        if len(numbers) == 1 and values:
            answers.setdefault(numbers[0], values[0])

    return answers


def _parse_correction_notes(text: str) -> Dict[int, str]:
    """解析更正答案的自然語句。"""
    normalized = text.translate(_FULLWIDTH_TRANS)
    out: Dict[int, str] = {}

    award_pattern = re.compile(
        r"第\s*(\d{1,3})\s*題\s*答\s*"
        r"([A-D](?:\s*[或、,，/／]\s*[A-D]){0,3})"
        r"\s*(?:者)?\s*(?:均)?\s*給分"
    )
    for match in award_pattern.finditer(normalized):
        value = normalize_answer(match.group(2))
        if value:
            out[int(match.group(1))] = value

    all_credit_pattern = re.compile(
        r"第\s*(\d{1,3})\s*題\s*(?:一律給分|送分)"
    )
    for match in all_credit_pattern.finditer(normalized):
        out[int(match.group(1))] = "送分"

    return out


def parse_answer_text(text: str) -> Dict[int, str]:
    """從抽出的純文字解析標準答案與更正說明。"""
    if not text:
        return {}

    normalized = text.translate(_FULLWIDTH_TRANS)
    answers: Dict[int, str] = {}
    lines = normalized.splitlines()

    index = 0
    while index < len(lines):
        line = re.sub(r"\s+", " ", lines[index]).strip()
        numbers = [int(n) for n in _QUESTION_NUM_RE.findall(line)]
        if numbers and "題號" in line:
            # 有些 PDF 會在題號列與答案列之間插入空白列。
            for next_index in range(index + 1, min(index + 4, len(lines))):
                answer_line = re.sub(r"\s+", " ", lines[next_index]).strip()
                if "答案" not in answer_line:
                    continue
                body = answer_line.split("答案", 1)[1]
                raw_tokens = _ANSWER_TOKEN_RE.findall(body)
                values = [normalize_answer(token) for token in raw_tokens]
                values = [value for value in values if value]
                for number, value in zip(numbers, values):
                    answers[number] = value
                index = next_index
                break
        index += 1

    # 更正說明必須覆蓋原答案。
    answers.update(_parse_correction_notes(normalized))
    return answers


def _parse_pdf_only(pdf_path: Path) -> Dict[int, str]:
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber 未安裝，無法解析答案 PDF")
        return {}

    text_parts: List[str] = []
    table_answers: Dict[int, str] = {}
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
                try:
                    for table in page.extract_tables() or []:
                        table_answers.update(parse_answer_table(table))
                except Exception as exc:
                    logger.debug("答案表格抽取失敗 %s: %s", pdf_path, exc)
    except Exception as exc:
        logger.warning("答案 PDF 讀取失敗 %s: %s", pdf_path, exc)
        return {}

    text_answers = parse_answer_text("\n".join(text_parts))
    # 表格通常較準；更正文字必須最後覆蓋。
    merged = dict(text_answers)
    merged.update(table_answers)
    merged.update(_parse_correction_notes("\n".join(text_parts)))
    return merged


def parse_answer_pdf(pdf_path: str | Path, normalize: bool = True) -> Dict[int, str]:
    """解析答案 PDF；若是更正答案，先載入一般答案再套用更正。"""
    path = Path(pdf_path)
    if not path.exists():
        return {}

    answers: Dict[int, str] = {}
    if path.name == "更正答案.pdf":
        base = path.parent / "答案.pdf"
        if base.exists():
            answers.update(_parse_pdf_only(base))
    answers.update(_parse_pdf_only(path))

    if normalize:
        normalized: Dict[int, str] = {}
        for number, value in answers.items():
            result = normalize_answer(value)
            if result:
                normalized[number] = result
        return normalized
    return answers


def find_answer_pdf(
    question_pdf_path: Path,
    prefer_corrected: bool = True,
) -> Optional[Path]:
    """尋找同目錄答案；更正答案優先，解析時會自動疊加一般答案。"""
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
    questions: list,
    answers: Dict[int, str],
) -> int:
    """把答案合併至選擇題，回傳成功合併題數。"""
    merged = 0
    for question in questions:
        if question.get("type") != "choice":
            continue
        number = question.get("number")
        if isinstance(number, int) and number in answers:
            question["answer"] = answers[number]
            merged += 1
    return merged
