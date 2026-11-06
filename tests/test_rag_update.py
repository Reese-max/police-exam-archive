import json
import sqlite3
import sys
from contextlib import closing
from types import SimpleNamespace

import pytest

from scripts.rag import update_index
from scripts.rag import dataset_index
from scripts.rag.build_corpus import build_corpus, json_text
from scripts.rag.build_index import build_index
from scripts.rag.build_source_map import build_source_map, write_json
from scripts.rag.update_index import MODEL, update
from test_rag_index import FakeEmbedder


def catalog_entry(year):
    code = f"{year}060"
    return {"year": year, "exam_code": code, "exam_name": f"{year}年警察特種考試",
            "category_code": "501", "category_name": "行政警察", "category_exam": "警察人員考試三等考試",
            "subject_code": "0102", "subject_name": "警察法規",
            "question_pdf_url": f"https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code={code}&c=501&s=0102&q=1",
            "answer_pdf_url": None}


def paper(root, year, stem, subject="警察法規"):
    path = root / f"考古題庫/行政警察/{year}年/{subject}/試題.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"questions": [{"number": 1, "type": "essay", "stem": stem}]}),
                    encoding="utf-8")


def test_incremental_update_fetches_new_year_and_second_run_is_noop(tmp_path, monkeypatch):
    root, db = tmp_path / "repo", tmp_path / "index.sqlite"
    paper(root, 115, "舊年度題目")
    catalog_path = root / "rag/moex_catalog.json"
    write_json(catalog_path, {"schema_version": 1, "pages": [], "entries": [catalog_entry(115)]})
    source, _ = build_source_map(root)
    source_path = tmp_path / "source.json"
    write_json(source_path, source)
    records, _ = build_corpus(root / "考古題庫", source_path)
    corpus = tmp_path / "initial.jsonl"
    corpus.write_text("".join(json_text(record) + "\n" for record in records), encoding="utf-8")
    fake = FakeEmbedder()
    build_index(corpus, db, model=MODEL, embedder_factory=lambda model: fake)

    paper(root, 116, "新年度題目")
    fetched = []
    def fetch(root, *, years):
        fetched.extend(years)
        entries = [catalog_entry(116)]
        if len(fetched) > 1:
            extra = catalog_entry(116)
            extra.update(subject_name="新科目", subject_code="0103",
                         question_pdf_url=extra["question_pdf_url"].replace("s=0102", "s=0103"))
            entries.append(extra)
        return {"schema_version": 1, "pages": [], "entries": entries}, 1
    monkeypatch.setattr(update_index, "fetch_catalog", fetch)
    output_catalog = tmp_path / "new-catalog.json"
    fake.calls.clear()
    result = update(root, db, catalog_out=output_catalog, embedder_factory=lambda model: fake)
    assert fetched == [116] and result["catalog_added_years"] == [116]
    assert result["added"] == result["embedded"] == len(fake.calls) == 1
    assert result["index_changed"] and result["catalog_changed"]
    with closing(sqlite3.connect(db)) as connection:
        docs = [json.loads(row[0]) for row in connection.execute("SELECT doc_json FROM questions")]
    assert any("116060" in doc["sources"][0]["question_pdf_url"] for doc in docs if doc["stem"] == "新年度題目")
    before = db.read_bytes()
    again = update(root, db, catalog=output_catalog, catalog_out=output_catalog,
                   embedder_factory=lambda model: pytest.fail("no-op must not load model"))
    assert (again["added"], again["updated"], again["removed"], again["embedded"]) == (0, 0, 0, 0)
    assert not again["index_changed"] and not again["catalog_changed"]
    assert db.read_bytes() == before and fetched == [116]
    paper(root, 116, "同年度新增考卷", subject="新科目")
    changed = update(root, db, catalog=output_catalog, catalog_out=output_catalog,
                     embedder_factory=lambda model: fake)
    assert fetched == [116, 116] and changed["catalog_refreshed_years"] == [116]
    assert changed["catalog_added_years"] == [] and changed["embedded"] == 1
    with closing(sqlite3.connect(db)) as connection:
        docs = [json.loads(row[0]) for row in connection.execute("SELECT doc_json FROM questions")]
    assert any("s=0103" in doc["sources"][0]["question_pdf_url"]
               for doc in docs if doc["stem"] == "同年度新增考卷")


def test_update_rejects_missing_or_incompatible_seed(tmp_path):
    with pytest.raises(ValueError, match="索引不存在"):
        update(tmp_path, tmp_path / "missing.sqlite")
    bad = tmp_path / "bad.sqlite"
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json_text({"question_id": "a", "text": "題目", "stem": "題目"}) + "\n", encoding="utf-8")
    build_index(corpus, bad, embed=False)
    before = bad.read_bytes()
    with pytest.raises(ValueError, match="不完整或模型/schema"):
        update(tmp_path, bad)
    assert bad.read_bytes() == before


def test_dataset_download_is_anonymous_and_upload_is_guarded(tmp_path, monkeypatch):
    calls = []
    class FakeApi:
        def __init__(self, *, token):
            calls.append(("api", token))
        def repo_info(self, repo, **kwargs):
            calls.append(("info", repo, kwargs))
            return SimpleNamespace(sha="previous-revision")
        def upload_folder(self, **kwargs):
            calls.append(("upload", kwargs))
    def fetch(repo, filename, **kwargs):
        calls.append(("download", repo, filename, kwargs))
        (kwargs["local_dir"] / filename).write_text("fixture", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "huggingface_hub",
                        SimpleNamespace(HfApi=FakeApi, hf_hub_download=fetch))
    dataset_index.download("owner/dataset", tmp_path)
    assert calls[0] == ("api", False) and calls[1][2]["token"] is False
    assert all(call[3]["token"] is False and call[3]["revision"] == "previous-revision"
               for call in calls if call[0] == "download")
    report = tmp_path / "report.json"
    report.write_text('{"index_changed": false, "catalog_changed": false}', encoding="utf-8")
    before = len(calls)
    dataset_index.publish("owner/dataset", tmp_path, report)
    assert len(calls) == before
    report.write_text('{"index_changed": true, "catalog_changed": false}', encoding="utf-8")
    monkeypatch.setenv("HF_DATASET_TOKEN", "test-token")
    with pytest.raises(ValueError, match="dataset 不同"):
        dataset_index.publish("other/dataset", tmp_path, report)
    dataset_index.publish("owner/dataset", tmp_path, report)
    assert calls[-1][1]["parent_commit"] == "previous-revision"
    assert calls[-1][1]["allow_patterns"] == list(dataset_index.FILES)
