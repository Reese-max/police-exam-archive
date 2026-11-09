import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.rag.bench import configurations, choose_default, measure, percentile, run_benchmark
from scripts.rag.build_index import build_index
from scripts.rag.check_eval_set import check_records, shared_four, read_jsonl
from scripts.rag.query import format_results
from scripts.rag.retrieval import (Retriever, SCHEMA_VERSION, add_search_arguments, chunk_text,
    embedding_texts, expand_query, load_abbreviations, model_prefix, parse_search_args,
    rrf, vector_blob)
from test_rag_index import FakeEmbedder, document, write_corpus


@pytest.fixture
def memory_builder(monkeypatch):
    """Exercise the real builder SQL/transactions entirely inside SQLite :memory:."""
    import importlib
    module = importlib.import_module("scripts.rag.build_index")

    class Connection(sqlite3.Connection):
        def close(self):
            pass  # Keep the in-memory database alive across incremental calls.

    connection = sqlite3.connect(":memory:", factory=Connection)
    # The builder's only filesystem operations here are output-directory setup/stat.
    destination = SimpleNamespace(parent=SimpleNamespace(mkdir=lambda **kwargs: None),
                                  stat=lambda: SimpleNamespace(st_size=0))
    monkeypatch.setattr(module, "Path", lambda value: destination)
    monkeypatch.setattr(module.sqlite3, "connect", lambda path: connection)

    def run(docs, **options):
        records = {doc["question_id"]: (hashlib.sha256(doc["text"].encode()).hexdigest(),
                                      json.dumps(doc, sort_keys=True), doc["text"]) for doc in docs}
        monkeypatch.setattr(module, "read_corpus", lambda path: (records, "fake-corpus-hash"))
        return module.build_index("unused", ":memory:", **options)

    yield run, connection
    sqlite3.Connection.close(connection)


@pytest.fixture
def memory_retriever(monkeypatch):
    """Real FTS and vector aggregation, with no model or filesystem dependency."""
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE questions(question_id TEXT PRIMARY KEY, doc_json TEXT);
        CREATE VIRTUAL TABLE question_fts USING fts5(question_id UNINDEXED,text, tokenize='trigram');
        CREATE TABLE vectors(vector_id TEXT PRIMARY KEY,embedding BLOB);
        CREATE TABLE question_vectors(question_id TEXT,vector_id TEXT);
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    """)
    for doc in (document("a", "精確命中的完整片語"), document("b", "完全不同的背景內容")):
        connection.execute("INSERT INTO questions VALUES (?,?)", (doc["question_id"], json.dumps(doc)))
        connection.execute("INSERT INTO question_fts VALUES (?,?)", (doc["question_id"], doc["text"]))
    for key, vector in [("q:a:000000", [0., 1.]), ("q:b:000000", [1., 0.]), ("shared", [.8, .6])]:
        connection.execute("INSERT INTO vectors VALUES (?,?)", (key, vector_blob(vector)))
    connection.executemany("INSERT INTO question_vectors VALUES (?,?)",
                          [("a", "q:a:000000"), ("a", "shared"), ("b", "q:b:000000"), ("b", "shared")])
    connection.executemany("INSERT INTO meta VALUES (?,?)", [(key, json.dumps(value)) for key, value in
                          {"model": "fake-e5", "dimension": 2, "schema_version": SCHEMA_VERSION}.items()])
    monkeypatch.setattr("scripts.rag.retrieval.open_index", lambda path: connection)

    class Encoder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            self.calls.extend(texts)
            return [[1., 0.] for _ in texts]

    from scripts.rag.retrieval import embedder_identity
    connection.execute("INSERT INTO meta VALUES (?, ?)",
                       ("model_identity", json.dumps(embedder_identity(Encoder(), "fake-e5"))))
    retriever = Retriever("unused", embedder=Encoder())
    yield retriever
    retriever.close()


def test_multivector_max_and_one_result_per_question(memory_retriever):
    result = memory_retriever.search("測試", mode="vector", k=10)
    assert [row["question_id"] for row in result] == ["b", "a"]
    assert [row["score"] for row in result] == pytest.approx([1., .8])
    assert len(memory_retriever.vector_ids) == 3  # Shared vector appears once.


def test_phrase_priority_preserves_keyword_even_against_huge_vector_weight(memory_retriever):
    options = dict(k=1, keyword_weight=1, vector_weight=100)
    assert memory_retriever.search("完整片語", **options)[0]["question_id"] == "a"
    assert memory_retriever.search("完整片語", phrase_priority=False, **options)[0]["question_id"] == "b"


def test_weighted_rrf_and_invalid_parameters():
    assert rrf([["a", "a", "b"], ["b", "a"]], k=0, weights=[3, 1]) == [("a", 3.5), ("b", 2.5)]
    for weights in ([0, 0], [-1, 1], [float("nan"), 1], [1]):
        with pytest.raises(ValueError):
            rrf([["a"], ["b"]], weights=weights)


def test_abbreviation_longest_first_nonrecursive_and_original_retained():
    assert expand_query("刑訴與行執法") == ["刑訴與行執法", "刑事訴訟法與行政執行法"]
    assert expand_query("刑事訴訟法") == ["刑事訴訟法"]
    assert expand_query("abc", {"ab": "c", "abc": "ab"}) == ["abc", "ab"]
    assert len(load_abbreviations()) >= 30


def test_expansion_queries_original_and_full_name(memory_retriever):
    memory_retriever.connection.execute("UPDATE question_fts SET text='警察職權行使法' WHERE question_id='b'")
    assert not memory_retriever.search("警職法", mode="keyword")
    assert memory_retriever.search("警職法", mode="keyword", expand_abbreviations=True)[0]["question_id"] == "b"
    memory_retriever.search("警職法", mode="vector", expand_abbreviations=True)
    assert memory_retriever.embedder.calls[-2:] == ["query: 警職法", "query: 警察職權行使法"]


def test_benchmark_reencodes_repeated_queries(memory_retriever):
    records = [{"query": "測試", "relevant_question_ids": ["b"]}]
    metrics = measure(memory_retriever, records, {"name": "vector", "mode": "vector"}, warmup=1, repeats=2)
    assert metrics["timed_queries"] == 2
    assert memory_retriever.embedder.calls == ["query: 測試"] * 3


def test_embedding_input_and_token_budget():
    class Tokenizer:
        def encode(self, text, add_special_tokens=False):
            return list(map(ord, text)) + ([1, 2] if add_special_tokens else [])

        def decode(self, ids, **kwargs):
            return "".join(map(chr, ids))

        def num_special_tokens_to_add(self, pair):
            return 2

    encoder = SimpleNamespace(tokenizer=Tokenizer(), max_seq_length=32)
    doc = document(stem="題幹" * 100, passage="文章" * 200, options={"A": "正解", "B": "錯誤"})
    texts = embedding_texts(doc)
    assert texts[0].startswith(doc["stem"]) and "正確選項：正解" in texts[0] and "警察法規" in texts[0]
    assert texts[1] == doc["passage"]
    chunks = chunk_text(encoder, texts[0], "passage: ")
    assert "".join(chunks) == texts[0]
    assert all(len(encoder.tokenizer.encode("passage: " + chunk, True)) <= 32 for chunk in chunks)
    assert model_prefix("BAAI/bge-m3") == model_prefix("BAAI/bge-m3", True) == ""


def test_real_builder_incremental_shared_passage_and_invalidation_in_memory(memory_builder):
    run, connection = memory_builder
    fake = FakeEmbedder()
    options = {"embedder_factory": lambda model: fake}
    docs = [document(qid, f"題幹{qid}", passage="共用文章", options={"A": "正解", "B": "另解"}) for qid in "ab"]
    assert run(docs, **options)["embedded"] == 3
    assert connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 3
    fake.calls.clear()
    assert run(docs, **options)["embedded"] == 0 and not fake.calls
    docs[0]["answer"] = "B"
    assert run(docs, **options)["embedded"] == 1
    assert "正確選項：另解" in fake.calls[0]
    docs[0]["appears_in"][0]["subject"] = "不同科目"
    assert run(docs, embed=False)["embedded"] == 0
    assert connection.execute("SELECT DISTINCT question_id FROM question_vectors WHERE vector_id LIKE 'q:%'").fetchall() == [("b",)]
    assert connection.execute("SELECT DISTINCT question_id FROM question_vectors WHERE vector_id LIKE 'p:%' ORDER BY question_id").fetchall() == [("a",), ("b",)]
    fake.calls.clear()
    assert run(docs, **options)["embedded"] == 1 and "不同科目" in fake.calls[0]
    assert run(docs[1:], **options)["removed"] == 1
    assert connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 2
    run([], **options)
    assert connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 0


def test_real_builder_resume_and_schema_migration_in_memory(memory_builder):
    run, connection = memory_builder
    docs = [document(qid, f"測試題幹{qid}") for qid in "abc"]

    class Interrupted(FakeEmbedder):
        def encode(self, texts, **kwargs):
            if self.calls:
                raise RuntimeError("interrupt")
            return super().encode(texts, **kwargs)

    with pytest.raises(RuntimeError, match="interrupt"):
        run(docs, batch_size=1, embedder_factory=lambda model: Interrupted())
    assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NOT NULL").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0] == 2
    assert run(docs, embedder_factory=lambda model: FakeEmbedder())["embedded"] == 2
    with connection:
        connection.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    assert run(docs, embedder_factory=lambda model: FakeEmbedder())["embedded"] == 3
    # Changing to a non-E5 model rebuilds every vector with the new input protocol.
    fake = FakeEmbedder()
    assert run(docs, model="BAAI/bge-m3", embedder_factory=lambda model: fake)["embedded"] == 3
    assert all(not text.startswith("passage: ") for text in fake.calls)


def test_shared_passage_reused_and_answer_subject_invalidate(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    fake = FakeEmbedder()
    docs = [document(qid, f"題幹{qid}", passage="共用的背景文章", options={"A": "正解", "B": "另一解"}) for qid in "ab"]
    write_corpus(corpus, docs)
    assert build_index(corpus, db, embedder_factory=lambda model: fake)["embedded"] == 3
    assert fake.calls.count("passage: 共用的背景文章") == 1
    fake.calls.clear()
    docs[0]["answer"] = "B"
    write_corpus(corpus, docs)
    assert build_index(corpus, db, embedder_factory=lambda model: fake)["embedded"] == 1
    assert "正確選項：另一解" in fake.calls[0]
    fake.calls.clear()
    docs[0]["appears_in"][0]["subject"] = "新科目"
    write_corpus(corpus, docs)
    assert build_index(corpus, db, embedder_factory=lambda model: fake)["embedded"] == 1
    assert "新科目" in fake.calls[0]


def test_schema_migration_and_no_embed_invalidates_old_vectors(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE vectors(question_id TEXT PRIMARY KEY,embedding BLOB)")
        connection.execute("INSERT INTO vectors VALUES ('stale',X'00')")
        connection.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)")
        connection.execute("INSERT INTO meta VALUES ('schema_version','1')")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="模型身分"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before
    new_db = tmp_path / "new-index.sqlite"
    build_index(corpus, new_db, embed=False)
    retriever = Retriever(new_db)
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="--embed"):
            retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    assert build_index(corpus, new_db, embedder_factory=lambda model: FakeEmbedder())["embedded"] == 1


def test_eval_checker_small_fixture_catches_overlap_unknown_and_coverage():
    docs = [document("a", "警察查證身分"), document("b", "行政機關依法辦事", type="essay")]
    rows = [{"query": "員警能問我是誰嗎", "relevant_question_ids": ["a"], "rationale": "身分盤查"},
            {"query": "政府做事的權限來源", "relevant_question_ids": ["b"], "rationale": "依法行政"}]
    opts = dict(min_queries=2, min_subjects=1, abbreviation_range=(0, 1))
    assert check_records(rows, docs, **opts)["errors"] == []
    assert shared_four("問：查證 身分", docs[0]) == "查證身分"
    assert shared_four("ＡＢＣＤ", document(stem="abcd")) == "abcd"
    rows[0].update(query="警察查證怎麼做", relevant_question_ids=["a", "missing"])
    errors = check_records(rows, docs, **opts)["errors"]
    assert any("shared four" in error for error in errors)
    assert any("unknown ID" in error for error in errors)
    assert check_records([], docs)["errors"]


def test_committed_set_count_and_fields_without_database():
    rows = read_jsonl(Path(__file__).parents[1] / "rag/eval_semantic.jsonl")
    assert len(rows) >= 150
    assert len({row["query"] for row in rows}) == len(rows)
    assert all(row["rationale"] and row["relevant_question_ids"] for row in rows)


def test_pdf_dedup_merges_categories_but_keeps_unknown_paths():
    result = document(rank=1, citations=[
        {"path": "x", "category": "甲學系", "question_pdf_url": "https://example.org/q.pdf"},
        {"path": "y", "category": "乙學系", "question_pdf_url": "https://example.org/q.pdf"},
        {"path": "z", "category": "丙學系", "question_pdf_url": None},
        {"path": "w", "category": "丁學系", "question_pdf_url": None}])
    text = format_results([result])
    assert text.count("https://example.org/q.pdf") == 1
    assert "乙學系、甲學系" in text
    assert text.count("未解析") == 2
    assert len(result["citations"]) == 4


def test_benchmark_metrics_and_selection():
    class FakeRetriever:
        def search(self, query, **kwargs):
            return [{"question_id": qid} for qid in ("a", "x", "b")]

    rows = [{"query": "q", "relevant_question_ids": ["a", "b"]}]
    result = measure(FakeRetriever(), rows, {"name": "keyword", "mode": "keyword"})
    assert result["recall@1"] == .5 and result["recall@5"] == result["recall@10"] == result["mrr"] == 1
    assert result["timed_queries"] == 1 and result["warmup_queries"] == 3
    assert percentile([1, 2, 3], .95) == 3
    baseline = {"model": "m", "configuration": {"name": "keyword"}, "metrics": {**result, "recall@5": .4}}
    winner = {"model": "m", "configuration": {"name": "hybrid"}, "metrics": {**result, "p95_ms": 499}}
    too_slow = {**winner, "metrics": {**winner["metrics"], "p95_ms": 501}}
    assert choose_default([baseline, winner, too_slow]) is winner
    assert choose_default([baseline, winner], complete=False) is None
    assert choose_default([baseline, too_slow]) is None
    assert choose_default([baseline, winner], device="cuda") is None
    assert any(c.get("use_reranker") for c in configurations(rerank=True))
    with pytest.raises(ValueError, match="different"):
        run_benchmark([("a", "same.sqlite"), ("b", "same.sqlite")], rows, [], device="cpu")


def test_reranker_only_top_twenty(memory_retriever):
    class FakeReranker:
        def predict(self, pairs):
            assert len(pairs) <= 20
            assert pairs[0][0] == "測試"
            return list(range(len(pairs)))

    results = memory_retriever.search("測試", mode="vector", reranker=FakeReranker())
    assert results[0]["question_id"] == "a" and results[0]["rank"] == 1
    assert "rerank_score" in results[0]


def test_failed_model_load_never_marks_partial_matrix_ready(memory_retriever):
    memory_retriever.embedder = None

    def unavailable(model):
        raise RuntimeError("model unavailable")

    memory_retriever.embedder_factory = unavailable
    with pytest.raises(RuntimeError, match="unavailable"):
        memory_retriever.search("測試", mode="vector")
    assert memory_retriever.vector_ids is None and memory_retriever.matrix is None


def test_benchmark_reports_one_failed_vector_setup_without_retry(memory_retriever, monkeypatch):
    calls = []

    def unavailable():
        calls.append("load")
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(memory_retriever, "_load_vectors", unavailable)
    monkeypatch.setattr(memory_retriever, "close", lambda: None)
    monkeypatch.setattr("scripts.rag.bench.Retriever", lambda *args, **kwargs: memory_retriever)
    configs = configurations(weights=[2], constants=[60])
    report = run_benchmark([("fake-e5", "not-opened.sqlite")],
        [{"query": "完整片語", "relevant_question_ids": ["a"]}], configs)
    assert calls == ["load"] and report["status"] == "incomplete"
    assert report["selected_default"] is None
    assert all(row["metrics"] is None for row in report["results"] if row["configuration"]["mode"] != "keyword")


def test_profile_requires_measured_selection_and_explicit_flags_win(monkeypatch):
    report = {"status": "measured", "device": "cpu", "selected_default": {
        "db": "rag/index-bge-m3.sqlite", "configuration": {"name": "chosen", "mode": "hybrid",
        "keyword_weight": 4, "expand_abbreviations": True}}}
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: json.dumps(report))
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    parser.add_argument("--mode", default="hybrid")
    add_search_arguments(parser)
    args = parse_search_args(parser, ["--profile", "report.json", "--keyword-weight", "3"])
    assert args.keyword_weight == 3 and args.expand_abbreviations and args.db.name == "index-bge-m3.sqlite"
    report["selected_default"] = None
    with pytest.raises(ValueError, match="尚未"):
        parse_search_args(parser, ["--profile", "report.json"])


def test_conflicted_answers_are_not_labeled_correct_for_embedding_or_reranking(memory_retriever):
    from scripts.rag.retrieval import embedding_texts_v1

    conflict = document("a", "精確命中的完整片語", options={"A": "第一個", "B": "第二個"},
                        answer_conflicts=[{"value": "A", "paths": ["甲"]},
                                          {"value": "B", "paths": ["乙"]}])
    normal = document("b", "完全不同的背景內容", options={"A": "第一個", "B": "第二個"})
    assert "正確選項：第一個" in embedding_texts_v1(conflict)[0]
    assert "正確選項" not in embedding_texts(conflict)[0]
    assert all(text in embedding_texts(conflict)[0] for text in ("第一個", "第二個", conflict["stem"]))
    assert embedding_texts(normal) == embedding_texts_v1(normal)
    memory_retriever.connection.execute("UPDATE questions SET doc_json=? WHERE question_id='a'", (json.dumps(conflict),))
    memory_retriever.connection.execute("UPDATE questions SET doc_json=? WHERE question_id='b'", (json.dumps(normal),))

    class CaptureReranker:
        def predict(self, pairs):
            self.pairs = pairs
            return [0] * len(pairs)

    reranker = CaptureReranker()
    results = memory_retriever.search("測試", mode="vector", k=2, reranker=reranker)
    by_id = {row["question_id"]: row for row in results}
    assert by_id["a"]["answer_confidence"] == "disputed"
    assert by_id["a"]["answer"] == "A" and by_id["a"]["answer_conflicts"] == conflict["answer_conflicts"]
    assert by_id["a"]["options"] == conflict["options"] and by_id["a"]["citations"]
    assert by_id["b"]["answer_confidence"] == "unknown"
    assert next(text for _, text in reranker.pairs if conflict["stem"] in text) == embedding_texts(conflict)[0]
