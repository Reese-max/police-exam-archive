# -*- coding: utf-8 -*-
"""ocr_fallback.py 基本邏輯測試（不需 OCR 依賴）"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parse import ocr_fallback as ofb  # noqa: E402


class TestNeedsOcr:
    def test_empty_list(self):
        assert ofb.needs_ocr([]) is True

    def test_very_few_chars(self):
        # 平均 < 100 字元/頁 → 觸發 OCR
        assert ofb.needs_ocr(["小", "短", ""]) is True

    def test_enough_chars(self):
        # 平均 > 100 字元/頁 → 不需 OCR
        page = "這是一段足夠長的文字" * 30
        assert ofb.needs_ocr([page, page]) is False


class TestFallbackOrchestration:
    def test_pdfplumber_success_no_ocr(self, tmp_path):
        long_page = "正常文字內容" * 50

        def fake_extract(_):
            return [long_page, long_page]

        pages, used_ocr = ofb.extract_text_with_fallback(
            tmp_path / "fake.pdf", fake_extract, enable_ocr=True
        )
        assert pages == [long_page, long_page]
        assert used_ocr is False

    def test_disable_ocr_returns_raw(self, tmp_path):
        def fake_extract(_):
            return [""]

        pages, used_ocr = ofb.extract_text_with_fallback(
            tmp_path / "fake.pdf", fake_extract, enable_ocr=False
        )
        assert pages == [""]
        assert used_ocr is False
