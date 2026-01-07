from pathlib import Path

from auto_generate_form import (
    _infer_year_from_filename,
    _split_question_and_options,
    load_questions,
)


def test_split_question_and_options_parses_inline_content():
    text = """1. 測試題目
A) 選項一
B．選項二
C、選項三
D 選項四"""

    question, options = _split_question_and_options(text)

    assert question == "測試題目"
    assert options["A"] == "選項一"
    assert options["B"] == "選項二"
    assert options["C"] == "選項三"
    assert options["D"] == "選項四"


def test_load_questions_handles_missing_columns_and_reports(tmp_path):
    csv_content = """年份,試題編號,題幹,選項A,選項B,選項C,選項D,標準答案
2025,1,第一題,甲,乙,丙,丁,A
2025,2,"2. 第二題
 甲
 乙
 丙
 丁",,,,,c
2025,3,,甲,乙,丙,丁,B
2025,4,第四題,甲,乙,丙,丁,E
"""
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    questions, report = load_questions(csv_path)

    assert report.total_rows == 4
    assert report.imported == 3
    assert report.skipped == 1
    assert any("第 4 行缺少題目內容" in warning for warning in report.warnings)
    assert any("答案格式不正確" in warning for warning in report.warnings)
    assert questions[1].option_a == "甲"
    assert questions[1].answer == "C"
    assert questions[-1].answer == "A"


def test_load_questions_infers_year_and_number(tmp_path):
    csv_content = """題目,選項A,選項B,選項C,選項D,標準答案
第一題,甲,乙,丙,丁,A
"""
    csv_path = tmp_path / "110年測試.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    questions, report = load_questions(csv_path)

    assert questions[0].year == "110"
    assert questions[0].number == "1"
    assert any("缺少年份欄位" in warning for warning in report.warnings)


def test_split_question_and_options_returns_empty_when_no_options():
    question, options = _split_question_and_options("單純題目")
    assert question == ""
    assert options == {}


def test_infer_year_from_filename():
    assert _infer_year_from_filename(Path("110年測試.csv")) == "110"
    assert _infer_year_from_filename(Path("demo.csv")) == ""
