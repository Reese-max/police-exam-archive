import hashlib
import json
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.rag.build_index import build_index
from scripts.rag.retrieval import load_embedder, metadata, embedding_texts


class FakeEmbedder:
    rag_identity = "a" * 64
    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.extend(texts)
        return [[1.0, 2.0, 3.0] for _ in texts]


def write_corpus(path, docs):
    path.write_text("".join(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n"
                            for doc in docs), encoding="utf-8")


def document(identifier="a", text="警察查證身分的法定要件", **fields):
    path = "行政警察/114年/警察法規"
    return {"question_id": identifier, "text": text, "stem": text, "type": "choice",
            "answer": "A", "answer_status": "normal",
            "appears_in": [{"path": path, "category": "行政警察", "year": 114,
                            "subject": "警察法規", "number": 7}],
            "sources": [{"path": path,
                         "question_pdf_url": "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=114060",
                         "answer_pdf_url": None}], **fields}


def test_incremental_and_noop_does_not_load_model(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    fake = FakeEmbedder()
    write_corpus(corpus, [document(), document("b"), document("c")])
    first = build_index(corpus, db, embedder_factory=lambda model: fake)
    assert (first["added"], first["updated"], first["removed"], first["embedded"]) == (3, 0, 0, 3)
    assert all(text.startswith("passage: ") for text in fake.calls)
    before = db.read_bytes()

    def unexpected(model):
        pytest.fail("No-op rebuild must not load an embedder")

    second = build_index(corpus, db, embedder_factory=unexpected)
    assert (second["added"], second["updated"], second["removed"], second["unchanged"]) == (0, 0, 0, 3)
    assert db.read_bytes() == before
    fake.calls.clear()
    write_corpus(corpus, [document("a", "修改後的警察法規"), document("c"), document("d")])
    third = build_index(corpus, db, embedder_factory=lambda model: fake)
    assert (third["added"], third["updated"], third["removed"], third["unchanged"]) == (1, 1, 1, 1)
    assert third["embedded"] == len(fake.calls) == 2
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT question_id FROM question_vectors WHERE vector_id IN (SELECT vector_id FROM vectors WHERE embedding IS NOT NULL) ORDER BY question_id").fetchall() == [("a",), ("c",), ("d",)]
        assert connection.execute("SELECT count(*) FROM question_fts").fetchone()[0] == 3
        assert connection.execute("SELECT question_id FROM question_fts WHERE question_fts MATCH '修改後'").fetchall() == [("a",)]
        meta = metadata(connection)
        assert meta["dimension"] == 3
        assert meta["corpus_sha256"] == hashlib.sha256(corpus.read_bytes()).hexdigest()
        blob = connection.execute("SELECT embedding FROM vectors LIMIT 1").fetchone()[0]
        assert len(blob) == 3 * 4
    write_corpus(corpus, [])
    empty = build_index(corpus, db, embedder_factory=unexpected)
    assert empty["removed"] == 3 and empty["embedded"] == 0
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM question_fts").fetchone()[0] == 0


def test_build_without_laws_preserves_existing_law_tables_and_hash(tmp_path):
    corpus, laws, db = tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    law = {
        "id": "law:A1234567:6", "law_name": "測試法", "pcode": "A1234567",
        "article_no": "第6條", "chapter": "第一章", "content": "原有法條",
        "law_modified_date": "20251006",
        "url": "https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=A1234567&flno=6",
    }
    laws.write_text(json.dumps(law, ensure_ascii=False) + "\n", encoding="utf-8")
    build_index(corpus, db, embed=False, laws=laws)
    with sqlite3.connect(db) as connection:
        before = connection.execute("SELECT * FROM law_articles").fetchall()
        digest = connection.execute("SELECT value FROM meta WHERE key='laws_sha256'").fetchone()[0]

    build_index(corpus, db, embed=False)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT * FROM law_articles").fetchall() == before
        assert connection.execute("SELECT value FROM meta WHERE key='laws_sha256'").fetchone()[0] == digest


def test_citation_only_change_updates_doc_without_embedding(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    fake = FakeEmbedder()
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda model: fake)
    fake.calls.clear()
    write_corpus(corpus, [document(answer="B", sources=[])])
    result = build_index(corpus, db, embedder_factory=lambda model: fake)
    assert result["unchanged"] == 1 and result["embedded"] == 0 and not fake.calls
    with sqlite3.connect(db) as connection:
        doc = json.loads(connection.execute("SELECT doc_json FROM questions").fetchone()[0])
        assert doc["answer"] == "B" and doc["sources"] == []


def test_model_change_rebuilds_all_vectors(tmp_path, capsys):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document(), document("b")])
    fake = FakeEmbedder()
    build_index(corpus, db, model="model/first", embedder_factory=lambda model: fake)
    class DifferentEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            return [row[:2] for row in super().encode(texts, **kwargs)]

    replacement = DifferentEmbedder()
    result = build_index(corpus, db, model="model/second", embedder_factory=lambda model: replacement)
    assert result["model_changed"] and result["embedded"] == len(replacement.calls) == 2
    assert "全量重建" in capsys.readouterr().err
    with sqlite3.connect(db) as connection:
        assert metadata(connection)["model"] == "model/second"
        assert metadata(connection)["dimension"] == 2


def test_keyword_updates_invalidate_only_changed_vectors_then_backfill(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    fake = FakeEmbedder()
    write_corpus(corpus, [document(), document("b")])
    build_index(corpus, db, embedder_factory=lambda model: fake)
    write_corpus(corpus, [document(text="新的警察職權"), document("b")])
    build_index(corpus, db, embed=False)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT question_id FROM question_vectors WHERE vector_id IN (SELECT vector_id FROM vectors WHERE embedding IS NOT NULL)").fetchall() == [("b",)]
    fake.calls.clear()
    result = build_index(corpus, db, embedder_factory=lambda model: fake)
    assert result["embedded"] == len(fake.calls) == 1
    assert result["updated"] == result["added"] == 0


def test_bad_encoder_rolls_back_existing_index(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embed=False)
    before = db.read_bytes()

    class InvalidEmbedder:
        rag_identity = "a" * 64
        def encode(self, texts, **kwargs):
            return [[0.0, 0.0]] * len(texts)

    write_corpus(corpus, [document(text="修改題目")])
    with pytest.raises(ValueError, match="zero"):
        build_index(corpus, db, embedder_factory=lambda model: InvalidEmbedder())
    assert db.read_bytes() == before


def test_missing_dependency_is_clear_and_cache_is_local(monkeypatch):
    import builtins
    from scripts.rag.retrieval import ROOT
    original_import = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("deliberately unavailable")
        return original_import(name, *args, **kwargs)

    for name in ("HF_HOME", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE",
                 "SENTENCE_TRANSFORMERS_HOME", "HF_ENDPOINT", "HF_HUB_DISABLE_IMPLICIT_TOKEN",
                 "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(name, "unused-outside-cache")
    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(RuntimeError, match="sentence-transformers.*--no-embed"):
        load_embedder("not/downloaded")
    import os
    assert os.environ["HF_HOME"] == str(ROOT / ".hf_cache")


def test_invalid_corpus_preserves_index(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embed=False)
    before = db.read_bytes()
    write_corpus(corpus, [document(), document()])
    with pytest.raises(ValueError, match="Duplicate question_id"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before


def test_batches_resume_after_interruption_and_hot_journal(tmp_path, capsys):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    docs = [document(identifier, f"警察題目{identifier}") for identifier in "abcde"]
    write_corpus(corpus, docs)

    class InterruptedEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            assert kwargs["batch_size"] == 2
            if self.calls:
                raise KeyboardInterrupt("interrupted second batch")
            return super().encode(texts, **kwargs)

    with pytest.raises(KeyboardInterrupt):
        build_index(corpus, db, batch_size=2, embedder_factory=lambda model: InterruptedEmbedder())
    assert "2/5" in capsys.readouterr().err
    with sqlite3.connect(db) as connection:
        before = connection.execute("SELECT vector_id, embedding FROM vectors WHERE embedding IS NOT NULL ORDER BY vector_id").fetchall()
        assert [row[0] for row in before] == ["q:a:000000", "q:b:000000"]
        assert metadata(connection)["dimension"] == 3
    # Exit without close/rollback after SQLite has spilled dirty pages: a real hot journal.
    subprocess.run([sys.executable, "-c", """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.create_function('rag_model_identity_builder_authorized', 0, lambda: 1)
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
connection.execute("UPDATE questions SET text_hash='interrupted' WHERE question_id='a'")
connection.execute("UPDATE vectors SET embedding=zeroblob(262144) WHERE vector_id='q:a:000000'")
os._exit(0)
""", str(db)], check=True)
    assert db.with_name(db.name + "-journal").stat().st_size > 512
    fake = FakeEmbedder()
    resumed = build_index(corpus, db, batch_size=2, embedder_factory=lambda model: fake)
    assert resumed["embedded"] == 3
    assert resumed["added"] == resumed["updated"] == 0
    assert fake.calls == ["passage: " + embedding_texts(doc)[0] for doc in docs[2:]]
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT vector_id, embedding FROM vectors WHERE embedding IS NOT NULL ORDER BY vector_id LIMIT 2").fetchall() == before
    write_corpus(corpus, [document("a", "題文改變後需要重算"), *docs[1:]])
    fake.calls.clear()
    assert build_index(corpus, db, embedder_factory=lambda model: fake)["embedded"] == 1
    assert fake.calls == ["passage: " + embedding_texts(document("a", "題文改變後需要重算"))[0]]


def test_interrupted_model_change_resumes_new_model_only(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document(identifier) for identifier in "abc"])
    build_index(corpus, db, model="old", embedder_factory=lambda model: FakeEmbedder())

    class InterruptedReplacement(FakeEmbedder):
        def encode(self, texts, **kwargs):
            if self.calls:
                raise RuntimeError("interrupted")
            return [row[:2] for row in super().encode(texts, **kwargs)]

    replacement = InterruptedReplacement()
    with pytest.raises(RuntimeError, match="interrupted"):
        build_index(corpus, db, model="new", batch_size=1, embedder_factory=lambda model: replacement)
    with sqlite3.connect(db) as connection:
        assert metadata(connection)["model"] == "new"
        assert metadata(connection)["dimension"] == 2
        assert connection.execute("SELECT question_id FROM question_vectors WHERE vector_id IN (SELECT vector_id FROM vectors WHERE embedding IS NOT NULL)").fetchall() == [("a",)]
    replacement.calls.clear()
    resumed = build_index(corpus, db, model="new", batch_size=2, embedder_factory=lambda model: replacement)
    assert resumed["embedded"] == 2 and not resumed["model_changed"]


@pytest.mark.parametrize("requested,available,expected", [
    ("auto", True, "cuda"), ("auto", False, "cpu"), ("cpu", True, "cpu"),
    ("cuda", True, "cuda"), ("cuda", False, None),
])
def test_device_selection_without_real_model(monkeypatch, requested, available, expected):
    calls = []
    monkeypatch.setattr("scripts.rag.retrieval.resolve_model_revision", lambda *a, **kw: "a" * 40)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: available)))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(
        SentenceTransformer=lambda model, **kwargs: calls.append((model, kwargs))))
    if expected is None:
        with pytest.raises(RuntimeError, match="CUDA"):
            load_embedder("fake", device=requested)
        assert not calls
    else:
        load_embedder("fake", device=requested)
        assert calls[0][1]["device"] == expected
        assert calls[0][1]["token"] is False
        assert calls[0][1]["trust_remote_code"] is False
        assert calls[0][1]["revision"] == "a" * 40


def test_load_embedder_preserves_default_download_policy_without_network(monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        pytest.fail("mocked model load must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.setattr("scripts.rag.retrieval.resolve_model_revision", lambda *a, **kw: "a" * 40)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    calls, encoder = [], object()

    def mock_model(model, **kwargs):
        calls.append((model, kwargs))
        return encoder

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=mock_model))
    assert load_embedder("not-yet-cached", device="cpu") is encoder
    assert calls[0][0] == "not-yet-cached"
    assert "local_files_only" not in calls[0][1]
    assert calls[0][1]["revision"] == "a" * 40
    assert calls[0][1]["trust_remote_code"] is False and calls[0][1]["token"] is False


def test_device_change_does_not_invalidate_vectors(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    fake = FakeEmbedder()
    fake.device = "cpu"
    build_index(corpus, db, device="cpu", embedder_factory=lambda model: fake)
    with sqlite3.connect(db) as connection:
        assert metadata(connection)["device"] == "cpu"
    before = db.read_bytes()
    result = build_index(corpus, db, device="cuda", embedder_factory=lambda model: pytest.fail("no-op loads model"))
    assert result["embedded"] == 0 and db.read_bytes() == before


def test_batch_size_validation():
    with pytest.raises(ValueError, match="batch_size"):
        build_index("unused.jsonl", batch_size=0)


@pytest.mark.parametrize("stale_vectors", [False, True])
def test_keyword_only_noop_preserves_bytes_and_backfills_vectors(tmp_path, stale_vectors):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever, vector_blob

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", "警察題目", passage="獨有文章")
    write_corpus(corpus, [doc])
    def unexpected(_):
        pytest.fail("keyword-only build must not load a model")

    build_index(corpus, db, embed=False, embedder_factory=unexpected)
    stale_blob = vector_blob([1., 0., 0.])
    if stale_vectors:
        main, passage = embedding_texts(doc)
        passage_id = "p:" + hashlib.sha256(passage.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.executemany("INSERT INTO vectors VALUES (?,?,?)",
                                   [("q:a:000000", main, stale_blob), (passage_id, passage, stale_blob)])
            connection.executemany("INSERT INTO question_vectors VALUES (?,?)", [("a", "q:a:000000"), ("a", passage_id)])
    before = db.read_bytes()
    result = build_index(corpus, db, embed=False, embedder_factory=unexpected)
    assert not result["index_changed"] and result["embedded"] == 0
    assert db.read_bytes() == before
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="缺漏或過期|模型身分"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    fake = FakeEmbedder()
    if stale_vectors:
        with pytest.raises(ValueError, match="模型身分"):
            build_index(corpus, db, embedder_factory=lambda _: fake)
        assert db.read_bytes() == before and not fake.calls
        return
    result = build_index(corpus, db, embedder_factory=lambda _: fake)
    assert result["embedded"] == len(fake.calls) == 2
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM question_vectors").fetchone()[0] == 2
        assert all(row[0] != stale_blob for row in connection.execute("SELECT embedding FROM vectors"))
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("警察", mode="vector")[0]["question_id"] == "a"
    finally:
        retriever.close()


def make_legacy_index(monkeypatch, corpus, db, docs, model="fake-e5", encoder=None):
    from scripts.rag import build_index as builder, retrieval

    write_corpus(corpus, docs)
    with monkeypatch.context() as patch:
        patch.setattr(builder, "embedding_texts", retrieval.embedding_texts_v1)
        build_index(corpus, db, model=model, embedder_factory=lambda _: encoder or FakeEmbedder())
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM meta WHERE key='embedding_text_version'")


@pytest.mark.parametrize("explicit_version", [False, True])
def test_legacy_migration_reencodes_only_changed_inputs_and_is_idempotent(tmp_path, monkeypatch, explicit_version):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    conflict = document("a", options={"A": "答案甲", "B": "答案乙"}, passage="共用文章",
                        answer_conflicts=[{"value": "A"}, {"value": "B"}])
    normal = document("b", options={"A": "答案甲", "B": "答案乙"}, passage="共用文章")
    # A conflict without a formerly labeled answer does not change the input.
    no_answer = document("c", passage="共用文章", answer=None, answer_conflicts=[{"value": "送分"}])
    make_legacy_index(monkeypatch, corpus, db, [conflict, normal, no_answer])
    if explicit_version:
        with sqlite3.connect(db) as connection:
            connection.execute("INSERT INTO meta VALUES ('embedding_text_version', '1')")
    with sqlite3.connect(db) as connection:
        before = dict(connection.execute("SELECT vector_id, embedding FROM vectors"))
    fake = FakeEmbedder()
    result = build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)
    assert result["embedded"] == len(fake.calls) == 1
    assert "正確選項" not in fake.calls[0] and "答案乙" in fake.calls[0]
    with sqlite3.connect(db) as connection:
        after = dict(connection.execute("SELECT vector_id, embedding FROM vectors"))
        assert metadata(connection)["embedding_text_version"] == 2
        assert all(after[key] == blob for key, blob in before.items() if not key.startswith("q:a:"))
    first = db.read_bytes()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: pytest.fail("loaded model"))["embedded"] == 0
    assert db.read_bytes() == first


def test_legacy_no_embed_and_interrupted_migration_resume_safely(tmp_path, monkeypatch):
    from scripts.rag.retrieval import Retriever

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    docs = [document(key, options={"A": "答案甲", "B": "答案乙"}, passage="共用文章",
                     answer_conflicts=[{"value": "A"}, {"value": "B"}]) for key in "ab"]
    docs.append(document("c", options={"A": "答案甲"}, passage="共用文章"))
    make_legacy_index(monkeypatch, corpus, db, docs)
    build_index(corpus, db, embed=False)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT DISTINCT question_id FROM question_vectors WHERE vector_id LIKE 'q:%'").fetchall() == [("c",)]
        assert connection.execute("SELECT DISTINCT question_id FROM question_vectors WHERE vector_id LIKE 'p:%' ORDER BY question_id").fetchall() == [("a",), ("b",), ("c",)]
        assert metadata(connection)["embedding_text_version"] == 2
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="缺漏或過期"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()

    class Interrupted(FakeEmbedder):
        def encode(self, texts, **kwargs):
            if self.calls:
                raise RuntimeError("interrupt")
            return super().encode(texts, **kwargs)

    with pytest.raises(RuntimeError, match="interrupt"):
        build_index(corpus, db, model="fake-e5", batch_size=1, embedder_factory=lambda _: Interrupted())
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        with pytest.raises(ValueError, match="缺漏或過期"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    fake = FakeEmbedder()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)["embedded"] == 1
    assert len(fake.calls) == 1 and "正確選項" not in fake.calls[0]


@pytest.mark.parametrize("version", [0, 3, "2", None, True])
def test_unsupported_embedding_version_refuses_build_and_vector_query(tmp_path, version):
    from scripts.rag.retrieval import Retriever

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT OR REPLACE INTO meta VALUES ('embedding_text_version', ?)", (json.dumps(version),))
    before = db.read_bytes()
    with pytest.raises(ValueError, match="版本"):
        build_index(corpus, db, embedder_factory=lambda _: pytest.fail("loaded model"))
    assert db.read_bytes() == before
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="版本"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()


def test_unknown_schema_does_not_get_rebuilt_or_vector_searched(tmp_path):
    from scripts.rag.retrieval import Retriever

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE meta SET value='3' WHERE key='schema_version'")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="schema.*版本"):
        build_index(corpus, db, embedder_factory=lambda _: pytest.fail("loaded model"))
    assert db.read_bytes() == before
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="schema"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()


@pytest.mark.parametrize("schema", ["missing", "null"])
def test_existing_index_with_missing_or_null_schema_is_not_modified(tmp_path, schema):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with sqlite3.connect(db) as connection:
        if schema == "missing":
            connection.execute("DELETE FROM meta WHERE key='schema_version'")
        else:
            connection.execute("UPDATE meta SET value='null' WHERE key='schema_version'")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="schema 版本"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before


def test_existing_unversioned_database_is_not_treated_as_new(tmp_path):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("CREATE TABLE other_data(value TEXT)")
        connection.execute("INSERT INTO other_data VALUES ('preserve')")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="schema 版本"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before


def test_legacy_migration_persists_changed_vector_used_by_retriever(tmp_path, monkeypatch):
    from scripts.rag.retrieval import Retriever

    class InputSensitiveEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            self.calls.extend(texts)
            return [[0., 1., 0.] if text.startswith("query:") else
                    [1., 0., 0.] if "正確選項：" in text else
                    [0., 1., 0.] if "衝突特徵" in text else [.6, .8, 0.] for text in texts]

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    docs = [document("a", "衝突特徵", options={"A": "甲", "B": "乙"},
                     answer_conflicts=[{"value": "A"}, {"value": "B"}]), document("b", "其他背景")]
    fake = InputSensitiveEmbedder()
    make_legacy_index(monkeypatch, corpus, db, docs, encoder=fake)
    with sqlite3.connect(db) as connection:
        before = dict(connection.execute("SELECT vector_id,embedding FROM vectors"))
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("尋找衝突", mode="vector")[0]["question_id"] == "b"
    finally:
        retriever.close()
    fake.calls.clear()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)["embedded"] == 1
    with sqlite3.connect(db) as connection:
        after = dict(connection.execute("SELECT vector_id,embedding FROM vectors"))
    assert before["q:a:000000"] != after["q:a:000000"]
    assert before["q:b:000000"] == after["q:b:000000"]
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("尋找衝突", mode="vector")[0]["question_id"] == "a"
    finally:
        retriever.close()


def test_no_embed_retains_unique_passage_but_rejects_incomplete_index(tmp_path, monkeypatch):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever
    from scripts.rag.update_index import MODEL, seed_info

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", options={"A": "甲", "B": "乙"}, passage="獨有文章",
                   answer_conflicts=[{"value": "A"}, {"value": "B"}])
    make_legacy_index(monkeypatch, corpus, db, [doc], model=MODEL)
    with closing(sqlite3.connect(db)) as connection:
        original = connection.execute("SELECT vector_id,text,embedding FROM vectors WHERE vector_id LIKE 'p:%'").fetchone()
    build_index(corpus, db, embed=False)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT vector_id,text,embedding FROM vectors WHERE vector_id LIKE 'p:%'").fetchone() == original
        assert set(connection.execute("SELECT vector_id FROM question_vectors").fetchall()) == {(original[0],), ("pending:a",)}
    with pytest.raises(ValueError, match="不完整"):
        seed_info(db)
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="缺漏或過期"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    before_repeat = db.read_bytes()
    build_index(corpus, db, embed=False)
    assert db.read_bytes() == before_repeat
    fake = FakeEmbedder()
    assert build_index(corpus, db, model=MODEL, embedder_factory=lambda _: fake)["embedded"] == 1
    assert len(fake.calls) == 1 and "獨有文章" not in fake.calls[0]
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT vector_id,text,embedding FROM vectors WHERE vector_id LIKE 'p:%'").fetchone() == original
    seed_info(db)


@pytest.mark.parametrize("change", ["passage_changed", "passage_removed", "question_removed"])
def test_no_embed_discards_obsolete_passages(tmp_path, monkeypatch, change):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", options={"A": "甲", "B": "乙"}, passage="舊文章",
                   answer_conflicts=[{"value": "A"}, {"value": "B"}])
    make_legacy_index(monkeypatch, corpus, db, [doc])
    build_index(corpus, db, embed=False)
    if change == "question_removed":
        docs = []
    else:
        doc["passage"] = "新文章" if change == "passage_changed" else ""
        docs = [doc]
    write_corpus(corpus, docs)
    build_index(corpus, db, embed=False)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM vectors WHERE text='舊文章'").fetchone()[0] == 0
    if docs:
        retriever = Retriever(db, embedder=FakeEmbedder())
        try:
            with pytest.raises(ValueError, match="缺漏或過期"):
                retriever.search("警察", mode="vector")
        finally:
            retriever.close()
    fake = FakeEmbedder()
    result = build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)
    assert result["embedded"] == {"passage_changed": 2, "passage_removed": 1, "question_removed": 0}[change]


@pytest.mark.parametrize("change", ["replace", "remove"])
def test_passage_only_no_embed_preserves_main_and_safely_backfills(tmp_path, change):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever
    from scripts.rag.update_index import MODEL, seed_info

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", "題目不變", passage="舊文章")
    write_corpus(corpus, [doc])
    build_index(corpus, db, model=MODEL, embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection:
        old_main = connection.execute("SELECT embedding FROM vectors WHERE vector_id='q:a:000000'").fetchone()[0]
    doc["passage"] = "新文章" if change == "replace" else ""
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=False)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT embedding FROM vectors WHERE vector_id='q:a:000000'").fetchone()[0] == old_main
        assert connection.execute("SELECT count(*) FROM vectors WHERE text='舊文章'").fetchone()[0] == 0
        if change == "replace":
            assert metadata(connection)["pending_question_vectors"] == {"a": ["passage"]}
            assert connection.execute("SELECT embedding FROM vectors WHERE vector_id='pending:a'").fetchone() == (None,)
            # Older readers only check question coverage and NULL blobs.
            assert {row[0] for row in connection.execute("SELECT question_id FROM question_vectors")} == {"a"}
            assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 1
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("題目", mode="keyword")
        if change == "replace":
            with pytest.raises(ValueError, match="缺漏或過期"):
                retriever.search("題目", mode="vector")
        else:
            assert retriever.search("題目", mode="vector")
    finally:
        retriever.close()
    if change == "replace":
        with pytest.raises(ValueError, match="不完整"):
            seed_info(db)
    else:
        seed_info(db)
    before_repeat = db.read_bytes()
    build_index(corpus, db, embed=False)
    assert db.read_bytes() == before_repeat
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == (change == "replace")
    fake = FakeEmbedder()
    def factory(_):
        if change == "remove":
            pytest.fail("removing a passage must not load the model")
        return fake
    result = build_index(corpus, db, model=MODEL, embedder_factory=factory)
    assert result["embedded"] == (change == "replace")
    assert fake.calls == (["新文章"] if change == "replace" else [])
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT embedding FROM vectors WHERE vector_id='q:a:000000'").fetchone()[0] == old_main
        assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 0
    seed_info(db)
    after = db.read_bytes()
    assert build_index(corpus, db, model=MODEL, embedder_factory=lambda _: pytest.fail("no-op loaded model"))["embedded"] == 0
    assert db.read_bytes() == after


@pytest.mark.parametrize("embed_on_removal", [False, True])
def test_removing_a_pending_passage_clears_marker_without_reencoding_main(tmp_path, embed_on_removal):
    from contextlib import closing
    from scripts.rag.update_index import MODEL, seed_info

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", passage="舊文章")
    write_corpus(corpus, [doc])
    build_index(corpus, db, model=MODEL, embedder_factory=lambda _: FakeEmbedder())
    doc["passage"] = "新文章"
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=False)
    doc["passage"] = ""
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=embed_on_removal, model=MODEL,
                embedder_factory=lambda _: pytest.fail("removing passage loaded model"))
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 0
        assert metadata(connection)["pending_question_vectors"] == {}
    seed_info(db)
    before = db.read_bytes()
    assert build_index(corpus, db, model=MODEL, embedder_factory=lambda _: pytest.fail("loaded model"))["embedded"] == 0
    assert db.read_bytes() == before


def test_no_embed_preserves_every_chunk_of_unchanged_long_passage(tmp_path, monkeypatch):
    from contextlib import closing

    class Tokenizer:
        def encode(self, text, add_special_tokens=False):
            return list(text) + (["<s>", "</s>"] if add_special_tokens else [])
        def decode(self, tokens, **kwargs):
            return "".join(tokens)
        def num_special_tokens_to_add(self, pair):
            return 2

    class ChunkEmbedder(FakeEmbedder):
        tokenizer = Tokenizer()
        max_seq_length = 28

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    passage = "".join(chr(0x4E00 + i) for i in range(100))
    doc = document("a", "題目", options={"A": "甲", "B": "乙"}, passage=passage,
                   answer_conflicts=[{"value": "A"}, {"value": "B"}])
    fake = ChunkEmbedder()
    make_legacy_index(monkeypatch, corpus, db, [doc], model="chunk-model", encoder=fake)
    with closing(sqlite3.connect(db)) as connection:
        before = connection.execute("SELECT vector_id,text,embedding FROM vectors WHERE vector_id LIKE 'p:%' ORDER BY vector_id").fetchall()
    assert len(before) > 1
    build_index(corpus, db, embed=False)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT vector_id,text,embedding FROM vectors WHERE vector_id LIKE 'p:%' ORDER BY vector_id").fetchall() == before
        assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 1
    repeat = db.read_bytes()
    build_index(corpus, db, embed=False)
    assert db.read_bytes() == repeat
    fake.calls.clear()
    result = build_index(corpus, db, model="chunk-model", embedder_factory=lambda _: fake)
    assert result["embedded"] == len(fake.calls) > 0
    assert not {row[1] for row in before}.intersection(fake.calls)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT vector_id,text,embedding FROM vectors WHERE vector_id LIKE 'p:%' ORDER BY vector_id").fetchall() == before


@pytest.mark.parametrize("question_id,vector_id", [
    ("a", None), (None, "q:a:000000"), ("a", sqlite3.Binary(b"bad-vector")),
    (sqlite3.Binary(b"bad-question"), "q:a:000000"),
])
def test_invalid_link_types_fail_build_and_vector_query_without_mutation(tmp_path, question_id, vector_id):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("INSERT INTO question_vectors VALUES (?,?)", (question_id, vector_id))
    before = db.read_bytes()
    with pytest.raises(ValueError, match="連結無效"):
        build_index(corpus, db, embed=False, embedder_factory=lambda _: pytest.fail("loaded model"))
    assert db.read_bytes() == before
    retriever = Retriever(db, embedder_factory=lambda _: pytest.fail("loaded model"))
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="連結無效"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    assert db.read_bytes() == before


def test_git_head_builder_cannot_complete_pending_marker_and_new_builder_can_backfill(tmp_path):
    import os
    from contextlib import closing

    legacy = git_head_legacy_rag(tmp_path)
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", "警察題目", passage="舊文章")
    write_corpus(corpus, [doc])
    build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: FakeEmbedder())
    doc["passage"] = "新文章"
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=False)
    pending_bytes = db.read_bytes()
    with closing(sqlite3.connect(db)) as connection:
        guards = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'rag_pending_vector_no_%'")}
    assert guards == {"rag_pending_vector_no_encode", "rag_pending_vector_no_delete"}
    build_index(corpus, db, embed=False)
    assert db.read_bytes() == pending_bytes

    runner = """
import sqlite3, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from build_index import build_index
from retrieval import Retriever
class Fake:
    def encode(self, texts, **kwargs):
        return [[1., 2., 3.] for _ in texts]
corpus, db = Path(sys.argv[2]), Path(sys.argv[3])
before = db.read_bytes()
def reader_rejects():
    retriever = Retriever(db, embedder=Fake())
    try:
        try:
            retriever.search('警察', mode='vector')
        except ValueError:
            return
        raise AssertionError('Git HEAD reader accepted an incomplete index')
    finally:
        retriever.close()
reader_rejects()
for embed, model in ((False, 'fake-e5'), (True, 'fake-e5'), (True, 'different-model')):
    try:
        build_index(corpus, db, embed=embed, model=model, embedder_factory=lambda _: Fake())
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
        assert any(key in str(exc).lower() for key in ('pending', 'rag_v2_builder_authorized', 'rag_model_identity_builder_authorized'))
    else:
        raise AssertionError('Git HEAD builder accepted a pending marker')
    reader_rejects()
    assert db.read_bytes() == before
"""
    result = subprocess.run([sys.executable, "-c", runner, str(legacy), str(corpus), str(db)],
                            cwd=legacy, capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert db.read_bytes() == pending_bytes
    class BrokenEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            raise RuntimeError("encoding failed")
    with pytest.raises(RuntimeError, match="encoding failed"):
        build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: BrokenEmbedder())
    assert db.read_bytes() == pending_bytes
    with closing(sqlite3.connect(db)) as connection:
        assert {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'rag_pending_vector_no_%'")} == guards
    fake = FakeEmbedder()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)["embedded"] == 1
    assert fake.calls == ["passage: 新文章"]
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' "
                                  "AND name LIKE 'rag_pending_vector_no_%'").fetchone()[0] == 0
    ready = db.read_bytes()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: pytest.fail("loaded model"))["embedded"] == 0
    assert db.read_bytes() == ready


def git_head_legacy_rag(tmp_path):
    from pathlib import Path
    fixture = Path(__file__).resolve().parent / "fixtures/rag_baseline_9cc4304"
    directory = tmp_path / "legacy-rag"
    directory.mkdir()
    for name in ("build_index.py", "retrieval.py", "build_corpus.py"):
        (directory / name).write_bytes((fixture / name).read_bytes())
    return directory


def normalized_fixture_sha256(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


@pytest.mark.parametrize("name,expected", [
    ("build_index.py", "73091934dc71c5c0652a33b0642d5c5db1fb5fda6ecb460cfc5787013f569c59"),
    ("retrieval.py", "1fa76b6cdb7d4f8a9dc3e4c196c7edb66098c1c254780866516bdac69660233e"),
    ("build_corpus.py", "6e09af046f92477e3082726c72ec0ff107accb3b6f1257eb752d4b4fc86b64f1"),
])
def test_git_head_fixture_preserves_original_files(name, expected):
    from pathlib import Path
    fixture = Path(__file__).resolve().parent / "fixtures/rag_baseline_9cc4304" / name
    source = fixture.read_bytes()
    lf = source.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    assert normalized_fixture_sha256(source) == normalized_fixture_sha256(lf) == normalized_fixture_sha256(crlf) == expected
    assert normalized_fixture_sha256(crlf + b"# altered\r\n") != expected


def attempt_legacy_build(legacy, corpus, db, *, model="fake-e5", read="skip"):
    import os
    runner = """
import sqlite3, sys
sys.path.insert(0, sys.argv[1])
from build_index import build_index
from retrieval import Retriever
class Fake:
    def encode(self, texts, **kwargs):
        return [[1., 2., 3.] for _ in texts]
corpus, db, model, read = sys.argv[2:]
if read != 'skip':
    retriever = Retriever(db, embedder=Fake())
    try:
        try:
            rows = retriever.search('警察', mode='vector')
        except ValueError:
            assert read == 'reject'
        else:
            assert read == 'ok' and rows
    finally:
        retriever.close()
try:
    build_index(corpus, db, model=model, batch_size=1, embedder_factory=lambda _: Fake())
except sqlite3.Error as exc:
    print('blocked:', type(exc).__name__, str(exc))
else:
    raise AssertionError('Git HEAD builder committed version-1 input rules')
"""
    return subprocess.run([sys.executable, "-c", runner, str(legacy), str(corpus), str(db), model, read],
                          cwd=legacy, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


@pytest.mark.parametrize("line_ending", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_legacy_builder_and_reader_use_fixture_without_git(tmp_path, monkeypatch, line_ending):
    from pathlib import Path

    original_run = subprocess.run
    def reject_git(args, *positional, **kwargs):
        assert Path(args[0]).name.lower() not in ("git", "git.exe"), "fixture must not invoke Git"
        return original_run(args, *positional, **kwargs)
    monkeypatch.setattr(subprocess, "run", reject_git)
    legacy = git_head_legacy_rag(tmp_path)
    for source in legacy.glob("*.py"):
        lf = source.read_bytes().replace(b"\r\n", b"\n")
        source.write_bytes(lf.replace(b"\n", line_ending))
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "警察題目")])
    build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: FakeEmbedder())
    before = db.read_bytes()
    attempt = attempt_legacy_build(legacy, corpus, db, read="ok")
    assert attempt.returncode == 0, attempt.stdout + attempt.stderr
    assert db.read_bytes() == before


def test_git_head_cannot_write_conflict_changes_to_complete_v2_index(tmp_path):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever

    class InputSensitive(FakeEmbedder):
        def encode(self, texts, **kwargs):
            self.calls.extend(texts)
            return [[1., 0., 0.] if "正確選項：" in text else [0., 1., 0.] for text in texts]

    legacy = git_head_legacy_rag(tmp_path)
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", "警察題目", options={"A": "甲", "B": "乙"})
    write_corpus(corpus, [doc])
    fake = InputSensitive()
    build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)
    before = db.read_bytes()
    doc["answer_conflicts"] = [{"value": "A"}, {"value": "B"}]
    write_corpus(corpus, [doc])
    attempt = attempt_legacy_build(legacy, corpus, db, read="ok")
    assert attempt.returncode == 0, attempt.stdout + attempt.stderr
    assert db.read_bytes() == before
    with closing(sqlite3.connect(db)) as connection:
        assert "answer_conflicts" not in json.loads(connection.execute("SELECT doc_json FROM questions").fetchone()[0])
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)["embedded"] == 1
    retriever = Retriever(db, embedder=fake)
    try:
        row = retriever.search("警察", mode="vector")[0]
        assert row["answer_confidence"] == "disputed" and row["score"] == pytest.approx(1.)
    finally:
        retriever.close()


def test_git_head_cannot_commit_early_null_batch_or_new_stale_document(tmp_path):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever

    legacy = git_head_legacy_rag(tmp_path)
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    docs = [document("a", "警察甲", passage="舊文章"), document("b", "警察乙", passage="另一文章")]
    write_corpus(corpus, docs)
    build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: FakeEmbedder())
    docs[0]["passage"] = "新文章"
    write_corpus(corpus, docs)
    build_index(corpus, db, embed=False)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.create_function("rag_model_identity_builder_authorized", 0, lambda: 1)
        connection.execute("UPDATE vectors SET embedding=NULL WHERE text='另一文章'")
        pending = [row[0] for row in connection.execute("SELECT vector_id FROM vectors WHERE embedding IS NULL ORDER BY vector_id")]
    assert pending[0].startswith("p:") and pending[1].startswith("pending:")
    before = db.read_bytes()
    docs.append(document("c", "警察新題", options={"A": "甲", "B": "乙"},
                         answer_conflicts=[{"value": "A"}, {"value": "B"}]))
    write_corpus(corpus, docs)
    attempt = attempt_legacy_build(legacy, corpus, db, read="reject")
    assert attempt.returncode == 0, attempt.stdout + attempt.stderr
    assert db.read_bytes() == before
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM questions WHERE question_id='c'").fetchone()[0] == 0
    fake = FakeEmbedder()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)["embedded"] == 3
    with closing(sqlite3.connect(db)) as connection:
        assert "正確選項" not in connection.execute("SELECT text FROM vectors WHERE vector_id='q:c:000000'").fetchone()[0]
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("警察", mode="vector", k=3)
    finally:
        retriever.close()


def test_git_head_cannot_replace_initial_model_less_pending_index(tmp_path):
    from scripts.rag.retrieval import Retriever

    legacy = git_head_legacy_rag(tmp_path)
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "警察題目", passage="文章")])
    build_index(corpus, db, embed=False)
    before = db.read_bytes()
    attempt = attempt_legacy_build(legacy, corpus, db, read="reject")
    assert attempt.returncode == 0, attempt.stdout + attempt.stderr
    assert db.read_bytes() == before
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        with pytest.raises(ValueError, match="缺漏或過期"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    fake = FakeEmbedder()
    assert build_index(corpus, db, model="fake-e5", embedder_factory=lambda _: fake)["embedded"] == 2


def test_pending_model_change_preserves_guards_user_triggers_and_backup(tmp_path):
    from contextlib import closing
    from scripts.rag.retrieval import Retriever

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("a", "警察題目", passage="舊文章")
    write_corpus(corpus, [doc])
    build_index(corpus, db, model="old", embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("CREATE TRIGGER user_vector_trigger AFTER INSERT ON vectors BEGIN SELECT 1; END")
    doc["passage"] = "新文章"
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=False)
    before = db.read_bytes()
    with closing(sqlite3.connect(db)) as connection:
        triggers = set(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'"))
    class Broken(FakeEmbedder):
        def encode(self, texts, **kwargs):
            raise RuntimeError("first batch failed")
    with pytest.raises(RuntimeError, match="first batch failed"):
        build_index(corpus, db, model="new", embedder_factory=lambda _: Broken())
    assert db.read_bytes() == before
    with closing(sqlite3.connect(db)) as connection:
        assert set(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")) == triggers
    fake = FakeEmbedder()
    result = build_index(corpus, db, model="new", embedder_factory=lambda _: fake)
    assert result["model_changed"] and result["embedded"] == 2
    with closing(sqlite3.connect(db)) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {"user_vector_trigger", "rag_v2_writer_guard"}.issubset(names)
        backup = tmp_path / "backup.sqlite"
        with closing(sqlite3.connect(backup)) as target:
            connection.backup(target)
    retriever = Retriever(backup, embedder=fake)
    try:
        assert retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    ready = db.read_bytes()
    assert not build_index(corpus, db, model="new", embedder_factory=lambda _: pytest.fail("no-op loaded model"))["index_changed"]
    assert db.read_bytes() == ready


def test_existing_v2_index_installs_writer_guard_once_and_reports_change(tmp_path):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("DROP TRIGGER rag_v2_writer_guard")
    before = db.read_bytes()
    result = build_index(corpus, db, embedder_factory=lambda _: pytest.fail("loaded model"))
    assert result["index_changed"] and result["embedded"] == 0 and db.read_bytes() != before
    ready = db.read_bytes()
    assert not build_index(corpus, db, embedder_factory=lambda _: pytest.fail("loaded model"))["index_changed"]
    assert db.read_bytes() == ready


@pytest.mark.parametrize("trigger_name", ["rag_v2_writer_guard", "rag_pending_vector_no_encode", "rag_pending_vector_no_delete",
                                         "rag_model_identity_insert_guard", "rag_model_identity_update_guard",
                                         "rag_model_identity_delete_guard"])
@pytest.mark.parametrize("case", ["lower", "upper", "mixed"])
@pytest.mark.parametrize("table", ["vectors", "questions"])
def test_reserved_user_trigger_is_never_overwritten_or_removed(tmp_path, trigger_name, case, table):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    collision = (trigger_name if case == "lower" else trigger_name.upper() if case == "upper" else
                 "".join(char.upper() if index % 2 else char for index, char in enumerate(trigger_name)))
    user_sql = f"CREATE TRIGGER {collision} AFTER INSERT ON {table} BEGIN SELECT 42; END"
    with closing(sqlite3.connect(db)) as connection, connection:
        if trigger_name == "rag_v2_writer_guard" or trigger_name.startswith("rag_model_identity_"):
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(user_sql)
    before = db.read_bytes()
    with pytest.raises(ValueError, match="觸發器名稱已被使用"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=? COLLATE BINARY",
                                  (collision,)).fetchone() == (user_sql,)


@pytest.mark.parametrize("table", ["vectors", "question_vectors"])
def test_schema_rebuild_refuses_to_drop_user_triggers(tmp_path, table):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        connection.execute(f"CREATE TRIGGER user_preserved AFTER INSERT ON {table} BEGIN SELECT 1; END")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="自訂觸發器"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before


@pytest.mark.parametrize("table", ["VECTORS", "VeCtOrS", "QUESTION_VECTORS", "QuEsTiOn_VeCtOrS"])
def test_legacy_case_variant_table_trigger_is_preserved_before_any_ddl(tmp_path, monkeypatch, table):
    from contextlib import closing
    from scripts.rag import build_index as builder

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "legacy.sqlite"
    write_corpus(corpus, [document()])
    trigger_sql = f'CREATE TRIGGER user_preserved AFTER INSERT ON "{table}" BEGIN SELECT 42; END'
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        connection.execute("INSERT INTO meta VALUES ('schema_version','1')")
        if table.casefold() == "vectors":
            connection.execute(f'CREATE TABLE "{table}" (question_id TEXT PRIMARY KEY,embedding BLOB)')
            connection.execute(f'INSERT INTO "{table}" VALUES (?,?)', ("old", b"old-vector"))
        else:
            connection.execute(f'CREATE TABLE "{table}" (question_id TEXT,vector_id TEXT,PRIMARY KEY(question_id,vector_id))')
            connection.execute(f'INSERT INTO "{table}" VALUES (?,?)', ("old", "old-vector"))
        connection.execute(trigger_sql)
    before = db.read_bytes()
    statements = []
    original_connect = sqlite3.connect
    def traced_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection
    with monkeypatch.context() as patch:
        patch.setattr(builder.sqlite3, "connect", traced_connect)
        with pytest.raises(ValueError, match="自訂觸發器"):
            build_index(corpus, db, embed=False)
    assert db.read_bytes() == before
    assert not any(statement.lstrip().upper().startswith(("CREATE ", "DROP ", "ALTER ")) for statement in statements)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='user_preserved'").fetchone() == (trigger_sql,)


@pytest.mark.parametrize("table", ["VECTORS", "VeCtOrS", "QUESTION_VECTORS", "QuEsTiOn_VeCtOrS"])
def test_legacy_case_variant_table_migrates_when_no_user_trigger(tmp_path, table):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "legacy.sqlite"
    write_corpus(corpus, [document()])
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        connection.execute("INSERT INTO meta VALUES ('schema_version','1')")
        if table.casefold() == "vectors":
            connection.execute(f'CREATE TABLE "{table}" (question_id TEXT PRIMARY KEY,embedding BLOB)')
        else:
            connection.execute(f'CREATE TABLE "{table}" (question_id TEXT,vector_id TEXT,PRIMARY KEY(question_id,vector_id))')
    assert build_index(corpus, db, embed=False)["added"] == 1
    with closing(sqlite3.connect(db)) as connection:
        assert metadata(connection)["schema_version"] == 2
        assert connection.execute("SELECT count(*) FROM questions").fetchone()[0] == 1


def rename_index_tables_for_case_test(connection, meta_name, links_name):
    connection.execute('ALTER TABLE meta RENAME TO temporary_meta_case')
    connection.execute(f'ALTER TABLE temporary_meta_case RENAME TO "{meta_name}"')
    connection.execute('ALTER TABLE question_vectors RENAME TO temporary_links_case')
    connection.execute(f'ALTER TABLE temporary_links_case RENAME TO "{links_name}"')


@pytest.mark.parametrize("meta_name,links_name", [("META", "QUESTION_VECTORS"), ("MeTa", "QuEsTiOn_VeCtOrS")])
@pytest.mark.parametrize("question_id,vector_id", [("a", None), (None, "q:a:000000"), ("a", sqlite3.Binary(b"bad"))])
def test_case_variant_metadata_and_links_reject_invalid_values(tmp_path, meta_name, links_name, question_id, vector_id):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        rename_index_tables_for_case_test(connection, meta_name, links_name)
        connection.execute(f'INSERT INTO "{links_name}" VALUES (?,?)', (question_id, vector_id))
        assert metadata(connection)["schema_version"] == 2
    before = db.read_bytes()
    with pytest.raises(ValueError, match="連結無效"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before


@pytest.mark.parametrize("meta_name,links_name", [("META", "QUESTION_VECTORS"), ("MeTa", "QuEsTiOn_VeCtOrS")])
def test_case_variant_metadata_and_links_allow_valid_noop(tmp_path, meta_name, links_name):
    from contextlib import closing

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        rename_index_tables_for_case_test(connection, meta_name, links_name)
    before = db.read_bytes()
    result = build_index(corpus, db, embedder_factory=lambda _: pytest.fail("no-op loaded model"))
    assert not result["index_changed"] and db.read_bytes() == before
