# -*- coding: utf-8 -*-
"""answer_extractor.py 測試"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parse.answer_extractor import (  # noqa: E402
    find_answer_pdf,
    merge_answers_into_questions,
    normalize_answer,
    parse_answer_text,
)


class TestNormalizeAnswer:
    def test_single(self):
        assert normalize_answer("A") == "A"
        assert normalize_answer("D") == "D"

    def test_song_fen_to_none(self):
        assert normalize_answer("送分") is None

    def test_chinese_or(self):
        assert normalize_answer("A或B") == ["A", "B"]
        assert normalize_answer("A、B") == ["A", "B"]
        assert normalize_answer("A,B") == ["A", "B"]

    def test_concatenated(self):
        assert normalize_answer("AB") == ["A", "B"]
        assert normalize_answer("ACD") == ["A", "C", "D"]

    def test_empty(self):
        assert normalize_answer("") is None
        assert normalize_answer(None) is None


class TestParseAnswerText:
    def test_standard_format(self):
        text = """
題號 第1題 第2題 第3題 第4題 第5題
答案 A B C D A
"""
        out = parse_answer_text(text)
        assert out == {1: "A", 2: "B", 3: "C", 4: "D", 5: "A"}

    def test_multiple_blocks(self):
        text = """
題號 第1題 第2題 第3題
答案 A B C
題號 第4題 第5題 第6題
答案 D A B
"""
        out = parse_answer_text(text)
        assert out == {1: "A", 2: "B", 3: "C", 4: "D", 5: "A", 6: "B"}

    def test_blank_answers(self):
        # 後段未公布 → 不在結果中
        text = """
題號 第1題 第2題 第3題
答案 A B C
題號 第11題 第12題 第13題
答案
"""
        out = parse_answer_text(text)
        assert out == {1: "A", 2: "B", 3: "C"}

    def test_special_song_fen(self):
        text = "題號 第1題 第2題\n答案 送分 B"
        out = parse_answer_text(text)
        assert out == {1: "送分", 2: "B"}

    def test_multi_answer(self):
        text = "題號 第1題 第2題\n答案 A或B C"
        out = parse_answer_text(text)
        assert out == {1: "A或B", 2: "C"}

    def test_empty_text(self):
        assert parse_answer_text("") == {}


class TestFindAnswerPdf:
    def test_prefer_corrected(self, tmp_path):
        q = tmp_path / "試題.pdf"
        q.touch()
        ans = tmp_path / "答案.pdf"
        ans.touch()
        corrected = tmp_path / "更正答案.pdf"
        corrected.touch()
        assert find_answer_pdf(q) == corrected

    def test_fallback_to_answer(self, tmp_path):
        q = tmp_path / "試題.pdf"
        q.touch()
        ans = tmp_path / "答案.pdf"
        ans.touch()
        assert find_answer_pdf(q) == ans

    def test_none_found(self, tmp_path):
        q = tmp_path / "試題.pdf"
        q.touch()
        assert find_answer_pdf(q) is None


class TestMerge:
    def test_merge_into_choice(self):
        qs = [
            {"number": 1, "type": "choice"},
            {"number": 2, "type": "choice"},
            {"number": "一", "type": "essay"},
        ]
        n = merge_answers_into_questions(qs, {1: "A", 2: "B"})
        assert n == 2
        assert qs[0]["answer"] == "A"
        assert qs[1]["answer"] == "B"
        assert "answer" not in qs[2]

    def test_skip_essay(self):
        qs = [{"number": "一", "type": "essay"}]
        n = merge_answers_into_questions(qs, {1: "A"})
        assert n == 0
