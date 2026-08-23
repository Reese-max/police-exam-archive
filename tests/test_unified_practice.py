#!/usr/bin/env python3
"""統一搜尋／練習站的資料契約與防回歸測試。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "考古題庫"
SUBJECT = "中華民國憲法與警察專業英文"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair = load_module(
    "fix_115_common_english",
    PROJECT_ROOT / "scripts" / "repair" / "fix_115_common_english.py",
)
index_builder = load_module(
    "build_search_index_v2",
    PROJECT_ROOT / "scripts" / "build_search_index.py",
)


@pytest.fixture(scope="module")
def search_index():
    return index_builder.build_index(DATA_DIR)


def row(search_index: dict, *, year: int, subject: str, number: str) -> dict:
    columns = search_index["columns"]
    for index, value in enumerate(columns["no"]):
        if (
            value == number
            and columns["yr"][index] == year
            and columns["sub"][index] == subject
        ):
            return {field: columns[field][index] for field in search_index["fields"]}
    raise AssertionError(f"找不到 {year} 年 {subject} 第 {number} 題")


def test_all_common_english_copies_match_official_fixture():
    for category in repair.CATEGORIES:
        path = DATA_DIR / category / "115年" / SUBJECT / "試題.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        questions = {
            question["number"]: question
            for question in document["questions"]
            if isinstance(question, dict) and isinstance(question.get("number"), int)
        }
        for number, expected in repair.OFFICIAL.items():
            assert repair.normalized_projection(questions[number]) == expected, (
                f"{path.relative_to(PROJECT_ROOT)} 第 {number} 題與官方 fixture 不符"
            )


def test_search_index_schema_v2(search_index):
    assert search_index["v"] == 2
    assert search_index["fields"] == index_builder.FIELDS
    assert "passage" in search_index["columns"]
    assert "cats" in search_index["columns"]
    length = search_index["stats"]["total"]
    assert all(len(values) == length for values in search_index["columns"].values())


def test_common_paper_keeps_every_category_membership(search_index):
    item = row(search_index, year=115, subject=SUBJECT, number="51")
    assert set(item["cats"]) == set(repair.CATEGORIES)
    assert set(repair.CATEGORIES).issubset(search_index["facets"]["categories"])


def test_reading_passages_and_question_50_are_clean(search_index):
    q50 = row(search_index, year=115, subject=SUBJECT, number="50")
    q51 = row(search_index, year=115, subject=SUBJECT, number="51")
    q56 = row(search_index, year=115, subject=SUBJECT, number="56")

    assert q50["optD"] == "deter"
    assert "請依下文" not in q50["optD"]
    assert not q50["passage"]
    assert all(f"[[{number}]]" in q51["passage"] for number in range(51, 56))
    assert "Zero Trust" in q56["passage"]
    assert "seeing is no longer believing" in q56["passage"]


def test_unified_frontend_files_reference_shared_engine():
    website = PROJECT_ROOT / "考古題網站"
    practice = (website / "practice.html").read_text(encoding="utf-8")
    search = (website / "search.html").read_text(encoding="utf-8")
    quiz = (website / "quiz.html").read_text(encoding="utf-8")
    answer_utils = (website / "js" / "answer-utils.js").read_text(encoding="utf-8")

    assert 'src="js/answer-utils.js"' in practice
    assert 'src="js/search-engine.js"' in practice
    assert "q.passage" in practice
    assert "AnswerUtils.isCorrect" in practice
    assert 'src="js/answer-utils.js"' in search
    assert "item.passage" in search
    assert "AnswerUtils.acceptedAnswers" in search
    assert "location.replace(target.href)" in quiz
    assert "acceptedAnswers" in answer_utils
    assert "isBonus" in answer_utils
