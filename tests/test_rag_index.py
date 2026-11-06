import hashlib
import json
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.rag.build_index import build_index
from scripts.rag.retrieval import load_embedder, metadata


class FakeEmbedder:
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
        assert connection.execute("SELECT question_id FROM vectors ORDER BY question_id").fetchall() == [("a",), ("c",), ("d",)]
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
        assert connection.execute("SELECT question_id FROM vectors").fetchall() == [("b",)]
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
        before = connection.execute("SELECT question_id, embedding FROM vectors ORDER BY question_id").fetchall()
        assert [row[0] for row in before] == ["a", "b"]
        assert metadata(connection)["dimension"] == 3
    # Exit without close/rollback after SQLite has spilled dirty pages: a real hot journal.
    subprocess.run([sys.executable, "-c", """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
connection.execute("UPDATE questions SET text_hash='interrupted' WHERE question_id='a'")
connection.execute("UPDATE vectors SET embedding=zeroblob(262144) WHERE question_id='a'")
os._exit(0)
""", str(db)], check=True)
    assert db.with_name(db.name + "-journal").stat().st_size > 512
    fake = FakeEmbedder()
    resumed = build_index(corpus, db, batch_size=2, embedder_factory=lambda model: fake)
    assert resumed["embedded"] == 3
    assert resumed["added"] == resumed["updated"] == 0
    assert fake.calls == ["passage: " + doc["text"] for doc in docs[2:]]
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT question_id, embedding FROM vectors ORDER BY question_id LIMIT 2").fetchall() == before
    write_corpus(corpus, [document("a", "題文改變後需要重算"), *docs[1:]])
    fake.calls.clear()
    assert build_index(corpus, db, embedder_factory=lambda model: fake)["embedded"] == 1
    assert fake.calls == ["passage: 題文改變後需要重算"]


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
        assert connection.execute("SELECT question_id FROM vectors").fetchall() == [("a",)]
    replacement.calls.clear()
    resumed = build_index(corpus, db, model="new", batch_size=2, embedder_factory=lambda model: replacement)
    assert resumed["embedded"] == 2 and not resumed["model_changed"]


@pytest.mark.parametrize("requested,available,expected", [
    ("auto", True, "cuda"), ("auto", False, "cpu"), ("cpu", True, "cpu"),
    ("cuda", True, "cuda"), ("cuda", False, None),
])
def test_device_selection_without_real_model(monkeypatch, requested, available, expected):
    calls = []
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
