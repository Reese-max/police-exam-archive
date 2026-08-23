#!/usr/bin/env python3
"""從考古題庫 JSON 生成前端搜尋／練習索引。

索引採 column-oriented 格式，schema v2 新增：
- ``cats``：同一份共用考卷所屬的全部類科
- ``passage``：克漏字與閱讀測驗共用文章

用法：
    python scripts/build_search_index.py
    python scripts/build_search_index.py --output /tmp/search-index.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站" / "data" / "search-index.json"

FIELDS = [
    "cat",
    "cats",
    "yr",
    "sub",
    "no",
    "type",
    "stem",
    "passage",
    "optA",
    "optB",
    "optC",
    "optD",
    "ans",
]


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"  SKIP {path}: {exc}", file=sys.stderr)
        return None
    return value if isinstance(value, dict) else None


def _path_metadata(path: Path, data_dir: Path, document: dict[str, Any]) -> tuple[str, int | None, str]:
    rel = path.relative_to(data_dir)
    parts = rel.parts
    category = str(document.get("category") or (parts[0] if len(parts) > 0 else ""))
    subject = str(document.get("subject") or (parts[2] if len(parts) > 2 else ""))
    year = document.get("year")
    if not isinstance(year, int):
        year_text = parts[1].removesuffix("年") if len(parts) > 1 else ""
        year = int(year_text) if year_text.isdigit() else None
    return category, year, subject


def _relative_subject_key(path: Path, data_dir: Path) -> str:
    return path.parent.relative_to(data_dir).as_posix().strip("/")


def _canonical_key(document: dict[str, Any], own_key: str) -> str:
    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    duplicate_of = document.get("_duplicate_of") or metadata.get("_duplicate_of")
    if not duplicate_of:
        return own_key
    value = str(duplicate_of).replace("\\", "/").strip("/")
    if value.startswith("考古題庫/"):
        value = value[len("考古題庫/") :]
    if value.endswith("/試題.json"):
        value = value[: -len("/試題.json")]
    return value


def _is_duplicate(document: dict[str, Any]) -> bool:
    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return bool(document.get("_is_duplicate") or metadata.get("_is_duplicate"))


def _load_documents(data_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    documents: list[tuple[Path, dict[str, Any]]] = []
    skipped = 0
    for path in sorted(data_dir.rglob("試題.json")):
        document = _read_json(path)
        if document is None:
            skipped += 1
            continue
        documents.append((path, document))
    if skipped:
        print(f"  跳過 {skipped} 個無法讀取的檔案", file=sys.stderr)
    return documents


def build_memberships(
    documents: list[tuple[Path, dict[str, Any]]],
    data_dir: Path,
) -> dict[str, list[str]]:
    """建立 canonical paper → 所有類科的關聯。"""
    memberships: dict[str, set[str]] = defaultdict(set)
    for path, document in documents:
        category, _, _ = _path_metadata(path, data_dir, document)
        own_key = _relative_subject_key(path, data_dir)
        canonical = _canonical_key(document, own_key)
        if category:
            memberships[canonical].add(category)

    return {key: sorted(values) for key, values in memberships.items()}


def load_exam_files(data_dir: Path) -> list[tuple[Any, ...]]:
    documents = _load_documents(data_dir)
    memberships = build_memberships(documents, data_dir)
    rows: list[tuple[Any, ...]] = []

    for path, document in documents:
        if _is_duplicate(document):
            continue

        category, year, subject = _path_metadata(path, data_dir, document)
        own_key = _relative_subject_key(path, data_dir)
        cats = memberships.get(own_key) or ([category] if category else [])

        questions = document.get("questions")
        if not isinstance(questions, list):
            continue
        for question in questions:
            if not isinstance(question, dict):
                continue
            qtype = str(question.get("type") or "")
            options = question.get("options") if qtype == "choice" else {}
            options = options if isinstance(options, dict) else {}
            rows.append(
                (
                    category,
                    cats,
                    year,
                    subject,
                    str(question.get("number", "")),
                    qtype,
                    str(question.get("stem") or ""),
                    str(question.get("passage") or ""),
                    str(options.get("A") or ""),
                    str(options.get("B") or ""),
                    str(options.get("C") or ""),
                    str(options.get("D") or ""),
                    str(question.get("answer") or "") if qtype == "choice" else "",
                )
            )
    return rows


def build_index(data_dir: Path) -> dict[str, Any]:
    rows = load_exam_files(data_dir)

    categories = sorted({category for row in rows for category in row[1] if category})
    subjects = sorted({row[3] for row in rows if row[3]})
    years = sorted({row[2] for row in rows if row[2]})

    columns = {
        field: [row[index] for row in rows]
        for index, field in enumerate(FIELDS)
    }

    return {
        "v": 2,
        "fields": FIELDS,
        "stats": {
            "total": len(rows),
            "choice": sum(1 for row in rows if row[5] == "choice"),
            "essay": sum(1 for row in rows if row[5] == "essay"),
            "categories": len(categories),
            "subjects": len(subjects),
        },
        "facets": {
            "categories": categories,
            "subjects": subjects,
            "years": years,
        },
        "columns": columns,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成前端搜尋／練習索引")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gzip", action="store_true", help="同時產出 .gz 壓縮版")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"資料目錄不存在：{data_dir}", file=sys.stderr)
        return 1

    print(f"正在掃描 {data_dir} ...")
    index = build_index(data_dir)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = output.stat().st_size / 1024

    if args.gzip:
        gz_path = output.with_suffix(".json.gz")
        with output.open("rb") as source, gzip.open(gz_path, "wb", compresslevel=9) as target:
            target.write(source.read())
        print(f"  gzip：{gz_path.stat().st_size / 1024:.0f} KB")

    print(f"\n已產出：{output}")
    print(f"  schema：v{index['v']}")
    print(f"  總題數：{index['stats']['total']}")
    print(f"  選擇題：{index['stats']['choice']}")
    print(f"  申論題：{index['stats']['essay']}")
    print(f"  類科數：{index['stats']['categories']}")
    print(f"  科目數：{index['stats']['subjects']}")
    print(f"  檔案大小：{size_kb:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
