# -*- coding: utf-8 -*-
"""audit_json.py 測試"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit.audit_json import audit_directory, audit_file  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _good_payload():
    return {
        "metadata": {"subject": "test"},
        "subject": "test",
        "source_pdf": "x.pdf",
        "questions": [
            {
                "number": 1,
                "type": "choice",
                "stem": "題1?",
                "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                "answer": "A",
            },
            {
                "number": 2,
                "type": "choice",
                "stem": "題2?",
                "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                "answer": "B",
            },
        ],
        "_quality": {"score": 0.9, "issues": []},
    }


class TestAuditFile:
    def test_perfect(self, tmp_path):
        f = tmp_path / "試題.json"
        _write_json(f, _good_payload())
        issues = audit_file(f)
        assert issues == []

    def test_missing_questions(self, tmp_path):
        f = tmp_path / "試題.json"
        d = _good_payload()
        d["questions"] = []
        _write_json(f, d)
        issues = audit_file(f)
        codes = [i.code for i in issues]
        assert "no_questions" in codes

    def test_low_quality(self, tmp_path):
        f = tmp_path / "試題.json"
        d = _good_payload()
        d["_quality"]["score"] = 0.5
        _write_json(f, d)
        issues = audit_file(f, threshold=0.7)
        assert any(i.code == "low_quality_score" for i in issues)

    def test_invalid_answer(self, tmp_path):
        f = tmp_path / "試題.json"
        d = _good_payload()
        d["questions"][0]["answer"] = 123  # 非法
        _write_json(f, d)
        issues = audit_file(f)
        assert any(i.code == "invalid_answer" for i in issues)

    def test_multi_answer_list_valid(self, tmp_path):
        f = tmp_path / "試題.json"
        d = _good_payload()
        d["questions"][0]["answer"] = ["A", "B"]  # 合法
        _write_json(f, d)
        issues = audit_file(f)
        assert not any(i.code == "invalid_answer" for i in issues)

    def test_null_answer_valid(self, tmp_path):
        f = tmp_path / "試題.json"
        d = _good_payload()
        d["questions"][0]["answer"] = None  # 送分 → null 合法
        _write_json(f, d)
        issues = audit_file(f)
        assert not any(i.code == "invalid_answer" for i in issues)

    def test_unreadable(self, tmp_path):
        f = tmp_path / "試題.json"
        f.write_text("not valid json {{", encoding="utf-8")
        issues = audit_file(f)
        assert any(i.code == "unreadable" for i in issues)


class TestAuditDirectory:
    def test_all_pass(self, tmp_path):
        for i in range(3):
            _write_json(tmp_path / f"sub{i}" / "試題.json", _good_payload())
        r = audit_directory(tmp_path)
        assert r.total_files == 3
        assert r.pass_count == 3
        assert r.fail_count == 0

    def test_mixed(self, tmp_path):
        _write_json(tmp_path / "ok" / "試題.json", _good_payload())
        bad = _good_payload()
        bad["_quality"]["score"] = 0.2
        _write_json(tmp_path / "bad" / "試題.json", bad)
        r = audit_directory(tmp_path)
        assert r.total_files == 2
        assert r.pass_count == 1
        assert r.fail_count == 1
