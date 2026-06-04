# -*- coding: utf-8 -*-
"""
PDF 文字抽取器集合（主路徑：PyMuPDF，~10x 快於 pdfplumber）。

提供統一介面 ExtractorFn = (Path) -> List[str]，每元素為一頁文字。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger(__name__)


ExtractorFn = Callable[[Path], List[str]]


def extract_with_pymupdf(pdf_path: Path) -> List[str]:
    """用 PyMuPDF (fitz) 抽純文字。快、純 Python、無外部 binary。

    注意：對雙欄排版會交錯抓兩欄；雙欄 PDF 改用 extract_with_pymupdf_columns。
    """
    import fitz  # PyMuPDF

    pages: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            text = page.get_text("text")
            if text:
                pages.append(text)
    return pages


def _arrange_two_columns(
    blocks: list, page_width: float, margin_ratio: float = 0.10
) -> str:
    """雙欄 PDF reading order 重組。

    規則：
      - block 中心 x < 頁寬中線 → 左欄；> 中線 → 右欄
      - 同時跨左右兩側（x0 在左、x1 在右，且寬度足夠）→ full-width
      - full-width block 作為「分段點」：之前累積的左/右欄各自按 y 排序後 flush
      - 段內順序：先左欄（按 y） → 後右欄（按 y）
    """
    if not blocks:
        return ""

    mid = page_width / 2
    margin = page_width * margin_ratio

    output: list[str] = []
    pending_left: list[tuple[float, str]] = []
    pending_right: list[tuple[float, str]] = []

    def flush() -> None:
        for _, t in sorted(pending_left, key=lambda x: x[0]):
            output.append(t)
        for _, t in sorted(pending_right, key=lambda x: x[0]):
            output.append(t)
        pending_left.clear()
        pending_right.clear()

    # PyMuPDF blocks: (x0, y0, x1, y1, text, block_no, type)
    for b in sorted(blocks, key=lambda x: (x[1], x[0])):
        x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
        if not text or not text.strip():
            continue
        is_full = (x0 < mid - margin) and (x1 > mid + margin)
        if is_full:
            flush()
            output.append(text)
        elif (x0 + x1) / 2 < mid:
            pending_left.append((y0, text))
        else:
            pending_right.append((y0, text))

    flush()
    return "\n".join(t.rstrip() for t in output if t.strip())


def extract_with_pymupdf_columns(pdf_path: Path) -> List[str]:
    """PyMuPDF + 雙欄重組 reading order（適合考古題標準雙欄排版）。"""
    import fitz

    pages: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            blocks = page.get_text("blocks")
            # 只取文字 block（type 0）；圖片 block 為 1
            text_blocks = [b for b in blocks if len(b) < 7 or b[6] == 0]
            arranged = _arrange_two_columns(text_blocks, page.rect.width)
            if arranged:
                pages.append(arranged)
    return pages


def extract_with_pdfplumber(pdf_path: Path) -> List[str]:
    """用 pdfplumber 抽文字。表格較強但較慢；保留作 fallback。"""
    import pdfplumber

    pages: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return pages


def extract_with_pymupdf4llm(pdf_path: Path) -> List[str]:
    """用 pymupdf4llm 抽 markdown（保留標題/列表結構）。

    需安裝：pip install pymupdf4llm
    回傳每頁 markdown 文字。
    """
    import pymupdf4llm

    chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    return [c.get("text", "") for c in chunks if c.get("text")]


# 名字 → callable 對照（給 CLI 用）
EXTRACTORS: dict[str, ExtractorFn] = {
    "pymupdf": extract_with_pymupdf,
    "pymupdf-columns": extract_with_pymupdf_columns,
    "pdfplumber": extract_with_pdfplumber,
    "pymupdf4llm": extract_with_pymupdf4llm,
}


def get_extractor(name: str) -> ExtractorFn:
    """依名字取 extractor，未知則 fallback 至 pymupdf-columns。"""
    if name not in EXTRACTORS:
        logger.warning(f"未知 extractor '{name}'，fallback 至 pymupdf-columns")
        return extract_with_pymupdf_columns
    return EXTRACTORS[name]
