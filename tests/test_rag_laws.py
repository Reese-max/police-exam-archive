import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import pytest

from scripts.rag import fetch_laws
from scripts.rag.build_index import build_index
from scripts.rag.eval_laws import compute_metrics
from scripts.rag.query import format_laws, format_results, main as query_main
from scripts.rag.retrieval import Retriever


class FakeEmbedder:
    rag_identity = "b" * 64

    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.extend(texts)
        return [[1.0, 0.0, 0.0] for _ in texts]


def article(article_no, content, article_type="A"):
    return {"ArticleType": article_type, "ArticleNo": article_no, "ArticleContent": content}


def chlaw(*, abandon="", law_name="測試法"):
    return {
        "UpdateDate": "2026/10/30",
        "Laws": [{
            "LawName": law_name,
            "LawURL": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=A1234567",
            "LawModifiedDate": "20251006",
            "LawAbandonNote": abandon,
            "LawArticles": [
                article("", "  第一章　總則  ", "C"),
                article("第 37 - 1 條", "第一款\r\n第二款"),
                article("第 38 條", "（刪除）"),
                article("第 39 條", "消防勤務規定"),
            ],
        }],
    }


def write_laws(path, records):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
                    encoding="utf-8", newline="\n")


def law_record(identifier="law:A1234567:37-1", content="警察查證身分的現行規定"):
    return {
        "id": identifier,
        "law_name": "測試法",
        "pcode": "A1234567",
        "article_no": "第37-1條",
        "chapter": "第一章 總則",
        "content": content,
        "law_modified_date": "20251006",
        "url": "https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=A1234567&flno=37-1",
    }


def write_corpus(path):
    doc = {"question_id": "question-1", "text": "題目內容", "stem": "題目內容",
           "type": "essay", "appears_in": []}
    path.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")


def test_fetch_normalizes_articles_and_rejects_missing_or_abandoned_laws(tmp_path):
    records, counts = fetch_laws.extract_laws(chlaw(), ["測試法"])
    assert counts == {"測試法": 2}
    assert records[0]["id"] == "law:A1234567:37-1"
    assert records[0]["article_no"] == "第37-1條"
    assert records[0]["chapter"] == "第一章 總則"
    assert records[0]["content"] == "第一款\n第二款"
    assert records[0]["law_modified_date"] == "20251006"
    assert records[0]["url"].endswith("pcode=A1234567&flno=37-1")
    assert records[1]["article_no"] == "第39條"
    with pytest.raises(ValueError, match="找不到法規"):
        fetch_laws.extract_laws(chlaw(), ["不存在法"])
    with pytest.raises(ValueError, match="已廢止法規"):
        fetch_laws.extract_laws(chlaw(abandon="廢"), ["測試法"])
    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("ChLaw.json", json.dumps(chlaw(), ensure_ascii=False))
    assert fetch_laws.read_source(source_zip)["UpdateDate"] == "2026/10/30"
    output, metadata = tmp_path / "laws.jsonl", tmp_path / "laws-meta.json"
    summary = fetch_laws.write_outputs(records, counts, "2026/10/30",
                                       output=output, meta_output=metadata)
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2
    assert json.loads(metadata.read_text(encoding="utf-8"))["total_articles"] == summary["total_articles"] == 2


def test_index_law_hash_skips_unchanged_data_and_rebuilds_changed_data(tmp_path):
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    write_laws(laws_path, [law_record()])
    fake = FakeEmbedder()
    build_index(corpus, db, laws=laws_path, embedder_factory=lambda _: fake)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM law_articles").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM law_vectors").fetchone()[0] == 1
        first_hash = json.loads(connection.execute(
            "SELECT value FROM meta WHERE key='laws_sha256'"
        ).fetchone()[0])
    before = db.read_bytes()
    build_index(corpus, db, laws=laws_path,
                embedder_factory=lambda _: pytest.fail("same law hash should skip encoding"))
    assert db.read_bytes() == before

    write_laws(laws_path, [law_record(content="警察查證身分的新規定")])
    replacement = FakeEmbedder()
    result = build_index(corpus, db, laws=laws_path, embedder_factory=lambda _: replacement)
    assert result["index_changed"] and replacement.calls
    with sqlite3.connect(db) as connection:
        current_hash = json.loads(connection.execute(
            "SELECT value FROM meta WHERE key='laws_sha256'"
        ).fetchone()[0])
        assert current_hash != first_hash
        assert connection.execute("SELECT content FROM law_articles").fetchone()[0] == "警察查證身分的新規定"


def test_no_law_tables_returns_empty_and_keyword_search_returns_full_records(tmp_path):
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    build_index(corpus, db, embed=False)
    retriever = Retriever(db)
    try:
        assert retriever.search_laws("查證身分") == []
    finally:
        retriever.close()

    write_laws(laws_path, [law_record(), law_record(
        identifier="law:A1234567:39", content="消防勤務規定",
    )])
    build_index(corpus, db, embed=False, laws=laws_path)
    retriever = Retriever(db)
    try:
        results = retriever.search_laws("警察查證身分", k=2)
    finally:
        retriever.close()
    assert results and results[0]["id"] == "law:A1234567:37-1"
    assert results[0]["content"] == "警察查證身分的現行規定"
    assert results[0]["score"] > 0


def test_hybrid_law_search_uses_the_configured_fake_embedder(tmp_path):
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    write_laws(laws_path, [
        law_record(),
        law_record(identifier="law:A1234567:39", content="消防勤務規定"),
    ])
    fake = FakeEmbedder()
    build_index(corpus, db, laws=laws_path, embedder_factory=lambda _: fake)
    retriever = Retriever(db, embedder=fake)
    try:
        results = retriever.search_laws("警察查證身分", k=2)
    finally:
        retriever.close()
    assert results[0]["id"] == "law:A1234567:37-1"
    assert "query: 警察查證身分" in fake.calls


def test_law_min_vector_score_hides_weak_matches(tmp_path):
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    write_laws(laws_path, [law_record()])
    fake = FakeEmbedder()  # every vector is [1, 0, 0], so the cosine score is 1.0
    build_index(corpus, db, laws=laws_path, embedder_factory=lambda _: fake)
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search_laws("警察", k=1, min_vector_score=0.99)
        assert retriever.search_laws("警察", k=1, min_vector_score=1.01) == []
    finally:
        retriever.close()


def test_law_search_checks_model_identity_once_not_per_query(tmp_path, monkeypatch):
    from scripts.rag import retrieval
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    write_laws(laws_path, [law_record()])
    fake = FakeEmbedder()
    build_index(corpus, db, laws=laws_path, embedder_factory=lambda _: fake)
    calls = []
    original = retrieval.embedder_identity
    monkeypatch.setattr(retrieval, "embedder_identity",
                        lambda *args: calls.append(1) or original(*args))
    retriever = Retriever(db, embedder=fake)
    try:
        for _ in range(3):
            retriever.search_laws("警察查證身分", k=1)
    finally:
        retriever.close()
    assert len(calls) == 1


def test_query_json_includes_laws_and_law_k_zero_disables_them(tmp_path, capsys):
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    write_laws(laws_path, [law_record()])
    build_index(corpus, db, embed=False, laws=laws_path)
    query_main(["查證身分", "--db", str(db), "--mode", "keyword", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["laws"][0]["article_no"] == "第37-1條"
    query_main(["查證身分", "--db", str(db), "--mode", "keyword", "--law-k", "0", "--json"])
    assert json.loads(capsys.readouterr().out)["laws"] == []


def test_law_output_formats_roc_date_truncates_and_rejects_untrusted_url(tmp_path, monkeypatch):
    item = law_record(content="法條內容" * 80)
    text = format_laws([item])
    assert "測試法 第37-1條（法規最後修正：民國114年10月6日）" in text
    assert "內容已截斷" in text and len(text.split("條文內容：", 1)[1].splitlines()[0]) < 330
    assert "[全國法規資料庫](https://law.moj.gov.tw/" in text
    low_confidence = format_results(
        [{"rank": 1, "question_id": "q", "type": "essay", "stem": "題目",
          "low_confidence": True, "citations": []}],
        laws=[item],
    )
    assert low_confidence.startswith("找不到高度相關的考題") and "相關現行條文" in low_confidence
    item["url"] = "https://law.moj.gov.tw.attacker.example/LawClass/LawSingle.aspx?pcode=x"
    assert "全國法規資料庫" not in format_laws([item])

    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location("rag_law_space_app", root / "space/app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    try:
        item["url"] = "https://law.moj.gov.tw.attacker.example/fake"
        rendered = app.render_laws([item])
        assert "attacker.example" not in rendered and "全國法規資料庫" not in rendered
        item["url"] = law_record()["url"]
        item["content"] = "<script>alert(1)</script>"
        rendered = app.render_laws([item])
        assert "&lt;script&gt;" in rendered and "<script>" not in rendered
        combined = app.render(
            [{"rank": 1, "question_id": "q", "type": "essay", "stem": "題目",
              "low_confidence": True, "citations": []}],
            laws=[item],
        )
        assert combined.startswith("找不到高度相關的考題") and "相關現行條文" in combined
    finally:
        app.executor.shutdown(wait=True)


def test_eval_law_recall_mrr_and_per_law_rates():
    rows = [
        {"query": "查證", "gold": [
            {"law": "警察職權行使法", "article": "第6條"},
            {"law": "刑法", "article": "第1條"},
        ]},
        {"query": "盤查", "gold": [{"law": "警察職權行使法", "article": "第8條"}]},
    ]
    rankings = [
        [{"law_name": "其他法", "article_no": "第1條"},
         {"law_name": "警察職權行使法", "article_no": "第 6 條"}],
        [{"law_name": "警察職權行使法", "article_no": "第8條"}],
    ]
    report = compute_metrics(rows, rankings)
    assert report["R@1"] == 0.5 and report["R@5"] == 1
    assert report["MRR"] == 0.75
    assert report["per_law_hit_rate"]["警察職權行使法"] == {
        "hits": 2, "n": 2, "hit_rate": 1,
    }
    assert report["per_law_hit_rate"]["刑法"]["hit_rate"] == 0
    assert report["misses"] == []


def test_eval_cli_accepts_profile_db_and_writes_report(tmp_path, capsys):
    from scripts.rag.eval_laws import main as eval_main

    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    evaluation, profile, output = (tmp_path / "eval.jsonl", tmp_path / "profile.json",
                                   tmp_path / "report.json")
    write_corpus(corpus)
    write_laws(laws_path, [law_record()])
    build_index(corpus, db, embed=False, laws=laws_path)
    evaluation.write_text(json.dumps({
        "query": "警察查證身分",
        "gold": [{"law": "測試法", "article": "第37-1條"}],
    }) + "\n", encoding="utf-8")
    profile.write_text(json.dumps({
        "status": "measured", "device": "cpu",
        "selected_default": {"db": str(db), "configuration": {"name": "keyword"}},
    }), encoding="utf-8")
    eval_main(["--eval", str(evaluation), "--profile", str(profile), "--out", str(output)])
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["R@1"] == report["R@5"] == 1
    assert json.loads(capsys.readouterr().out)["MRR"] == 1


def test_fetch_keeps_heading_hierarchy():
    data = chlaw()
    data["Laws"][0]["LawArticles"] = [
        article("", "第 一 編 總則", "C"), article("", "第 二 章 人", "C"),
        article("", "第 二 節 法人", "C"), article("", "第 一 款 通則", "C"),
        article("第 25 條", "法人非依本法或其他法律之規定，不得成立。"),
        article("", "第 三 章 物", "C"), article("第 66 條", "稱不動產者，謂土地及其定著物。"),
    ]
    records, _ = fetch_laws.extract_laws(data, ["測試法"])
    assert records[0]["chapter"] == "第一編 總則 第二章 人 第二節 法人 第一款 通則"
    assert records[1]["chapter"] == "第一編 總則 第三章 物"


def test_law_search_reuses_identity_verified_by_question_vectors(tmp_path, monkeypatch):
    from scripts.rag import retrieval
    corpus, laws_path, db = (tmp_path / "corpus.jsonl", tmp_path / "laws.jsonl",
                             tmp_path / "index.sqlite")
    write_corpus(corpus)
    write_laws(laws_path, [law_record()])
    fake = FakeEmbedder()
    build_index(corpus, db, laws=laws_path, embedder_factory=lambda _: fake)
    calls = []
    original = retrieval.embedder_identity
    monkeypatch.setattr(retrieval, "embedder_identity",
                        lambda *args: calls.append(1) or original(*args))
    retriever = Retriever(db, embedder_factory=lambda _: fake)
    try:
        retriever.search("題目內容", k=1)
        retriever.search_laws("警察查證身分", k=1)
    finally:
        retriever.close()
    assert len(calls) == 1
