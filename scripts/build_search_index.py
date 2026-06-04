#!/usr/bin/env python3
"""從考古題庫 JSON 生成前端搜尋索引。

產出 search-index.json 供前端 MiniSearch 使用。
採用 column-oriented 格式（陣列而非物件陣列）以大幅減少 JSON key 重複開銷。

用法:
    python scripts/build_search_index.py
    python scripts/build_search_index.py --output 考古題網站/data/search-index.json
"""

import argparse
import glob
import gzip
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站" / "data" / "search-index.json"

# 欄位定義（順序即為 column index）
FIELDS = ["cat", "yr", "sub", "no", "type", "stem", "optA", "optB", "optC", "optD", "ans"]


def load_exam_files(data_dir: Path) -> list[tuple]:
    """載入所有試題.json，回傳 tuple 列表（每個 tuple 對應一題的 FIELDS）。"""
    files = sorted(glob.glob(str(data_dir / "**" / "試題.json"), recursive=True))
    rows = []
    skipped = 0

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  SKIP {fp}: {e}", file=sys.stderr)
            skipped += 1
            continue

        if d.get("metadata", {}).get("_is_duplicate"):
            continue

        category = d.get("category", "")
        year = d.get("year")
        subject = d.get("subject", "")

        if not category or not year or not subject:
            rel = os.path.relpath(fp, str(data_dir))
            parts = rel.replace(os.sep, "/").split("/")
            if not category:
                category = parts[0] if len(parts) > 0 else ""
            if not year:
                year_str = parts[1].replace("年", "") if len(parts) > 1 else ""
                year = int(year_str) if year_str.isdigit() else None
            if not subject:
                subject = parts[2] if len(parts) > 2 else ""

        for q in d.get("questions", []):
            qtype = q.get("type", "")
            opts = q.get("options", {}) if qtype == "choice" else {}
            row = (
                category,                       # cat
                year,                            # yr
                subject,                         # sub
                str(q.get("number", "")),        # no
                qtype,                           # type
                q.get("stem", ""),               # stem
                opts.get("A", ""),               # optA
                opts.get("B", ""),               # optB
                opts.get("C", ""),               # optC
                opts.get("D", ""),               # optD
                q.get("answer", "") if qtype == "choice" else "",  # ans
            )
            rows.append(row)

    if skipped:
        print(f"  跳過 {skipped} 個無法讀取的檔案", file=sys.stderr)
    return rows


def build_index(data_dir: Path) -> dict:
    """建立 column-oriented 搜尋索引。"""
    rows = load_exam_files(data_dir)

    # 收集 facets
    categories = sorted({r[0] for r in rows if r[0]})
    subjects = sorted({r[2] for r in rows if r[2]})
    years = sorted({r[1] for r in rows if r[1]})

    # 轉為 columns dict
    columns = {}
    for i, field in enumerate(FIELDS):
        columns[field] = [r[i] for r in rows]

    return {
        "v": 1,
        "fields": FIELDS,
        "stats": {
            "total": len(rows),
            "choice": sum(1 for r in rows if r[4] == "choice"),
            "essay": sum(1 for r in rows if r[4] == "essay"),
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


def main():
    parser = argparse.ArgumentParser(description="生成前端搜尋索引")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gzip", action="store_true", help="同時產出 .gz 壓縮版")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"資料目錄不存在: {data_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"正在掃描 {data_dir} ...")
    index = build_index(data_dir)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # 寫入 compact JSON
    with open(output, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = output.stat().st_size / 1024

    # 可選 gzip
    if args.gzip:
        gz_path = output.with_suffix(".json.gz")
        with open(output, "rb") as f_in:
            with gzip.open(gz_path, "wb", compresslevel=9) as f_out:
                f_out.write(f_in.read())
        gz_kb = gz_path.stat().st_size / 1024
        print(f"  gzip: {gz_kb:.0f} KB")

    print(f"\n已產出: {output}")
    print(f"  總題數: {index['stats']['total']}")
    print(f"  選擇題: {index['stats']['choice']}")
    print(f"  申論題: {index['stats']['essay']}")
    print(f"  類科數: {index['stats']['categories']}")
    print(f"  科目數: {index['stats']['subjects']}")
    print(f"  檔案大小: {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
