#!/usr/bin/env python3
"""Incrementally build a local SQLite trigram / optional E5 vector index."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time

if __package__:
    from .retrieval import (DEFAULT_MODEL, SCHEMA_VERSION, EMBEDDING_TEXT_VERSION, LEGACY_EMBEDDING_TEXT_VERSION,
        chunk_text, embedder_identity, embedding_texts, embedding_texts_v1, embedding_text_version, encode, json_text, load_embedder,
        metadata, model_prefix, pending_vector_questions, vector_blob, REBUILD_MESSAGE,
        require_matching_identity, valid_identity, validate_model_revision, resolve_model_revision,
        load_injected_embedder)
else:
    from retrieval import (DEFAULT_MODEL, SCHEMA_VERSION, EMBEDDING_TEXT_VERSION, LEGACY_EMBEDDING_TEXT_VERSION,
        chunk_text, embedder_identity, embedding_texts, embedding_texts_v1, embedding_text_version, encode, json_text, load_embedder,
        metadata, model_prefix, pending_vector_questions, vector_blob, REBUILD_MESSAGE,
        require_matching_identity, valid_identity, validate_model_revision, resolve_model_revision,
        load_injected_embedder)


V2_WRITER_GUARD = ("CREATE TRIGGER rag_v2_writer_guard BEFORE DELETE ON vectors "
                   "BEGIN SELECT rag_v2_builder_authorized(); END")
PENDING_ENCODE_GUARD = ("CREATE TRIGGER rag_pending_vector_no_encode BEFORE UPDATE OF embedding ON vectors "
                        "WHEN OLD.vector_id LIKE 'pending:%' AND NEW.embedding IS NOT NULL "
                        "BEGIN SELECT RAISE(ABORT,'pending vectors require the current builder'); END")
PENDING_DELETE_GUARD = ("CREATE TRIGGER rag_pending_vector_no_delete BEFORE DELETE ON vectors "
                        "WHEN OLD.vector_id LIKE 'pending:%' "
                        "BEGIN SELECT RAISE(ABORT,'pending vectors require the current builder'); END")
IDENTITY_GUARDS = {
    f"rag_model_identity_{operation.lower()}_guard":
        f"CREATE TRIGGER rag_model_identity_{operation.lower()}_guard BEFORE {operation} ON vectors "
        "BEGIN SELECT rag_model_identity_builder_authorized(); END"
    for operation in ("INSERT", "UPDATE", "DELETE")
}
OWNED_TRIGGERS = {"rag_v2_writer_guard": V2_WRITER_GUARD,
                  "rag_pending_vector_no_encode": PENDING_ENCODE_GUARD,
                  "rag_pending_vector_no_delete": PENDING_DELETE_GUARD, **IDENTITY_GUARDS}


def reject_hardlinks(path):
    try:
        links = Path(path).stat().st_nlink
    except FileNotFoundError:
        return
    if links > 1:
        raise ValueError("索引有多個硬連結；請先使用獨立的索引檔")


@contextmanager
def retryable_sqlite_errors():
    try:
        yield
    except sqlite3.OperationalError as exc:
        code = getattr(exc, "sqlite_errorcode", 0) or 0
        # SQLITE_BUSY=5, SQLITE_LOCKED=6; the sqlite3 constants only exist on Python 3.11+.
        if code & 0xff in (5, 6) or str(exc).lower() in (
                "database is locked", "database table is locked"):
            raise sqlite3.OperationalError(f"資料庫忙碌或被鎖定；已提交批次保留，可以安全重試：{exc}") from exc
        raise


@contextmanager
def index_write_lock(db):
    """Serialize cooperating writers across commits and atomic replacement."""
    path = Path(db).resolve()
    if not path.parent.is_dir():
        raise ValueError(f"索引不存在：{path}")
    # Keep this stable sidecar: removing it after unlock permits inode races.
    with (path.parent / ("." + path.name + ".rag-write.lock")).open("a+b") as stream:
        if os.name == "nt":
            import errno
            import msvcrt
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) and getattr(exc, "winerror", None) not in (33, 36, 158):
                        raise
                    time.sleep(0.05)
            try:
                reject_hardlinks(path)
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                reject_hardlinks(path)
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


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


def read_law_corpus(path):
    raw = Path(path).read_bytes()
    records = []
    seen = set()
    fields = ("id", "law_name", "pcode", "article_no", "chapter", "content",
              "law_modified_date", "url")
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or any(not isinstance(record.get(key), str) for key in fields):
            raise ValueError(f"Laws line {line_number}: required fields must be strings")
        if not record["id"] or record["id"] in seen:
            raise ValueError(f"Laws line {line_number}: empty or duplicate id")
        seen.add(record["id"])
        records.append({key: record[key] for key in fields})
    return records, hashlib.sha256(raw).hexdigest()


def law_embedding_text(record):
    return "\n".join(value for value in (
        record["law_name"], record["article_no"], record["chapter"], record["content"]
    ) if value)


def build_index(corpus=Path("rag/corpus.jsonl"), db=Path("rag/index.sqlite"), *,
                embed=True, model=DEFAULT_MODEL, embedder_factory=None,
                device="auto", batch_size=64, laws=None):
    with retryable_sqlite_errors():
        if str(db) == ":memory:":
            return _build_index(corpus, db, embed=embed, model=model, embedder_factory=embedder_factory,
                                device=device, batch_size=batch_size, laws=laws)
        db = Path(db)
        db.parent.mkdir(parents=True, exist_ok=True)
        with index_write_lock(db):
            return _build_index(corpus, db, embed=embed, model=model, embedder_factory=embedder_factory,
                                device=device, batch_size=batch_size, laws=laws)


def _build_index(corpus, db, *, embed, model, embedder_factory, device, batch_size, laws=None):
    if batch_size <= 0:
        raise ValueError("batch_size 必須大於 0")
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError("device 必須為 auto、cpu 或 cuda")
    started = time.perf_counter()
    records, corpus_hash = read_corpus(corpus)
    law_records, laws_hash = read_law_corpus(laws) if laws is not None else (None, None)
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    connection.create_function("rag_v2_builder_authorized", 0, lambda: 1)
    connection.create_function("rag_model_identity_builder_authorized", 0, lambda: 1)
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
            previous_identity = previous_meta.get("model_identity")
            has_vectors = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vectors' COLLATE NOCASE"
            ).fetchone() is not None
            unidentified_vectors = bool(has_vectors and connection.execute(
                "SELECT 1 FROM vectors WHERE embedding IS NOT NULL LIMIT 1"
            ).fetchone() and not valid_identity(previous_identity))
            if valid_identity(previous_identity) and any(name not in triggers for name in IDENTITY_GUARDS):
                raise ValueError("模型身分索引的保護觸發器缺失；" + REBUILD_MESSAGE)
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
            if unidentified_vectors and schema_changed:
                raise ValueError(REBUILD_MESSAGE)
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
            if schema_changed and valid_identity(previous_identity):
                for sql in IDENTITY_GUARDS.values():
                    connection.execute(sql)
                guard_added = True
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
            if unidentified_vectors:
                # An unknown provenance cannot be repaired by hashing the model
                # currently installed. Preserve the original database, including
                # for delete-only or metadata-only updates. A true no-op can
                # leave it untouched without loading any model.
                same_records = (not added and not removed and all(
                    old[key] == records[key][:2] for key in records))
                if not same_records or corpus_hash != previous_meta.get("corpus_sha256"):
                    raise ValueError(REBUILD_MESSAGE)
                if embed:
                    main_ids = {question_id for question_id, vector_id in connection.execute(
                        "SELECT question_id,vector_id FROM question_vectors")
                        if vector_id.startswith(f"q:{question_id}:")}
                    incomplete = (pending_questions or main_ids != set(records)
                                  or connection.execute("SELECT 1 FROM vectors WHERE embedding IS NULL LIMIT 1").fetchone())
                    old_rule = (embedding_texts_v1 if previous_version == LEGACY_EMBEDDING_TEXT_VERSION
                                else embedding_texts)
                    migration = any(old_rule(json.loads(row[1])) != embedding_texts(json.loads(row[1]))
                                    for row in records.values())
                    if previous_meta.get("model") != model or incomplete or migration:
                        raise ValueError(REBUILD_MESSAGE)
                connection.rollback()
                return {"added": 0, "updated": 0, "removed": 0, "unchanged": len(records),
                        "embedded": 0, "model_changed": False, "corpus_sha256": corpus_hash,
                        "index_changed": False, "index_bytes": db.stat().st_size,
                        "build_seconds": round(time.perf_counter() - started, 3)}
            model_changed = embed and previous_meta.get("model") not in (None, model)
            reset = schema_changed or model_changed or (embed and not previous_meta.get("model"))
            if unidentified_vectors and reset and embed:
                raise ValueError(REBUILD_MESSAGE)
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
            current_identity = None if model_changed else previous_identity
            current_revision = None if model_changed else previous_meta.get("model_revision")
            embedder = None
            if prepare or (embed and unfinished):
                if unidentified_vectors or ("model_identity" in previous_meta and not valid_identity(previous_identity)):
                    raise ValueError(REBUILD_MESSAGE)
                if "model_revision" in previous_meta and not model_changed:
                    validate_model_revision(model, current_revision)
                if embedder_factory:
                    embedder = load_injected_embedder(embedder_factory, model, current_revision)
                else:
                    if current_revision is None:
                        current_revision = resolve_model_revision(model)
                    if current_revision is None:
                        embedder = load_embedder(model, device=device)
                    else:
                        embedder = load_embedder(model, device=device, revision=current_revision)
                current_identity = embedder_identity(embedder, model)
                if valid_identity(previous_identity) and not model_changed:
                    require_matching_identity(previous_identity, current_identity)
                for name, sql in IDENTITY_GUARDS.items():
                    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone() is None:
                        connection.execute(sql)
                        guard_added = True
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
                if model_changed:
                    current_meta.pop("model_revision", None)
                    current_meta.pop("model_identity", None)
                    connection.execute("DELETE FROM meta WHERE key='model_revision'")
                    connection.execute("DELETE FROM meta WHERE key='model_identity'")
                if (current_revision is not None and
                        ("model_revision" in previous_meta or not valid_identity(previous_identity) or model_changed)):
                    current_meta["model_revision"] = current_revision
                if current_identity is not None:
                    current_meta["model_identity"] = current_identity
                if pending:
                    current_meta["device"] = str(getattr(embedder, "device", device))
            elif reset:
                current_meta.update(model=None, dimension=None)
            if pending_questions or "pending_question_vectors" in previous_meta:
                current_meta["pending_question_vectors"] = {key: sorted(value) for key, value in sorted(pending_questions.items())}
            for key, value in sorted(current_meta.items()):
                if (key not in previous_meta or previous_meta[key] != value
                        or (model_changed and key in ("model_identity", "model_revision"))):
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
            if law_records is not None:
                law_tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                required_law_tables = {"law_articles", "law_fts", "law_vectors"}
                rebuild_laws = (previous_meta.get("laws_sha256") != laws_hash
                                or not required_law_tables.issubset(law_tables))
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS law_articles ("
                    "id TEXT PRIMARY KEY, law_name TEXT NOT NULL, pcode TEXT NOT NULL, "
                    "article_no TEXT NOT NULL, chapter TEXT NOT NULL, content TEXT NOT NULL, "
                    "law_modified_date TEXT NOT NULL, url TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS law_fts "
                    "USING fts5(article_id UNINDEXED, text, tokenize='trigram')"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS law_vectors ("
                    "article_id TEXT PRIMARY KEY REFERENCES law_articles(id) ON DELETE CASCADE, "
                    "embedding BLOB NOT NULL)"
                )
                if rebuild_laws:
                    connection.execute("DELETE FROM law_vectors")
                    connection.execute("DELETE FROM law_fts")
                    connection.execute("DELETE FROM law_articles")
                    for record in law_records:
                        connection.execute(
                            "INSERT INTO law_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            tuple(record[key] for key in (
                                "id", "law_name", "pcode", "article_no", "chapter",
                                "content", "law_modified_date", "url"
                            )),
                        )
                        searchable = "\n".join(filter(None, (
                            record["law_name"], record["article_no"], record["chapter"], record["content"]
                        )))
                        connection.execute(
                            "INSERT INTO law_fts(article_id, text) VALUES (?, ?)",
                            (record["id"], searchable),
                        )

                law_vector_count = connection.execute("SELECT count(*) FROM law_vectors").fetchone()[0]
                law_identity = previous_meta.get("laws_model_identity")
                law_vectors_complete = (law_vector_count == len(law_records)
                                        and valid_identity(law_identity)
                                        and previous_meta.get("laws_model") == model)
                rebuild_law_vectors = embed and (
                    rebuild_laws or not law_vectors_complete
                    or (current_identity is not None and law_identity != current_identity)
                )
                law_model_revision = previous_meta.get("laws_model_revision")
                if embedder is not None:
                    law_model_revision = current_revision
                if rebuild_law_vectors:
                    if embedder is None:
                        if law_model_revision is not None and previous_meta.get("laws_model") == model:
                            validate_model_revision(model, law_model_revision)
                        elif not embedder_factory:
                            law_model_revision = resolve_model_revision(model)
                        if embedder_factory:
                            embedder = load_injected_embedder(embedder_factory, model, law_model_revision)
                        elif law_model_revision is None:
                            embedder = load_embedder(model, device=device)
                        else:
                            embedder = load_embedder(model, device=device, revision=law_model_revision)
                        if current_revision is None:
                            current_revision = law_model_revision
                    actual_law_identity = embedder_identity(embedder, model)
                    if valid_identity(previous_meta.get("model_identity")) and previous_meta.get("model") == model:
                        require_matching_identity(previous_meta["model_identity"], actual_law_identity)
                    dimension = previous_meta.get("laws_dimension")
                    chunks, article_chunks = [], {}
                    for record in law_records:
                        article_chunks[record["id"]] = []
                        for chunk in chunk_text(embedder, law_embedding_text(record), model_prefix(model)):
                            article_chunks[record["id"]].append(len(chunks))
                            chunks.append(chunk)
                    encoded = encode(embedder, chunks, model_prefix(model), batch_size=batch_size)
                    connection.execute("DELETE FROM law_vectors")
                    for record in law_records:
                        vectors = [encoded[index] for index in article_chunks[record["id"]]]
                        vector = [sum(row[column] for row in vectors) / len(vectors)
                                  for column in range(len(vectors[0]))]
                        norm = sum(value * value for value in vector) ** 0.5
                        if not math.isfinite(norm) or norm == 0:
                            raise ValueError("法條向量平均為零或非有限值")
                        vector = [value / norm for value in vector]
                        if dimension is None:
                            dimension = len(vector)
                        if dimension != len(vector):
                            raise ValueError("法條向量維度不符；請使用一致的 --model 重新建置")
                        connection.execute(
                            "INSERT INTO law_vectors(article_id, embedding) VALUES (?, ?)",
                            (record["id"], vector_blob(vector)),
                        )
                    law_meta = {
                        "laws_model": model,
                        "laws_model_identity": actual_law_identity,
                        "laws_dimension": dimension,
                    }
                    if law_model_revision is not None:
                        law_meta["laws_model_revision"] = law_model_revision
                    else:
                        connection.execute("DELETE FROM meta WHERE key='laws_model_revision'")
                    for key, value in law_meta.items():
                        connection.execute(
                            "INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json_text(value))
                        )
                elif rebuild_laws:
                    connection.execute(
                        "DELETE FROM meta WHERE key IN "
                        "('laws_model','laws_model_identity','laws_model_revision','laws_dimension')"
                    )
                if previous_meta.get("laws_sha256") != laws_hash:
                    connection.execute(
                        "INSERT OR REPLACE INTO meta VALUES ('laws_sha256', ?)", (json_text(laws_hash),)
                    )
                connection.commit()
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
    parser.add_argument("--laws", type=Path, help="現行法條 JSONL（不指定時保留既有法條索引）")
    args = parser.parse_args(argv)
    try:
        result = build_index(args.corpus, args.db, embed=args.embed, model=args.model,
                             device=args.device, batch_size=args.batch_size, laws=args.laws)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"索引建置失敗：{exc}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
