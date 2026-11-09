#!/usr/bin/env python3
"""Incrementally build a local SQLite trigram / optional E5 vector index."""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

if __package__:
    from .retrieval import (DEFAULT_MODEL, SCHEMA_VERSION, EMBEDDING_TEXT_VERSION, LEGACY_EMBEDDING_TEXT_VERSION,
        chunk_text, embedding_texts, embedding_texts_v1, embedding_text_version, encode, json_text, load_embedder,
        metadata, model_prefix, pending_vector_questions, vector_blob)
else:
    from retrieval import (DEFAULT_MODEL, SCHEMA_VERSION, EMBEDDING_TEXT_VERSION, LEGACY_EMBEDDING_TEXT_VERSION,
        chunk_text, embedding_texts, embedding_texts_v1, embedding_text_version, encode, json_text, load_embedder,
        metadata, model_prefix, pending_vector_questions, vector_blob)


V2_WRITER_GUARD = ("CREATE TRIGGER rag_v2_writer_guard BEFORE DELETE ON vectors "
                   "BEGIN SELECT rag_v2_builder_authorized(); END")
PENDING_ENCODE_GUARD = ("CREATE TRIGGER rag_pending_vector_no_encode BEFORE UPDATE OF embedding ON vectors "
                        "WHEN OLD.vector_id LIKE 'pending:%' AND NEW.embedding IS NOT NULL "
                        "BEGIN SELECT RAISE(ABORT,'pending vectors require the current builder'); END")
PENDING_DELETE_GUARD = ("CREATE TRIGGER rag_pending_vector_no_delete BEFORE DELETE ON vectors "
                        "WHEN OLD.vector_id LIKE 'pending:%' "
                        "BEGIN SELECT RAISE(ABORT,'pending vectors require the current builder'); END")
OWNED_TRIGGERS = {"rag_v2_writer_guard": V2_WRITER_GUARD,
                  "rag_pending_vector_no_encode": PENDING_ENCODE_GUARD,
                  "rag_pending_vector_no_delete": PENDING_DELETE_GUARD}


def read_corpus(path):
    raw = Path(path).read_bytes()
    records = {}
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        doc = json.loads(line)
        identifier, text = doc.get("question_id"), doc.get("text")
        if not isinstance(identifier, str) or not identifier or not isinstance(text, str):
            raise ValueError(f"Corpus line {line_number}: question_id/text must be strings")
        if identifier in records:
            raise ValueError(f"Duplicate question_id at corpus line {line_number}: {identifier}")
        records[identifier] = (hashlib.sha256(text.encode("utf-8")).hexdigest(), json_text(doc), text)
    return records, hashlib.sha256(raw).hexdigest()


def build_index(corpus=Path("rag/corpus.jsonl"), db=Path("rag/index.sqlite"), *,
                embed=True, model=DEFAULT_MODEL, embedder_factory=None,
                device="auto", batch_size=64):
    if batch_size <= 0:
        raise ValueError("batch_size 必須大於 0")
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError("device 必須為 auto、cpu 或 cuda")
    started = time.perf_counter()
    records, corpus_hash = read_corpus(corpus)
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    connection.create_function("rag_v2_builder_authorized", 0, lambda: 1)
    connection.execute("PRAGMA foreign_keys=ON")
    changes_before = connection.total_changes
    guard_added = False
    try:
        with connection:
            connection.execute("BEGIN")
            has_existing_schema = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone() is not None
            has_meta = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta' COLLATE NOCASE"
            ).fetchone() is not None
            previous_meta = metadata(connection) if has_meta else {}
            previous_schema = previous_meta.get("schema_version")
            if ((has_existing_schema and previous_schema is None)
                    or (previous_schema is not None and
                        (type(previous_schema) is not int or previous_schema not in (1, SCHEMA_VERSION)))):
                raise ValueError(f"不支援的索引 schema 版本：{previous_schema!r}")
            previous_version = embedding_text_version(previous_meta)
            pending_questions = pending_vector_questions(previous_meta)
            triggers = {name: (table, sql) for name, table, sql in connection.execute(
                "SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger'")}
            for name, (_, sql) in triggers.items():
                canonical = name.casefold()
                if canonical in OWNED_TRIGGERS and (name != canonical or sql != OWNED_TRIGGERS[canonical]):
                    raise ValueError(f"保護觸發器名稱已被使用：{name}")
            has_links = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='question_vectors' COLLATE NOCASE"
            ).fetchone() is not None
            if has_links and connection.execute(
                    "SELECT 1 FROM question_vectors WHERE typeof(question_id)<>'text' "
                    "OR typeof(vector_id)<>'text' LIMIT 1").fetchone():
                raise ValueError("向量索引連結無效")
            schema_changed = previous_meta.get("schema_version") != SCHEMA_VERSION
            if schema_changed and any(table.casefold() in ("vectors", "question_vectors") and name.casefold() not in OWNED_TRIGGERS
                                      for name, (table, _) in triggers.items()):
                raise ValueError("既有索引含自訂觸發器；拒絕重建")
            connection.execute("CREATE TABLE IF NOT EXISTS questions "
                               "(question_id TEXT PRIMARY KEY, text_hash TEXT NOT NULL, doc_json TEXT NOT NULL)")
            connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS question_fts "
                               "USING fts5(question_id UNINDEXED, text, tokenize='trigram')")
            connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            if schema_changed:
                connection.execute("DROP TABLE IF EXISTS question_vectors")
                connection.execute("DROP TABLE IF EXISTS vectors")
                print("向量 schema 變更；全量重建向量索引", file=sys.stderr)
            connection.execute("CREATE TABLE IF NOT EXISTS vectors "
                               "(vector_id TEXT PRIMARY KEY, text TEXT NOT NULL, embedding BLOB)")
            connection.execute("CREATE TABLE IF NOT EXISTS question_vectors "
                               "(question_id TEXT REFERENCES questions(question_id) ON DELETE CASCADE, "
                               "vector_id TEXT REFERENCES vectors(vector_id) ON DELETE CASCADE, "
                               "PRIMARY KEY(question_id, vector_id))")
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='rag_v2_writer_guard'").fetchone() is None:
                connection.execute(V2_WRITER_GUARD)
                guard_added = True
            old = {identifier: (text_hash, doc_json) for identifier, text_hash, doc_json in
                   connection.execute("SELECT question_id, text_hash, doc_json FROM questions")}
            fts_rows = {identifier: rowid for rowid, identifier in
                        connection.execute("SELECT rowid, question_id FROM question_fts")}
            added = sorted(records.keys() - old.keys())
            removed = sorted(old.keys() - records.keys())
            updated = sorted(identifier for identifier in records.keys() & old.keys()
                             if records[identifier][0] != old[identifier][0])
            changed = set(added + updated)
            model_changed = embed and previous_meta.get("model") not in (None, model)
            reset = schema_changed or model_changed or (embed and not previous_meta.get("model"))
            if model_changed:
                print(f"模型變更：{previous_meta['model']} → {model}；全量重建向量索引", file=sys.stderr)
            if reset:
                connection.execute("DROP TRIGGER IF EXISTS rag_pending_vector_no_delete")
                connection.execute("DROP TRIGGER IF EXISTS rag_pending_vector_no_encode")
                connection.execute("DELETE FROM question_vectors")
                connection.execute("DELETE FROM vectors")
            present = {question_id for question_id, vector_id in connection.execute(
                "SELECT question_id, vector_id FROM question_vectors")
                if vector_id.startswith(f"q:{question_id}:")}
            for identifier in records.keys() - present:
                pending_questions.setdefault(identifier, set()).add("main")
            documents = {key: json.loads(row[1]) for key, row in records.items()}
            previous_texts = (embedding_texts_v1 if previous_version == LEGACY_EMBEDDING_TEXT_VERSION
                              else embedding_texts)
            current_texts = {key: embedding_texts(doc) for key, doc in documents.items()}
            old_texts = {key: previous_texts(json.loads(old[key][1])) for key in records.keys() & old.keys()}
            main_changed = set(added) | {key for key in old_texts if current_texts[key][0] != old_texts[key][0]}
            passage_changed = set(added) | {key for key in old_texts if current_texts[key][1:] != old_texts[key][1:]}
            for identifier in removed:
                pending_questions.pop(identifier, None)
                connection.execute("DELETE FROM question_vectors WHERE question_id=?", (identifier,))
            for identifier in sorted(main_changed | passage_changed):
                parts = pending_questions.setdefault(identifier, set())
                if identifier in main_changed:
                    parts.add("main")
                    connection.execute("DELETE FROM question_vectors WHERE question_id=? AND vector_id NOT LIKE 'p:%'",
                                       (identifier,))
                if identifier in passage_changed:
                    connection.execute("DELETE FROM question_vectors WHERE question_id=? AND vector_id LIKE 'p:%'",
                                       (identifier,))
                    if len(current_texts[identifier]) > 1:
                        parts.add("passage")
                    else:
                        parts.discard("passage")
                if not parts:
                    pending_questions.pop(identifier, None)
            needs_passage = {key for key in passage_changed if len(current_texts[key]) > 1}
            prepare = sorted((records.keys() - present) | main_changed | needs_passage | pending_questions.keys()) if embed else []
            unfinished = connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL "
                                            "AND vector_id NOT LIKE 'pending:%'").fetchone()[0]
            dimension = None if reset else previous_meta.get("dimension")
            if prepare or (embed and unfinished):
                embedder = (embedder_factory(model) if embedder_factory
                            else load_embedder(model, device=device))
            for identifier in removed:
                connection.execute("DELETE FROM question_fts WHERE rowid=?", (fts_rows[identifier],))
                connection.execute("DELETE FROM questions WHERE question_id=?", (identifier,))
            for identifier in sorted(records):
                text_hash, doc_json, text = records[identifier]
                if identifier in changed:
                    if identifier in fts_rows:
                        connection.execute("DELETE FROM question_fts WHERE rowid=?", (fts_rows[identifier],))
                    connection.execute("INSERT INTO question_fts(question_id, text) VALUES (?, ?)",
                                       (identifier, text))
                if identifier not in old or old[identifier] != (text_hash, doc_json):
                    connection.execute("INSERT INTO questions VALUES (?, ?, ?) ON CONFLICT(question_id) "
                                       "DO UPDATE SET text_hash=excluded.text_hash, doc_json=excluded.doc_json",
                                       (identifier, text_hash, doc_json))
            for identifier in prepare:
                for kind, text in enumerate(current_texts[identifier]):
                    for ordinal, chunk in enumerate(chunk_text(embedder, text, model_prefix(model))):
                        # Main chunks stay question-specific; identical passages share storage/encoding.
                        digest = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                        vector_id = (f"q:{identifier}:{ordinal:06d}" if kind == 0 else "p:" + digest)
                        existing = connection.execute("SELECT text FROM vectors WHERE vector_id=?", (vector_id,)).fetchone()
                        if existing and existing[0] != chunk:
                            connection.execute("UPDATE vectors SET text=?, embedding=NULL WHERE vector_id=?", (chunk, vector_id))
                        else:
                            connection.execute("INSERT OR IGNORE INTO vectors(vector_id,text) VALUES (?,?)", (vector_id, chunk))
                        connection.execute("INSERT OR IGNORE INTO question_vectors VALUES (?,?)", (identifier, vector_id))
            # NULL markers make incomplete indexes fail even in older vector readers.
            markers = connection.execute("SELECT question_id,vector_id FROM question_vectors "
                                         "WHERE vector_id LIKE 'pending:%'").fetchall()
            for identifier, vector_id in markers:
                if embed or identifier not in pending_questions:
                    connection.execute("DELETE FROM question_vectors WHERE question_id=? AND vector_id=?",
                                       (identifier, vector_id))
            if not embed:
                for identifier in sorted(pending_questions.keys() & records.keys()):
                    marker = "pending:" + identifier
                    connection.execute("INSERT OR IGNORE INTO vectors(vector_id,text) VALUES (?, '')", (marker,))
                    connection.execute("UPDATE vectors SET text='', embedding=NULL WHERE vector_id=? "
                                       "AND (text<>'' OR embedding IS NOT NULL)", (marker,))
                    connection.execute("INSERT OR IGNORE INTO question_vectors VALUES (?,?)", (identifier, marker))
            orphan_marker = connection.execute(
                "SELECT 1 FROM vectors WHERE vector_id LIKE 'pending:%' "
                "AND vector_id NOT IN (SELECT vector_id FROM question_vectors) LIMIT 1"
            ).fetchone()
            if orphan_marker:
                connection.execute("DROP TRIGGER IF EXISTS rag_pending_vector_no_delete")
            connection.execute("DELETE FROM vectors WHERE vector_id NOT IN (SELECT vector_id FROM question_vectors)")
            if connection.execute("SELECT 1 FROM vectors WHERE vector_id LIKE 'pending:%' LIMIT 1").fetchone():
                connection.execute("CREATE TRIGGER IF NOT EXISTS rag_pending_vector_no_encode "
                                   "BEFORE UPDATE OF embedding ON vectors "
                                   "WHEN OLD.vector_id LIKE 'pending:%' AND NEW.embedding IS NOT NULL "
                                   "BEGIN SELECT RAISE(ABORT,'pending vectors require the current builder'); END")
                connection.execute("CREATE TRIGGER IF NOT EXISTS rag_pending_vector_no_delete "
                                   "BEFORE DELETE ON vectors WHEN OLD.vector_id LIKE 'pending:%' "
                                   "BEGIN SELECT RAISE(ABORT,'pending vectors require the current builder'); END")
            else:
                connection.execute("DROP TRIGGER IF EXISTS rag_pending_vector_no_delete")
                connection.execute("DROP TRIGGER IF EXISTS rag_pending_vector_no_encode")
            pending = connection.execute("SELECT vector_id,text FROM vectors WHERE embedding IS NULL ORDER BY vector_id").fetchall() if embed else []
            current_meta = {**previous_meta, "schema_version": SCHEMA_VERSION, "corpus_sha256": corpus_hash,
                            "embedding_text_version": EMBEDDING_TEXT_VERSION}
            if embed:
                pending_questions.clear()  # All prepared links now exist; NULL blobs track unfinished batches.
                current_meta.update(model=model, dimension=dimension)
                if pending:
                    current_meta["device"] = str(getattr(embedder, "device", device))
            elif reset:
                current_meta.update(model=None, dimension=None)
            if pending_questions or "pending_question_vectors" in previous_meta:
                current_meta["pending_question_vectors"] = {key: sorted(value) for key, value in sorted(pending_questions.items())}
            for key, value in sorted(current_meta.items()):
                if key not in previous_meta or previous_meta[key] != value:
                    connection.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json_text(value)))
            for offset in range(0, len(pending), batch_size):
                batch = pending[offset:offset + batch_size]
                vectors = encode(embedder, [text for identifier, text in batch],
                                 model_prefix(model), batch_size=batch_size)
                for (identifier, text), vector in zip(batch, vectors):
                    if dimension is None:
                        dimension = len(vector)
                    if dimension != len(vector):
                        raise ValueError("Embedder dimension changed; rebuild with a different --model name")
                    connection.execute("UPDATE vectors SET embedding=? WHERE vector_id=?",
                                       (vector_blob(vector), identifier))
                if current_meta["dimension"] != dimension:
                    current_meta["dimension"] = dimension
                    connection.execute("INSERT OR REPLACE INTO meta VALUES ('dimension', ?)",
                                       (json_text(dimension),))
                # Hash updates and stale-vector deletion commit atomically with the first batch.
                # SQLite recovers an interrupted batch's journal on the next writable open.
                connection.commit()
                print(f"向量進度：{offset + len(batch)}/{len(pending)}"
                      f"（本次 {offset + len(batch)}/{len(pending)}）", file=sys.stderr, flush=True)
        index_changed = connection.total_changes > changes_before or guard_added
    finally:
        connection.close()
    return {"added": len(added), "updated": len(updated), "removed": len(removed),
            "unchanged": len(records) - len(added) - len(updated), "embedded": len(pending),
            "model_changed": model_changed, "corpus_sha256": corpus_hash, "index_changed": index_changed,
            "index_bytes": db.stat().st_size, "build_seconds": round(time.perf_counter() - started, 3)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("rag/corpus.jsonl"))
    parser.add_argument("--db", type=Path, default=Path("rag/index.sqlite"))
    parser.add_argument("--embed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        result = build_index(args.corpus, args.db, embed=args.embed, model=args.model,
                             device=args.device, batch_size=args.batch_size)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"索引建置失敗：{exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
