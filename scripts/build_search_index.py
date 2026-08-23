#!/usr/bin/env python3
"""從考古題庫 JSON 生成前端搜尋索引。"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站" / "data" / "search-index.json"

FIELDS = [
    "cat", "cats", "yr", "sub", "no", "type", "passage", "stem",
    "optA", "optB", "optC", "optD", "ans",
]


def _categories(document: dict[str, Any], fallback: str) -> list[str]:
    raw = document.get("categories")
    metadata = document.get("metadata")
    if not isinstance(raw, list) and isinstance(metadata, dict):
        raw = metadata.get("categories")
    values = [str(value).strip() for value in (raw or []) if str(value).strip()]
    if fallback and fallback not in values:
        values.append(fallback)
    return sorted(set(values))


def load_exam_files(data_dir: Path) -> list[tuple]:
    files = sorted(glob.glob(str(data_dir / "**" / "試題.json"), recursive=True))
    rows: list[tuple] = []
    skipped = 0

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  SKIP {fp}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        metadata = document.get("metadata") or {}
        if document.get("_is_duplicate") or metadata.get("_is_duplicate"):
            continue

        category = document.get("category", "")
        year = document.get("year")
        subject = document.get("subject", "")
        if not category or not year or not subject:
            rel = os.path.relpath(fp, str(data_dir))
            parts = rel.replace(os.sep, "/").split("/")
            category = category or (parts[0] if len(parts) > 0 else "")
            if not year:
                value = parts[1].replace("年", "") if len(parts) > 1 else ""
                year = int(value) if value.isdigit() else None
            subject = subject or (parts[2] if len(parts) > 2 else "")

        categories = _categories(document, category)
        for question in document.get("questions", []):
            qtype = question.get("type", "")
            options = question.get("options", {}) if qtype == "choice" else {}
            rows.append((
                category,
                categories,
                year,
                subject,
                str(question.get("number", "")),
                qtype,
                question.get("passage", ""),
                question.get("stem", ""),
                options.get("A", ""),
                options.get("B", ""),
                options.get("C", ""),
                options.get("D", ""),
                question.get("answer", "") if qtype == "choice" else "",
            ))

    if skipped:
        print(f"  跳過 {skipped} 個無法讀取的檔案", file=sys.stderr)
    return rows


def build_index(data_dir: Path) -> dict[str, Any]:
    rows = load_exam_files(data_dir)
    categories = sorted({category for row in rows for category in row[1] if category})
    subjects = sorted({row[3] for row in rows if row[3]})
    years = sorted({row[2] for row in rows if row[2]})
    columns = {field: [row[index] for row in rows] for index, field in enumerate(FIELDS)}
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
        "facets": {"categories": categories, "subjects": subjects, "years": years},
        "columns": columns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成前端搜尋索引")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gzip", action="store_true", help="同時產出 .gz 壓縮版")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"資料目錄不存在: {data_dir}", file=sys.stderr)
        raise SystemExit(1)
    index = build_index(data_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.gzip:
        with output.open("rb") as source, gzip.open(output.with_suffix(".json.gz"), "wb", compresslevel=9) as target:
            target.write(source.read())
    print(f"已產出: {output}")
    print(json.dumps(index["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
