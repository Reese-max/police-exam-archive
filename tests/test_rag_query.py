import json
import sqlite3

import pytest

from scripts.rag.build_index import build_index
from scripts.rag.eval_retrieval import evaluate, middle_query, matching_text
from scripts.rag.eval_retrieval import main as eval_main
from scripts.rag.query import format_results, main
from scripts.rag.retrieval import Retriever, keyword_search, rrf
from test_rag_index import FakeEmbedder, document, write_corpus


@pytest.mark.parametrize("profile_db", ["rag/index.sqlite", r"rag\index.sqlite"])
def test_profile_paths_work_for_query_and_evaluation(tmp_path, monkeypatch, capsys, profile_db):
    monkeypatch.chdir(tmp_path)
    rag = tmp_path / "rag"
    rag.mkdir()
    corpus, db = rag / "corpus.jsonl", rag / "index.sqlite"
    write_corpus(corpus, [document("a", "警察查證身分的法律規定")])
    build_index(corpus, db, embed=False)
    profile = rag / "profile.json"
    profile.write_text(json.dumps({"status": "measured", "device": "cpu", "selected_default": {
        "db": profile_db, "configuration": {"name": "keyword", "mode": "keyword"}}}), encoding="utf-8")
    main(["查證身分", "--profile", str(profile), "--json"])
    assert json.loads(capsys.readouterr().out)[0]["question_id"] == "a"
    eval_main(["--profile", str(profile), "--corpus", str(corpus), "--out", str(rag / "eval.json"),
               "--modes", "keyword", "--n", "1"])
    assert json.loads((rag / "eval.json").read_text(encoding="utf-8"))["n"] == 1


def test_rrf_correct_scores_dedup_and_stable_ties():
    result = rrf([["a", "b", "a", "c"], ["b", "c", "a"]])
    expected = {"a": 1 / 61 + 1 / 63, "b": 1 / 62 + 1 / 61, "c": 1 / 63 + 1 / 62}
    assert [identifier for identifier, _ in result] == ["b", "a", "c"]
    assert dict(result) == pytest.approx(expected)
    assert [identifier for identifier, _ in rrf([["z"], ["a"]])] == ["a", "z"]


def test_short_like_fallback_and_fts_escaping(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "DNA 鑑定警察規則 100%_正確"), document("b", "消防勤務規則")])
    build_index(corpus, db, embed=False)
    with sqlite3.connect(db) as connection:
        assert keyword_search(connection, "鑑定", 5) == [("a", 0.0)]
        assert keyword_search(connection, "%_", 5) == [("a", 0.0)]
        assert keyword_search(connection, "規則", 5) == [("a", 0.0), ("b", 0.0)]
        assert keyword_search(connection, "DNA 鑑定", 5)[0][0] == "a"
        assert keyword_search(connection, "DNA 不存在", 5)[0][0] == "a"  # OR fallback
        assert keyword_search(connection, '" OR * -', 5) == []
        assert keyword_search(connection, "  ", 5) == []


def test_full_phrase_precedes_unrelated_short_word_matches(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "the rapid growth of community colleges"),
                          document("b", "the community has rapid changes and growth")])
    build_index(corpus, db, embed=False)
    retriever = Retriever(db)
    try:
        assert [row["question_id"] for row in retriever.search("the rapid gro", mode="keyword")] == ["a"]
    finally:
        retriever.close()


def test_output_citations_links_and_full_json(tmp_path, capsys):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document(stem="警察查證身分" * 40)
    doc["appears_in"] *= 4
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=False)
    main(["查證身分", "--db", str(db), "--mode", "keyword", "--json"])
    results = json.loads(capsys.readouterr().out)
    assert results[0]["rank"] == 1
    assert len(results[0]["citations"]) == 4
    assert results[0]["sources"] == doc["sources"]
    output = format_results(results)
    assert "行政警察／114年／警察法規／第7題" in output
    assert "https://wwwq.moex.gov.tw/exam/" in output
    assert output.count("試題 PDF：") == 1 and "另有" not in output
    assert len(output.split("題幹：")[1].splitlines()[0]) == 120
    assert "答案：A" in output
    assert "查無" in format_results([])


def test_vector_and_hybrid_with_fake_embedder(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "警察職權行使法查證身分"), document("b", "消防勤務規則")])

    class SemanticEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            self.calls.extend(texts)
            return [[1, 0] if "警察" in text else [0, 1] for text in texts]

    fake = SemanticEmbedder()
    build_index(corpus, db, embedder_factory=lambda model: fake)
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("警察", mode="vector")[0]["question_id"] == "a"
        hybrid = retriever.search("警察職權", mode="hybrid")
        assert hybrid[0]["question_id"] == "a"
        assert hybrid[0]["score"] == pytest.approx(3 / 61)
        assert any(text == "query: 警察" for text in fake.calls)
        assert retriever.search("  ", mode="keyword") == []
        with pytest.raises(ValueError, match="k"):
            retriever.search("警察", k=0)
    finally:
        retriever.close()


def test_missing_vectors_never_silently_downgrade(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embed=False)
    retriever = Retriever(db)
    try:
        assert retriever.search("查證身分", mode="keyword")
        with pytest.raises(ValueError, match="--embed"):
            retriever.search("查證身分", mode="hybrid")
    finally:
        retriever.close()


def test_seeded_evaluation_uses_original_middle_excerpt(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    docs = [document("a", "這是長度超過十五個字的警察職權行使法題目內容"), document("b", "DNA鑑定")]
    write_corpus(corpus, docs)
    fake = FakeEmbedder()
    build_index(corpus, db, embedder_factory=lambda model: fake)
    report = evaluate(corpus, db, n=2, modes=["keyword", "vector", "hybrid"], embedder=fake)
    assert report["n"] == 2 and report["seed"] == 0
    assert report["modes"]["keyword"]["top1"] == report["modes"]["keyword"]["top5"] == 1.0
    assert set(report["modes"]) == {"keyword", "vector", "hybrid"}
    assert middle_query("短題目") == "短題目"
    assert middle_query("0123456789abcdefghijk") == "3456789abcdefgh"
    assert "mean_query_ms" in report["modes"]["hybrid"]
    write_corpus(corpus, [document("changed")])
    with pytest.raises(ValueError, match="雜湊不符"):
        evaluate(corpus, db, modes=["keyword"])


def test_evaluation_groups_use_full_text_containment_and_keep_strict_scores(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    docs = [document("a", "獨特的警察題目"),
            document("b", "共同查詢片段" + "很長的題組背景" * 50, stem="共同查詢片段"),
            document("c", "另一個不同題幹，文章含共同查詢片段", stem="另一個不同題幹")]
    write_corpus(corpus, docs)
    build_index(corpus, db, embed=False)
    report = evaluate(corpus, db, modes=["keyword"])
    assert report["requested_n"] == 500
    assert report["groups"] == {"unique": {"n": 2, "proportion": 2 / 3},
                                "ambiguous": {"n": 1, "proportion": 1 / 3}}
    keyword = report["modes"]["keyword"]
    assert keyword["top1"] == 2 / 3  # Shorter containing document wins BM25, not the source b.
    assert keyword["top5"] == 1
    assert keyword["unique"] == {"top1": 1, "top5": 1}
    assert keyword["ambiguous"] == {"top1": 0, "top5": 1, "relevant_at1": 1, "relevant_at5": 1}
    assert report["acceptance"]["unique_keyword_top1"] is True
    assert report["acceptance"]["ambiguous_keyword_relevant_at1"] is True
    assert report["acceptance"]["unique_hybrid_top1"] is None
    assert report["unresolved_queries"] == []


def test_empty_evaluation_group_is_null_and_punctuation_is_equivalent(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    assert matching_text("(7 分)\n警察,") == matching_text("（7 分） 警察，")
    write_corpus(corpus, [document()])
    build_index(corpus, db, embed=False)
    report = evaluate(corpus, db, modes=["keyword"])
    assert report["groups"]["ambiguous"] == {"n": 0, "proportion": 0}
    assert report["modes"]["keyword"]["ambiguous"]["relevant_at1"] is None
    assert report["acceptance"]["ambiguous_keyword_relevant_at1"] is None


def test_query_device_is_forwarded_to_model_loader(tmp_path, monkeypatch, capsys):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    fake = FakeEmbedder()
    build_index(corpus, db, embedder_factory=lambda model: fake)
    calls = []

    def loader(model, device):
        calls.append((model, device))
        return fake

    monkeypatch.setattr("scripts.rag.retrieval.load_embedder", loader)
    main(["警察", "--db", str(db), "--mode", "vector", "--device", "cuda", "--json"])
    assert json.loads(capsys.readouterr().out)[0]["question_id"] == "a"
    assert calls == [("intfloat/multilingual-e5-small", "cuda")]
