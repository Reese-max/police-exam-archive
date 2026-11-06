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
    from .retrieval import DEFAULT_MODEL, SCHEMA_VERSION, chunk_text, embedding_texts, encode, json_text, load_embedder, metadata, model_prefix, vector_blob
else:
    from retrieval import DEFAULT_MODEL, SCHEMA_VERSION, chunk_text, embedding_texts, encode, json_text, load_embedder, metadata, model_prefix, vector_blob


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
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute("BEGIN")
            connection.execute("CREATE TABLE IF NOT EXISTS questions "
                               "(question_id TEXT PRIMARY KEY, text_hash TEXT NOT NULL, doc_json TEXT NOT NULL)")
            connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS question_fts "
                               "USING fts5(question_id UNINDEXED, text, tokenize='trigram')")
            connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            previous_meta = metadata(connection)
            schema_changed = previous_meta.get("schema_version") != SCHEMA_VERSION
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
            reset = schema_changed or model_changed or not previous_meta.get("model")
            if model_changed:
                print(f"模型變更：{previous_meta['model']} → {model}；全量重建向量索引", file=sys.stderr)
            if reset:
                connection.execute("DELETE FROM question_vectors")
                connection.execute("DELETE FROM vectors")
            present = {row[0] for row in connection.execute("SELECT DISTINCT question_id FROM question_vectors")}
            documents = {key: json.loads(row[1]) for key, row in records.items()}
            vector_changed = {key for key in records.keys() & old.keys()
                              if embedding_texts(documents[key]) != embedding_texts(json.loads(old[key][1]))}
            invalid = set(added) | vector_changed
            for identifier in sorted(invalid | set(removed)):
                connection.execute("DELETE FROM question_vectors WHERE question_id=?", (identifier,))
            prepare = sorted((records.keys() - present) | invalid) if embed else []
            unfinished = connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0]
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
                for kind, text in enumerate(embedding_texts(documents[identifier])):
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
            connection.execute("DELETE FROM vectors WHERE vector_id NOT IN (SELECT vector_id FROM question_vectors)")
            pending = connection.execute("SELECT vector_id,text FROM vectors WHERE embedding IS NULL ORDER BY vector_id").fetchall() if embed else []
            current_meta = {**previous_meta, "schema_version": SCHEMA_VERSION, "corpus_sha256": corpus_hash}
            if embed:
                current_meta.update(model=model, dimension=dimension)
                if pending:
                    current_meta["device"] = str(getattr(embedder, "device", device))
            elif reset:
                current_meta.update(model=None, dimension=None)
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
    finally:
        connection.close()
    return {"added": len(added), "updated": len(updated), "removed": len(removed),
            "unchanged": len(records) - len(added) - len(updated), "embedded": len(pending),
            "model_changed": model_changed, "corpus_sha256": corpus_hash,
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
