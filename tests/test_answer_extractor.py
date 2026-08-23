# -*- coding: utf-8 -*-
"""answer_extractor.py 測試。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parse.answer_extractor import (  # noqa: E402
    _declared_single_choice_count,
    find_answer_pdf,
    merge_answers_into_questions,
    normalize_answer,
    parse_answer_table,
    parse_answer_text,
)


class TestNormalizeAnswer:
    def test_single(self):
        assert normalize_answer("A") == "A"
        assert normalize_answer("Ｄ") == "D"

    def test_song_fen_kept_as_database_value(self):
        assert normalize_answer("送分") == "送分"
        assert normalize_answer("一律給分") == "送分"

    def test_multi_answer(self):
        assert normalize_answer("A或B") == "A或B"
        assert normalize_answer("Ａ、Ｃ") == "A或C"
        assert normalize_answer("A,B") == "A或B"
        assert normalize_answer("ACD") == "A或C或D"

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
        text = """
題號 第1題 第2題 第3題
答案 A B C
題號 第11題 第12題 第13題
答案
"""
        out = parse_answer_text(text)
        assert out == {1: "A", 2: "B", 3: "C"}

    def test_correction_notes(self):
        text = (
            "第4題答Ａ或Ｃ者均給分。"
            "第6題答Ａ或Ｃ或Ｄ者均給分。"
            "第24題一律給分。"
            "第23題答Ｂ給分，第25題一律給分。"
        )
        out = parse_answer_text(text)
        assert out == {
            4: "A或C",
            6: "A或C或D",
            23: "B",
            24: "送分",
            25: "送分",
        }

    def test_empty_text(self):
        assert parse_answer_text("") == {}

    def test_declared_single_choice_count(self):
        text = "單選題數：25題 單選每題配分：2.00分"
        assert _declared_single_choice_count(text) == 25
        assert _declared_single_choice_count("單選題數: 60 題") == 60
        assert _declared_single_choice_count("沒有題數宣告") is None


class TestParseAnswerTable:
    def test_two_row_table(self):
        rows = [
            ["題號", "第1題", "第2題", "第3題"],
            ["答案", "A", "Ｂ", "送分"],
        ]
        assert parse_answer_table(rows) == {1: "A", 2: "B", 3: "送分"}

    def test_row_per_question_table(self):
        rows = [["1", "A"], ["2", "C"]]
        assert parse_answer_table(rows) == {1: "A", 2: "C"}


class TestFindAnswerPdf:
    def test_prefer_corrected(self, tmp_path):
        question = tmp_path / "試題.pdf"
        question.touch()
        answer = tmp_path / "答案.pdf"
        answer.touch()
        corrected = tmp_path / "更正答案.pdf"
        corrected.touch()
        assert find_answer_pdf(question) == corrected

    def test_fallback_to_answer(self, tmp_path):
        question = tmp_path / "試題.pdf"
        question.touch()
        answer = tmp_path / "答案.pdf"
        answer.touch()
        assert find_answer_pdf(question) == answer

    def test_none_found(self, tmp_path):
        question = tmp_path / "試題.pdf"
        question.touch()
        assert find_answer_pdf(question) is None


class TestMerge:
    def test_merge_into_choice(self):
        questions = [
            {"number": 1, "type": "choice"},
            {"number": 2, "type": "choice"},
            {"number": "一", "type": "essay"},
        ]
        count = merge_answers_into_questions(questions, {1: "A或C", 2: "送分"})
        assert count == 2
        assert questions[0]["answer"] == "A或C"
        assert questions[1]["answer"] == "送分"
        assert "answer" not in questions[2]

    def test_skip_essay(self):
        questions = [{"number": "一", "type": "essay"}]
        count = merge_answers_into_questions(questions, {1: "A"})
        assert count == 0
