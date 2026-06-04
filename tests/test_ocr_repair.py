# -*- coding: utf-8 -*-
"""ocr_repair.py 單元測試"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from scripts.parse import ocr_repair as r  # noqa: E402


pytestmark = pytest.mark.skipif(
    not r.is_available(),
    reason="wordninja not installed",
)


class TestRepairEnglishSpacing:
    def test_th_rough(self):
        assert "through" in r.repair_english_spacing("walk th rough the park")

    def test_into(self):
        assert "into" in r.repair_english_spacing("step in to the room")

    def test_normal_english_untouched(self):
        good = "This is a normal English sentence."
        assert r.repair_english_spacing(good) == good

    def test_no_english_no_change(self):
        chinese = "下列何者屬於警察職務?"
        assert r.repair_english_spacing(chinese) == chinese


class TestNormalize:
    def test_strip_exam_code(self):
        assert "50110" not in r.normalize_with_ocr_repair("代號 50110 試題")

    def test_empty(self):
        assert r.normalize_with_ocr_repair("") == ""
        assert r.normalize_with_ocr_repair(None) == ""
