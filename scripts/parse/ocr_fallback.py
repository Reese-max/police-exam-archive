# -*- coding: utf-8 -*-
"""
OCR fallback：當 pdfplumber 抽不到夠多文字時，把 PDF page 渲染成圖再 OCR。

引擎選擇（pip install 即用，無外部 binary 依賴）：
  - PDF 渲染：PyMuPDF (fitz)
  - OCR：rapidocr-onnxruntime（內建 PP-OCRv4 中文 + 英文模型）

呼叫端用法：
    from scripts.parse.ocr_fallback import ocr_pdf_pages, needs_ocr

    pages_text = pdfplumber 抽到的 [str, ...]
    if needs_ocr(pages_text):
        pages_text = ocr_pdf_pages(pdf_path)

結果快取在 cache/ocr/{sha256}.json。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# 每頁文字少於此值視為「OCR 失敗」（pdfplumber 抽不到夠多文字）
MIN_CHARS_PER_PAGE = 50
# 整份 PDF 平均每頁低於此值才觸發 OCR fallback（避免單頁瑕疵就整檔重 OCR）
MIN_AVG_CHARS = 100


def needs_ocr(pages_text: List[str]) -> bool:
    """判斷是否需要 OCR fallback。"""
    if not pages_text:
        return True
    total = sum(len(t.strip()) for t in pages_text if t)
    avg = total / len(pages_text)
    return avg < MIN_AVG_CHARS


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(pdf_path: Path, cache_dir: Optional[Path]) -> Path:
    cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "cache" / "ocr"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = _sha256(pdf_path)
    return cache_dir / f"{digest}.json"


def _load_cache(cache_file: Path) -> Optional[List[str]]:
    if not cache_file.exists():
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(cache_file: Path, pages: List[str]) -> None:
    try:
        cache_file.write_text(
            json.dumps(pages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"OCR cache 寫入失敗 {cache_file}: {e}")


def _render_pdf_to_images(pdf_path: Path, dpi: int = 200):
    """PDF 各頁渲染成 numpy array (RGB)。需 PyMuPDF。"""
    import fitz  # PyMuPDF
    import numpy as np

    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)

    images = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            images.append(img)
    return images


def _ocr_image(image, ocr_engine) -> str:
    """單張圖跑 OCR，回傳 text。"""
    result, _ = ocr_engine(image)
    if not result:
        return ""
    # rapidocr 回傳 [[box, text, score], ...]
    return "\n".join(line[1] for line in result if len(line) >= 2)


def ocr_pdf_pages(
    pdf_path: str | Path,
    dpi: int = 200,
    cache_dir: Optional[Path] = None,
    force: bool = False,
) -> List[str]:
    """對整份 PDF 跑 OCR，回傳每頁文字。

    Args:
        pdf_path: PDF 路徑
        dpi: 渲染解析度（200 對中文 OCR 是合理起點）
        cache_dir: 自訂快取目錄（預設 <project>/cache/ocr）
        force: 忽略快取強制重做

    Returns:
        每頁的 OCR 文字 list
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    cache_file = _cache_path(pdf_path, cache_dir)
    if not force:
        cached = _load_cache(cache_file)
        if cached is not None:
            logger.info(f"使用快取 OCR 結果: {pdf_path.name}")
            return cached

    # 延遲 import 避免 module load 時就要求所有依賴都在
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        raise ImportError(
            "OCR fallback 需要 rapidocr-onnxruntime: "
            "pip install rapidocr-onnxruntime"
        ) from e

    logger.info(f"開始 OCR: {pdf_path.name}")
    ocr = RapidOCR()
    images = _render_pdf_to_images(pdf_path, dpi=dpi)

    pages = []
    for idx, img in enumerate(images, 1):
        text = _ocr_image(img, ocr)
        pages.append(text)
        logger.debug(f"  page {idx}/{len(images)}: {len(text)} chars")

    _save_cache(cache_file, pages)
    return pages


def extract_text_with_fallback(
    pdf_path: str | Path,
    extract_func,
    enable_ocr: bool = True,
) -> tuple[List[str], bool]:
    """主入口：先用 pdfplumber，失敗或文字過少時 fallback 到 OCR。

    Args:
        pdf_path: PDF 路徑
        extract_func: 主抽文字函數 (pdf_path -> List[str])
        enable_ocr: 是否啟用 OCR fallback

    Returns:
        (pages_text, used_ocr) tuple
    """
    pages = extract_func(pdf_path) or []
    if not enable_ocr:
        return pages, False
    if not needs_ocr(pages):
        return pages, False

    try:
        ocr_pages = ocr_pdf_pages(pdf_path)
        if ocr_pages and any(p.strip() for p in ocr_pages):
            return ocr_pages, True
    except ImportError as e:
        logger.warning(f"OCR 依賴缺失，跳過 fallback: {e}")
    except Exception as e:
        logger.warning(f"OCR 失敗 {pdf_path}: {e}")

    return pages, False
