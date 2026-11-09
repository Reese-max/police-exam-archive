import argparse
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.rag.build_index import build_index
from scripts.rag.eval_retrieval import evaluate, middle_query, matching_text
from scripts.rag.eval_retrieval import main as eval_main
from scripts.rag.query import format_results, is_legal_subject, main
from scripts.rag.calibrate_threshold import (
    calibration_rows, read_queries, recommend_threshold,
)
from scripts.rag.retrieval import (
    Retriever, add_search_arguments, keyword_search, parse_search_args, rrf,
)
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
    assert json.loads(capsys.readouterr().out)["results"][0]["question_id"] == "a"
    eval_main(["--profile", str(profile), "--corpus", str(corpus), "--out", str(rag / "eval.json"),
               "--modes", "keyword", "--n", "1"])
    assert json.loads((rag / "eval.json").read_text(encoding="utf-8"))["n"] == 1


def test_profile_min_vector_score_defaults_and_cli_override(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"status": "measured", "device": "cpu", "selected_default": {
        "db": "rag/index.sqlite",
        "configuration": {"name": "hybrid", "mode": "hybrid", "min_vector_score": 0.62},
    }}), encoding="utf-8")
    def make_parser():
        parser = argparse.ArgumentParser()
        parser.add_argument("--db", type=Path)
        parser.add_argument("--mode", default="hybrid")
        add_search_arguments(parser)
        return parser

    parser = make_parser()
    assert parser.parse_args([]).min_vector_score is None
    configured = parse_search_args(parser, ["--profile", str(profile)])
    overridden = parse_search_args(parser, ["--profile", str(profile), "--min-vector-score", "0.4"])

    assert configured.min_vector_score == pytest.approx(0.62)
    assert overridden.min_vector_score == pytest.approx(0.4)
    profile_data = json.loads(profile.read_text(encoding="utf-8"))
    profile_data["selected_default"]["configuration"].pop("min_vector_score")
    profile.write_text(json.dumps(profile_data), encoding="utf-8")
    uncalibrated = parse_search_args(make_parser(), ["--profile", str(profile)])
    assert uncalibrated.min_vector_score is None


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
    results = json.loads(capsys.readouterr().out)["results"]
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
        assert hybrid[0]["top1_vector_score"] == pytest.approx(1)
        assert hybrid[0]["keyword_phrase_hit"] is True
        assert any(text == "query: 警察" for text in fake.calls)
        assert retriever.search("  ", mode="keyword") == []
        with pytest.raises(ValueError, match="k"):
            retriever.search("警察", k=0)
    finally:
        retriever.close()


def test_min_vector_score_is_opt_in_and_exact_phrase_prevents_low_confidence(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "警察法規特殊片語")])

    class OppositeQueryEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            self.calls.extend(texts)
            return [[0, 1] if text.startswith("query:") else [1, 0] for text in texts]

    fake = OppositeQueryEmbedder()
    build_index(corpus, db, embedder_factory=lambda model: fake)
    retriever = Retriever(db, embedder=fake)
    try:
        disabled = retriever.search("完全無關的程式問題", mode="hybrid")
        assert disabled[0]["top1_vector_score"] == pytest.approx(0)
        assert disabled[0]["keyword_phrase_hit"] is False
        assert "low_confidence" not in disabled[0]

        enabled = retriever.search("完全無關的程式問題", mode="hybrid", min_vector_score=0.1)
        assert enabled[0]["low_confidence"] is True
        exact = retriever.search("警察法規特殊片語", mode="hybrid", min_vector_score=0.1,
                                 phrase_priority=False)
        assert exact[0]["top1_vector_score"] == pytest.approx(0)
        assert exact[0]["keyword_phrase_hit"] is True
        assert "low_confidence" not in exact[0]
        with pytest.raises(ValueError, match="min_vector_score"):
            retriever.search("警察", mode="hybrid", min_vector_score=2)
    finally:
        retriever.close()


@pytest.mark.parametrize("subject", ["警察法規", "刑法概要", "憲法與警察專業英文"])
def test_legal_subject_detector(subject):
    assert is_legal_subject(subject)


def test_nonlegal_subject_does_not_trigger_law_reminder():
    assert not is_legal_subject("犯罪心理學")


def test_format_results_displays_roc_year_and_law_reminder_and_low_confidence_first():
    item = document(rank=1, citations=[
        {"path": "law", "category": "行政警察", "year": 114, "subject": "警察法規", "number": 7},
        {"path": "general", "category": "行政警察", "year": 113, "subject": "英文", "number": 8},
    ], low_confidence=True)
    text = format_results([item])
    assert text.startswith("找不到高度相關的考題，以下結果僅供參考")
    assert "年度：民國113年、民國114年" in text
    assert "此為民國114年試題，法規可能已修正，請以現行條文為準" in text
    assert "此為民國113年試題" not in text


def test_threshold_calibration_respects_related_false_alarm_limit(tmp_path):
    semantic = [{"score": 0.8, "keyword_phrase_hit": False}] * 100
    offtopic = ([{"score": 0.2, "keyword_phrase_hit": False}] * 8
                + [{"score": 0.1, "keyword_phrase_hit": True}] * 2)
    rows = calibration_rows(semantic, offtopic)
    recommendation = recommend_threshold(rows)
    assert recommendation["related_false_low_rate"] <= 0.02
    assert recommendation["offtopic_detected_rate"] == pytest.approx(0.8)
    assert recommendation["threshold"] <= 0.8

    path = tmp_path / "eval.jsonl"
    path.write_text('{"query":"無關查詢"}\n', encoding="utf-8")
    assert read_queries(path) == ["無關查詢"]


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
    assert json.loads(capsys.readouterr().out)["results"][0]["question_id"] == "a"
    assert calls == [("intfloat/multilingual-e5-small", "cuda")]

def test_conflicted_answer_text_is_not_definitive_and_json_stays_raw(tmp_path, capsys):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    doc = document("conflict", "警察查證身分題目")
    doc["answer"] = "C"
    doc["answer_conflicts"] = [{"value": "C", "paths": ["甲"]}, {"value": "D", "paths": ["乙"]}]
    write_corpus(corpus, [doc])
    build_index(corpus, db, embed=False)
    main(["查證身分", "--db", str(db), "--mode", "keyword", "--json"])
    results = json.loads(capsys.readouterr().out)["results"]
    assert results[0]["answer"] == "C"
    assert results[0]["answer_conflicts"] == doc["answer_conflicts"]
    assert results[0]["citations"] and results[0]["stem"] == doc["stem"]
    before = json.dumps(results, ensure_ascii=False, sort_keys=True)
    text = format_results(results)
    assert "答案：待核實" in text and "原始答案存在歧異" in text
    assert "答案：C" not in text and "--json" in text
    assert json.dumps(results, ensure_ascii=False, sort_keys=True) == before

    free = {**results[0], "answer": None, "answer_status": "free"}
    assert "答案：待核實" in format_results([free])
    assert "答案：送分" not in format_results([free])
    normal = {**results[0], "answer_conflicts": []}
    assert "答案：C" in format_results([normal])
    no_answer = {**normal, "answer": None, "answer_status": "none"}
    assert "答案：" not in format_results([no_answer])
    free["answer_conflicts"] = []
    assert "答案：送分" in format_results([free])


def test_conflict_text_includes_original_answer_sources_and_correction_lookup():
    question = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106130"
    answer_a = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130&c=112"
    answer_b = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130&c=604"
    citation = {"path": "a", "category": "甲", "year": 106, "subject": "英文", "number": 47,
                "question_pdf_url": question, "answer_pdf_url": answer_a}
    item = {"rank": 1, "question_id": "x", "stem": "題目", "answer_conflicts": [{"value": "B"}],
            "citations": [citation, {**citation, "path": "b", "answer_pdf_url": answer_b}]}
    text = format_results([item])
    assert "原始答案 PDF：" + answer_a in text
    assert "原始答案 PDF：" + answer_b in text
    assert "更正查詢：https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx" in text
    item["citations"] = [{**citation, "answer_pdf_url": None}]
    assert "原始答案 PDF：未解析" in format_results([item])
    item["answer_conflicts"] = []
    assert "原始答案 PDF：" not in format_results([item])
    item["answer_conflicts"] = [{"value": "B"}]
    for separator in ("\r", "\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
        item["citations"][0]["answer_pdf_url"] = answer_a + separator + "答案：D"
        assert "答案：D" not in format_results([item]).splitlines()
        item["citations"][0]["question_pdf_url"] = question + separator + "答案：D"
        assert "答案：D" not in format_results([item]).splitlines()
    item["citations"][0]["answer_pdf_url"] = "https://attacker.example/fake"
    text = format_results([item])
    assert "非考選部原始答案" in text and "attacker.example" not in text
    item["citations"][0]["answer_pdf_url"] = question
    assert "原始答案 PDF：非考選部原始答案" in format_results([item])
    item["citations"][0]["answer_pdf_url"] = answer_a + "&t=Q"
    assert "原始答案 PDF：非考選部原始答案" in format_results([item])
    item["citations"][0]["question_pdf_url"] = answer_a
    assert "試題 PDF：非考選部試題" in format_results([item])


def test_legacy_vector_warning_is_stderr_only_and_keyword_does_not_warn(tmp_path, monkeypatch, capsys):
    import sqlite3
    from scripts.rag import retrieval

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])
    build_index(corpus, db, embedder_factory=lambda _: FakeEmbedder())
    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM meta WHERE key='embedding_text_version'")
    monkeypatch.setattr(retrieval, "load_embedder", lambda *args, **kwargs: FakeEmbedder())
    capsys.readouterr()
    main(["警察", "--db", str(db), "--mode", "vector", "--json"])
    output = capsys.readouterr()
    assert json.loads(output.out)["results"][0]["answer_confidence"] == "unknown"
    assert "舊版" in output.err and "尚未遷移" in output.err
    main(["警察", "--db", str(db), "--json"])
    output = capsys.readouterr()
    assert json.loads(output.out)["results"][0]["answer_confidence"] == "unknown"
    assert "舊版" in output.err and "尚未遷移" in output.err
    main(["警察", "--db", str(db), "--mode", "keyword", "--json"])
    output = capsys.readouterr()
    assert json.loads(output.out) and "尚未遷移" not in output.err
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO meta VALUES ('embedding_text_version', '999')")
    with pytest.raises(SystemExit):
        main(["警察", "--db", str(db), "--mode", "vector", "--json"])
    output = capsys.readouterr()
    assert not output.out and "版本" in output.err


def test_conflict_labels_provisional_source_folder_number_without_changing_normal_output():
    citation = {"path": "source", "category": "甲", "year": 106, "subject": "英文", "number": 42,
                "question_pdf_url": None, "answer_pdf_url": None}
    item = {"rank": 1, "question_id": "q", "stem": "題目", "answer": "A",
            "citations": [citation], "answer_conflicts": [{"value": "A"}, {"value": "B"}]}
    text = format_results([item])
    assert "第42題（來源資料夾題號，請核對官方試卷）" in text
    item["answer_conflicts"] = []
    text = format_results([item])
    assert "甲／106年／英文／第42題" in text and "來源資料夾題號" not in text


@pytest.mark.parametrize("malformed", [{}, [], {"url": "bad"}, ["bad"], 0, 42, False, True])
def test_malformed_source_urls_are_unresolved_without_losing_valid_sources(malformed):
    question = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106130"
    answer = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    citation = {"path": "a", "category": "甲", "year": 106, "subject": "英文", "number": 42,
                "question_pdf_url": malformed, "answer_pdf_url": malformed}
    valid = {**citation, "path": "b", "number": 43, "question_pdf_url": question, "answer_pdf_url": answer}
    item = {"rank": 1, "question_id": "q", "stem": "題目", "answer": "A",
            "answer_conflicts": [{"value": "A"}, {"value": "B"}], "citations": [citation, valid]}
    text = format_results([item])
    assert "試題 PDF：未解析" in text and "原始答案 PDF：未解析" in text
    assert "試題 PDF：" + question in text and "原始答案 PDF：" + answer in text
    item["answer_conflicts"] = []
    text = format_results([item])
    assert "試題 PDF：未解析" in text and "試題 PDF：" + question in text and "答案：A" in text


def test_malformed_and_valid_answer_urls_on_same_paper_are_both_handled():
    question = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106130"
    answer = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    citation = {"path": "a", "category": "甲", "year": 106, "subject": "英文", "number": 42,
                "question_pdf_url": question, "answer_pdf_url": ["bad"]}
    item = {"rank": 1, "question_id": "q", "stem": "題目", "answer_conflicts": [{"value": "A"}],
            "citations": [citation, {**citation, "path": "b", "answer_pdf_url": answer}]}
    text = format_results([item])
    assert "原始答案 PDF：未解析" in text and "原始答案 PDF：" + answer in text
