#!/usr/bin/env python3
"""115 年修補回歸測試。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_search_index import build_index

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "考古題庫"


def test_search_index_preserves_passages_and_memberships(tmp_path):
    index = build_index(DATA)
    assert index["v"] == 2
    assert "passage" in index["fields"]
    assert "cats" in index["fields"]
    columns = index["columns"]
    rows = [
        i for i, (year, subject, number) in enumerate(zip(columns["yr"], columns["sub"], columns["no"]))
        if year == 115 and subject == "中華民國憲法與警察專業英文" and number == "51"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert "[[51]]" in columns["passage"][row]
    assert len(columns["cats"][row]) > 1


def test_all_115_documents_have_official_subject_and_categories():
    paths = sorted(DATA.glob("*/115年/*/試題.json"))
    assert len(paths) == 90
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        metadata = document["metadata"]
        assert metadata["official_subject"]
        assert document["categories"] == metadata["categories"]
        assert path.relative_to(DATA).parts[0] in document["categories"]


def test_common_english_contract():
    paths = sorted(DATA.glob("*/115年/中華民國憲法與警察專業英文/試題.json"))
    assert paths
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        by_number = {q["number"]: q for q in document["questions"] if q.get("type") == "choice"}
        assert by_number[50]["options"]["D"] == "deter"
        for number in range(51, 56):
            assert by_number[number]["passage"].count(f"[[{number}]]") == 1
        for number in range(56, 61):
            assert "Zero Trust" in by_number[number]["passage"]
