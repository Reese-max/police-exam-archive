#!/usr/bin/env python3
"""Update a prebuilt BGE-M3 index without ever rebuilding it from scratch."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

if __package__:
    from .build_corpus import build_corpus, json_text
    from .build_index import build_index
    from .build_source_map import build_source_map, write_json
    from .fetch_moex_catalog import fetch_catalog
    from .retrieval import SCHEMA_VERSION, metadata, open_index
else:
    from build_corpus import build_corpus, json_text
    from build_index import build_index
    from build_source_map import build_source_map, write_json
    from fetch_moex_catalog import fetch_catalog
    from retrieval import SCHEMA_VERSION, metadata, open_index


MODEL = "BAAI/bge-m3"
ROOT = Path(__file__).resolve().parents[2]


def seed_info(db):
    connection = open_index(db)
    try:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("舊索引的 SQLite 完整性檢查失敗")
        meta = metadata(connection)
        count = connection.execute("SELECT count(*) FROM questions").fetchone()[0]
        pending = connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0]
        missing = connection.execute(
            "SELECT count(*) FROM questions q WHERE NOT EXISTS "
            "(SELECT 1 FROM question_vectors v WHERE v.question_id=q.question_id)"
        ).fetchone()[0]
        if (meta.get("schema_version") != SCHEMA_VERSION or meta.get("model") != MODEL
                or not meta.get("dimension") or not count or pending or missing):
            raise ValueError("舊索引不完整或模型/schema 不符；請先用本機 GPU 建立完整索引")
        ids, paths = set(), set()
        for identifier, document in connection.execute("SELECT question_id, doc_json FROM questions"):
            ids.add(identifier)
            paths.update(item["path"] for item in json.loads(document).get("appears_in", []) if item.get("path"))
        if not paths:
            raise ValueError("舊索引缺少考卷出處；請先用本機 GPU 建立完整索引")
        return meta, ids, paths
    finally:
        connection.close()


def update(root, db, *, catalog=None, catalog_out=None, device="cpu", batch_size=8,
           embedder_factory=None):
    root, db = Path(root), Path(db)
    catalog = Path(catalog) if catalog else root / "rag/moex_catalog.json"
    meta, old_ids, old_paths = seed_info(db)
    papers = sorted((root / "考古題庫").glob("*/*/*/試題.json"))
    if not papers:
        raise ValueError("沒有考古題；拒絕清空既有索引")
    years = {int(p.parent.parent.name[:-1]) for p in papers
             if p.parent.parent.name.endswith("年") and p.parent.parent.name[:-1].isdigit()}
    original_catalog = json.loads(catalog.read_text(encoding="utf-8-sig"))
    if original_catalog.get("schema_version") != 1:
        raise ValueError("考選部目錄 schema 不符")
    missing_years = years - {entry["year"] for entry in original_catalog["entries"]}
    archive = root / "考古題庫"
    new_paper_years = {
        int(p.parent.parent.name[:-1]) for p in papers
        if p.parent.relative_to(archive).as_posix() not in old_paths
        and p.parent.parent.name.endswith("年") and p.parent.parent.name[:-1].isdigit()
        and json.loads(p.read_text(encoding="utf-8-sig")).get("questions")
    }
    refresh_years = sorted(missing_years | new_paper_years)

    with tempfile.TemporaryDirectory(prefix=".rag-update-", dir=db.parent) as temporary:
        temp = Path(temporary)
        combined = original_catalog
        if refresh_years:
            from urllib.parse import parse_qs, urlsplit
            fresh, _ = fetch_catalog(temp, years=refresh_years)
            old_pages = [p for p in original_catalog["pages"]
                         if int(parse_qs(urlsplit(p["url"]).query)["y"][0]) - 1911 not in refresh_years]
            combined = {
                "schema_version": 1,
                "pages": sorted(old_pages + fresh["pages"], key=lambda p: p["url"]),
                "entries": sorted([e for e in original_catalog["entries"] if e["year"] not in refresh_years]
                                  + fresh["entries"],
                                  key=lambda x: (x["exam_code"], x["category_code"], x["subject_code"],
                                                 x["question_pdf_url"] or "", x["answer_pdf_url"] or "")),
            }
        new_catalog = temp / "moex_catalog.json"
        write_json(new_catalog, combined)
        source_map, _ = build_source_map(root, catalog_path=new_catalog)
        source_path = temp / "source_map.json"
        write_json(source_path, source_map)
        corpus, stats = build_corpus(root / "考古題庫", source_path)
        if not old_ids.intersection(record["question_id"] for record in corpus):
            raise ValueError("新語料與舊索引沒有共同題目；拒絕全量重建")
        corpus_path = temp / "corpus.jsonl"
        with corpus_path.open("w", encoding="utf-8", newline="\n") as stream:
            for record in corpus:
                stream.write(json_text(record) + "\n")

        candidate = temp / db.name
        with closing(open_index(db)) as source, closing(sqlite3.connect(candidate)) as target:
            source.backup(target)
        result = build_index(corpus_path, candidate, model=MODEL, device=device,
                             batch_size=batch_size, embedder_factory=embedder_factory)
        seed_info(candidate)
        changed = result["corpus_sha256"] != meta.get("corpus_sha256")
        if changed:
            os.replace(candidate, db)
        if catalog_out:
            output = Path(catalog_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            data = new_catalog.read_bytes()
            if not output.exists() or output.read_bytes() != data:
                output.write_bytes(data)
        return {**result, "index_changed": changed, "catalog_added_years": sorted(missing_years),
                "catalog_refreshed_years": refresh_years,
                "catalog_changed": combined != original_catalog,
                "questions": stats["deduplicated_question_count"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db", type=Path, required=True, help="Existing complete BGE-M3 SQLite index")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--catalog-out", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = update(args.root, args.db, catalog=args.catalog, catalog_out=args.catalog_out,
                        device=args.device, batch_size=args.batch_size)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"增量更新失敗：{exc}\n")
    output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
