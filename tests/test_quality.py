# -*- coding: utf-8 -*-
"""quality.py 測試"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parse.quality import assess_quality  # noqa: E402


def _good_choice(n, stem="正常題幹？"):
    return {
        "number": n,
        "type": "choice",
        "stem": stem,
        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
    }


def _good_result(n_choices=20):
    return {
        "metadata": {"subject": "test"},
        "questions": [_good_choice(i + 1) for i in range(n_choices)],
    }


class TestAssessQuality:
    def test_perfect_score(self):
        r = assess_quality(_good_result(20))
        assert r.score == 1.0
        assert r.issues == []
        assert r.is_good()

    def test_no_questions(self):
        r = assess_quality({"metadata": {}, "questions": []})
        assert r.score == 0.0
        assert "no_questions_extracted" in r.issues
        assert not r.is_good()

    def test_too_few_questions(self):
        r = assess_quality({
            "metadata": {"x": 1},
            "questions": [_good_choice(1), _good_choice(2)],
        })
        assert r.score < 1.0
        assert any("too_few" in i for i in r.issues)

    def test_empty_stems(self):
        res = _good_result(20)
        for q in res["questions"][:5]:
            q["stem"] = ""
        r = assess_quality(res)
        assert r.empty_stems == 5
        assert any("empty_stems" in i for i in r.issues)
        assert r.score < 0.9

    def test_missing_options(self):
        res = _good_result(20)
        for q in res["questions"][:5]:
            q["options"] = {"A": "甲", "B": "乙"}  # 少 C, D
        r = assess_quality(res)
        assert r.missing_options == 5
        assert any("missing_options" in i for i in r.issues)

    def test_metadata_leak(self):
        res = _good_result(10)
        res["questions"][0]["stem"] = "代號：50120 依憲法規定..."
        r = assess_quality(res)
        assert r.metadata_leaks == 1
        assert any("metadata_leaks" in i for i in r.issues)

    def test_merged_question(self):
        # 合併題判定條件：stem > 800 字 + 含 2+ 個分數標記
        res = _good_result(10)
        res["questions"][0]["stem"] = "題一（15 分）" + "X" * 800 + "題二（20 分）"
        r = assess_quality(res)
        assert r.merged_questions == 1

    def test_long_stem_without_scores_not_merged(self):
        # 申論題含長表格但無多分數標記 → 不算 merged
        res = _good_result(10)
        res["questions"][0]["stem"] = "X" * 1000
        r = assess_quality(res)
        assert r.merged_questions == 0

    def test_truncated_stem(self):
        res = _good_result(10)
        res["questions"][0]["stem"] = "下列何者為，"
        res["questions"][1]["stem"] = "依規定，警察是"
        r = assess_quality(res)
        assert r.truncated_stems >= 2

    def test_no_metadata(self):
        res = {"questions": [_good_choice(i + 1) for i in range(20)]}
        r = assess_quality(res)
        assert not r.has_metadata
        assert any("no_metadata" in i for i in r.issues)

    def test_discontinuous_numbers(self):
        res = _good_result(0)
        res["questions"] = [_good_choice(1), _good_choice(2), _good_choice(5)]
        r = assess_quality(res)
        assert r.discontinuous

    def test_is_good_threshold(self):
        r = assess_quality(_good_result(20))
        assert r.is_good(0.7)
        assert r.is_good(1.0)
        # 製造一個低品質結果
        res = _good_result(20)
        for q in res["questions"][:10]:
            q["stem"] = ""
            q["options"] = {}
        r2 = assess_quality(res)
        assert not r2.is_good(0.7)
