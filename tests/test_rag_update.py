import json
import hashlib
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from contextlib import closing, contextmanager
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


def test_dataset_publish_stops_on_revision_conflict(tmp_path, monkeypatch, capsys):
    calls = []
    class ConflictingApi:
        def __init__(self, *, token):
            assert token == "test-token"
        def upload_folder(self, **kwargs):
            calls.append(kwargs["parent_commit"])
            raise RuntimeError("revision conflict")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=ConflictingApi))
    monkeypatch.setenv("HF_DATASET_TOKEN", "test-token")
    receipt = tmp_path / ".base-revision.json"
    receipt.write_text('{"repo": "owner/dataset", "revision": "old-revision"}', encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_text('{"index_changed": true, "catalog_changed": false}', encoding="utf-8")
    before = receipt.read_bytes()
    with pytest.raises(RuntimeError, match="revision conflict"):
        dataset_index.publish("owner/dataset", tmp_path, report)
    assert calls == ["old-revision"] and receipt.read_bytes() == before
    assert "已上傳" not in capsys.readouterr().out


def legacy_update_fixture(tmp_path, monkeypatch, *, disputed, encoder=None):
    from scripts.rag import build_index as builder, retrieval

    root, db = tmp_path / "repo", tmp_path / "seed.sqlite"
    for category, answer in (("行政警察", "A"), ("刑事警察", "B" if disputed else "A")):
        path = root / f"考古題庫/{category}/115年/警察法規/試題.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"questions": [{"number": 1, "type": "choice", "stem": "相同題目",
                        "options": {"A": "選項甲", "B": "選項乙"}, "answer": answer}]}), encoding="utf-8")
    catalog = root / "rag/moex_catalog.json"
    write_json(catalog, {"schema_version": 1, "pages": [], "entries": [catalog_entry(115)]})
    source, _ = build_source_map(root, catalog_path=catalog)
    source_path = tmp_path / "source.json"
    write_json(source_path, source)
    records, _ = build_corpus(root / "考古題庫", source_path)
    corpus = tmp_path / "initial.jsonl"
    corpus.write_bytes("".join(json_text(record) + "\n" for record in records).encode("utf-8"))
    with monkeypatch.context() as patch:
        patch.setattr(builder, "embedding_texts", retrieval.embedding_texts_v1)
        build_index(corpus, db, model=MODEL, embedder_factory=lambda _: encoder or FakeEmbedder())
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("DELETE FROM meta WHERE key='embedding_text_version'")
        old_hash = retrieval.metadata(connection)["corpus_sha256"]
    monkeypatch.setattr(update_index, "fetch_catalog", lambda *a, **k: pytest.fail("unexpected network"))
    return root, db, old_hash


@pytest.mark.parametrize("disputed", [True, False])
def test_update_replaces_legacy_candidate_when_vectors_or_only_metadata_change(tmp_path, monkeypatch, disputed):
    root, db, old_hash = legacy_update_fixture(tmp_path, monkeypatch, disputed=disputed)
    old_bytes = db.read_bytes()
    fake = FakeEmbedder()
    def factory(_):
        if not disputed:
            pytest.fail("metadata-only migration must not load a model")
        return fake
    result = update(root, db, embedder_factory=factory)
    assert result["corpus_sha256"] == old_hash and result["index_changed"]
    assert result["embedded"] == len(fake.calls) == int(disputed)
    if disputed:
        assert "正確選項" not in fake.calls[0] and "選項乙" in fake.calls[0]
    with closing(sqlite3.connect(db)) as connection:
        from scripts.rag.retrieval import metadata
        assert metadata(connection)["embedding_text_version"] == 2
    assert db.read_bytes() != old_bytes
    migrated = db.read_bytes()
    again = update(root, db, embedder_factory=lambda _: pytest.fail("no-op loaded model"))
    assert not again["index_changed"] and again["embedded"] == 0
    assert db.read_bytes() == migrated


@pytest.mark.parametrize("failure", ["encoding", "validation"])
def test_update_failure_before_candidate_replacement_preserves_seed(tmp_path, monkeypatch, failure):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    before = db.read_bytes()
    if failure == "encoding":
        class Broken(FakeEmbedder):
            def encode(self, texts, **kwargs):
                raise RuntimeError("encoding failed")
        factory = lambda _: Broken()
    else:
        original = update_index.seed_info
        def reject_candidate(path):
            if path != db:
                raise ValueError("candidate validation failed")
            return original(path)
        monkeypatch.setattr(update_index, "seed_info", reject_candidate)
        factory = lambda _: FakeEmbedder()
    with pytest.raises((RuntimeError, ValueError), match="failed"):
        update(root, db, embedder_factory=factory)
    assert db.read_bytes() == before


def test_wal_seed_is_not_replaced_or_checkpointed(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    output = tmp_path / "catalog-output.json"
    output.write_bytes(b"unchanged catalog")
    writer = sqlite3.connect(db)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("CREATE TABLE operator_data (value TEXT)")
        writer.execute("INSERT INTO operator_data VALUES ('preserved')")
        writer.commit()
        wal, shm = Path(str(db) + "-wal"), Path(str(db) + "-shm")
        assert wal.exists() and shm.exists()
        before, wal_before = db.read_bytes(), wal.read_bytes()
        with pytest.raises(ValueError, match="WAL|sidecar"):
            update(root, db, catalog_out=output, embedder_factory=lambda _: FakeEmbedder())
        assert db.read_bytes() == before and wal.read_bytes() == wal_before
        assert wal.exists() and shm.exists() and output.read_bytes() == b"unchanged catalog"
        assert writer.execute("SELECT value FROM operator_data").fetchone() == ("preserved",)
        assert writer.execute("SELECT count(*) FROM questions").fetchone() == (1,)
    finally:
        writer.close()


def test_wal_mode_without_existing_sidecars_is_not_replaced(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    assert not Path(str(db) + "-wal").exists() and not Path(str(db) + "-shm").exists()
    before = db.read_bytes()
    with pytest.raises(ValueError, match="WAL"):
        update(root, db, embedder_factory=lambda _: FakeEmbedder())
    assert db.read_bytes() == before


def test_wal_true_noop_does_not_replace_seed(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=False)
    assert update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]
    writer = sqlite3.connect(db)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("CREATE TABLE operator_data (value TEXT)")
        writer.execute("INSERT INTO operator_data VALUES ('preserved')")
        writer.commit()
        wal = Path(str(db) + "-wal")
        before, wal_before = db.read_bytes(), wal.read_bytes()
        result = update(root, db, embedder_factory=lambda _: pytest.fail("no-op loaded model"))
        assert not result["index_changed"]
        assert db.read_bytes() == before and wal.read_bytes() == wal_before
        assert writer.execute("SELECT value FROM operator_data").fetchone() == ("preserved",)
    finally:
        writer.close()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_replacement_guard_preserves_existing_sidecars(tmp_path, monkeypatch, suffix):
    _, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    sidecar = Path(str(db) + suffix)
    sidecar.write_bytes(b"operator-owned sidecar")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="sidecar"):
        with update_index.replacement_guard(db):
            pytest.fail("unsafe seed accepted")
    assert db.read_bytes() == before and sidecar.read_bytes() == b"operator-owned sidecar"


def test_replacement_guard_blocks_real_sqlite_writer_until_replace(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    original = update_index.replacement_guard
    probes = []
    @contextmanager
    def guard(*args, **kwargs):
        with original(*args, **kwargs) as replace:
            def checked_replace(candidate):
                probe()
                return replace(candidate)
            yield checked_replace
    def probe():
        code = r"""
import sqlite3, sys
for statement in ('PRAGMA journal_mode=WAL', 'BEGIN IMMEDIATE'):
    con = sqlite3.connect(sys.argv[1], timeout=0)
    try:
        con.execute(statement).fetchall()
    except sqlite3.OperationalError as exc:
        print('locked' if 'locked' in str(exc).lower() else 'error:' + str(exc))
    else:
        print('unlocked')
    finally:
        con.close()
"""
        result = subprocess.run([sys.executable, "-c", code, str(db)], capture_output=True, text=True, check=True,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        probes.extend(result.stdout.splitlines())
    monkeypatch.setattr(update_index, "replacement_guard", guard)
    assert update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]
    assert probes == ["locked", "locked"]


def test_incremental_update_preserves_existing_law_tables(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=False)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(
            "CREATE TABLE law_articles (id TEXT PRIMARY KEY, law_name TEXT NOT NULL, "
            "pcode TEXT NOT NULL, article_no TEXT NOT NULL, chapter TEXT NOT NULL, "
            "content TEXT NOT NULL, law_modified_date TEXT NOT NULL, url TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE VIRTUAL TABLE law_fts USING fts5(article_id UNINDEXED, text, tokenize='trigram')"
        )
        connection.execute(
            "CREATE TABLE law_vectors (article_id TEXT PRIMARY KEY, embedding BLOB NOT NULL)"
        )
        article = ("law:A1234567:6", "測試法", "A1234567", "第6條", "第一章",
                   "警察查證身分", "20251006",
                   "https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=A1234567&flno=6")
        connection.execute("INSERT INTO law_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)", article)
        connection.execute("INSERT INTO law_fts(article_id, text) VALUES (?, ?)", (article[0], article[5]))
        connection.execute("INSERT INTO law_vectors VALUES (?, ?)", (article[0], b"law-vector"))
        connection.execute("INSERT INTO meta VALUES ('laws_sha256', ?)", (json.dumps("a" * 64),))

    result = update(root, db, embedder_factory=lambda _: pytest.fail("metadata-only update must not encode"))
    assert result["index_changed"]
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT * FROM law_articles").fetchone() == article
        assert connection.execute("SELECT * FROM law_fts").fetchone()[1] == "警察查證身分"
        assert connection.execute("SELECT embedding FROM law_vectors").fetchone()[0] == b"law-vector"
        assert json.loads(connection.execute(
            "SELECT value FROM meta WHERE key='laws_sha256'"
        ).fetchone()[0]) == "a" * 64
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
        assert connection.execute("SELECT count(*) FROM questions").fetchone() == (1,)


@pytest.mark.skipif(os.name != "nt", reason="Windows native rename only")
def test_windows_rename_passes_terminated_utf16_buffer_to_api(tmp_path, monkeypatch):
    import ctypes
    from ctypes import wintypes

    class RenameInfo(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]

    class NativeFunction:
        def __init__(self, function):
            self.function = function
        def __call__(self, *args):
            return self.function(*args)

    captured = []
    def record(handle, info_class, buffer, size):
        captured.append((handle, info_class, ctypes.string_at(buffer, size), ctypes.sizeof(buffer), size))
        return True
    kernel = SimpleNamespace(CreateFileW=NativeFunction(lambda *args: 42),
                             SetFileInformationByHandle=NativeFunction(record),
                             CloseHandle=NativeFunction(lambda *args: True))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    candidate, target = tmp_path / "candidate.sqlite", tmp_path / "檢索-🧪.sqlite"
    candidate.write_bytes(b"candidate")
    target.write_bytes(b"sentinel")
    update_index.replace_candidate(candidate, target)

    assert len(captured) == 1
    handle, info_class, raw, allocated, passed_size = captured[0]
    header = RenameInfo.from_buffer_copy(raw)
    expected = str(target.resolve()).encode("utf-16le")
    offset = RenameInfo.FileName.offset
    assert handle == 42 and info_class == 22 and header.Flags == 3
    assert "🧪".encode("utf-16le") in expected and len(expected) > 2 * len(str(target.resolve()))
    assert header.FileNameLength == len(expected)
    assert allocated == passed_size == len(raw) and passed_size >= offset + len(expected) + 2
    assert raw[offset:offset + len(expected)] == expected
    assert raw[offset + len(expected):offset + len(expected) + 2] == b"\x00\x00"
    assert candidate.read_bytes() == b"candidate" and target.read_bytes() == b"sentinel"


@pytest.mark.skipif(os.name != "nt", reason="Windows native rename only")
def test_windows_rename_uses_exact_utf16_target_and_preserves_sentinels(tmp_path):
    target, candidate = tmp_path / "索引-🌲.sqlite", tmp_path / "candidate.sqlite"
    sentinels = [tmp_path / (target.name + suffix) for suffix in ("a", "守護", "-backup")]
    for index, sentinel in enumerate(sentinels):
        sentinel.write_bytes(f"sentinel-{index}".encode())
    expected_names = {target.name, *(sentinel.name for sentinel in sentinels)}
    for attempt in range(100):
        target.write_bytes(b"old")
        candidate.write_bytes(f"new-{attempt}".encode())
        update_index.replace_candidate(candidate, target)
        assert target.read_bytes() == f"new-{attempt}".encode()
        assert {path.name for path in tmp_path.iterdir()} == expected_names
        assert [path.read_bytes() for path in sentinels] == [f"sentinel-{i}".encode() for i in range(3)]


def test_hardlink_added_after_guard_ready_prevents_replacement(tmp_path):
    db, candidate, alias = (tmp_path / name for name in ("seed.sqlite", "candidate.sqlite", "alias.sqlite"))
    for path, value in ((db, "old"), (candidate, "new")):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE state(value TEXT)")
            connection.execute("INSERT INTO state VALUES (?)", (value,))
    original, proposed = db.read_bytes(), candidate.read_bytes()
    with pytest.raises(ValueError, match="硬連結"):
        with update_index.replacement_guard(db) as replace:
            code = "import os,sys; os.link(sys.argv[1],sys.argv[2])"
            subprocess.run([sys.executable, "-c", code, str(db), str(alias)], check=True, capture_output=True)
            replace(candidate)
    assert db.read_bytes() == alias.read_bytes() == original and candidate.read_bytes() == proposed


def test_hardlink_added_during_rename_reports_uncertain_without_reverting(tmp_path):
    db, candidate, alias = (tmp_path / name for name in ("seed.sqlite", "candidate.sqlite", "alias.sqlite"))
    for path, value in ((db, "old"), (candidate, "new")):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE state(value TEXT)")
            connection.execute("INSERT INTO state VALUES (?)", (value,))
    original, proposed = db.read_bytes(), candidate.read_bytes()
    code = r"""
import subprocess, sys
sys.path.insert(0, sys.argv[1])
import update_index as m
original = m.replace_candidate
def race(candidate, db):
    subprocess.run([sys.executable, '-c', 'import os,sys; os.link(sys.argv[1],sys.argv[2])', db, sys.argv[3]],
                   check=True, capture_output=True)
    original(candidate, db)
m.replace_candidate = race
m._guard_worker(sys.argv[2], '')
"""
    worker = subprocess.Popen([sys.executable, "-c", code, str(Path(update_index.__file__).parent), str(db), str(alias)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8")
    try:
        assert json.loads(worker.stdout.readline()) == {"ready": True}
        output, errors = worker.communicate(json.dumps({"candidate": str(candidate)}) + "\n", timeout=30)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()
    assert worker.returncode != 0, errors
    packet = json.loads(output.splitlines()[0])
    assert "狀態不確定" in packet["error"] and "硬連結" in packet["error"]
    assert db.read_bytes() == proposed and alias.read_bytes() == original and not candidate.exists()


def test_dead_lock_worker_cannot_replace_seed(tmp_path, monkeypatch):
    _, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    candidate = tmp_path / "candidate.sqlite"
    candidate.write_bytes(db.read_bytes())
    before = db.read_bytes()
    original = subprocess.Popen
    workers = []
    def start(*args, **kwargs):
        worker = original(*args, **kwargs)
        workers.append(worker)
        return worker
    monkeypatch.setattr(update_index.subprocess, "Popen", start)
    with pytest.raises((BrokenPipeError, RuntimeError, OSError)):
        with update_index.replacement_guard(db) as replace:
            workers[0].terminate()
            workers[0].wait(timeout=10)
            replace(candidate)
    assert db.read_bytes() == before and candidate.exists()


def test_writer_after_seed_inspection_before_backup_is_preserved(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    output = tmp_path / "catalog-output.json"
    output.write_bytes(b"unchanged catalog")
    original = update_index.build_source_map
    committed = []
    def write_after_inspection(*args, **kwargs):
        result = original(*args, **kwargs)
        code = r"""
import json, sqlite3, sys
doc = json.dumps({'question_id': 'external', 'text': 'outside', 'appears_in': []})
with sqlite3.connect(sys.argv[1]) as con:
    con.execute('INSERT INTO questions VALUES (?, ?, ?)', ('external', 'outside', doc))
    con.execute('INSERT INTO question_fts(question_id, text) VALUES (?, ?)', ('external', 'outside'))
"""
        subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True)
        committed.append(hashlib.sha256(db.read_bytes()).hexdigest())
        return result
    monkeypatch.setattr(update_index, "build_source_map", write_after_inspection)
    with pytest.raises(ValueError, match="來源索引已變更.*安全重試"):
        update(root, db, catalog_out=output, embedder_factory=lambda _: FakeEmbedder())
    assert output.read_bytes() == b"unchanged catalog"
    assert hashlib.sha256(db.read_bytes()).hexdigest() == committed[0]
    code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute(\"SELECT count(*) FROM questions WHERE question_id='external'\").fetchone()[0]); c.close()"
    result = subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "1"


def test_seed_facts_and_baseline_digest_share_a_read_snapshot(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    original = update_index.snapshot_file_digest
    observed = []
    def check(db_path):
        if not observed:
            code = r"""
import sqlite3, sys
con = sqlite3.connect(sys.argv[1], timeout=0)
try:
    con.execute('CREATE TABLE external_change(value TEXT)')
    con.commit()
except sqlite3.OperationalError as exc:
    print('locked' if 'locked' in str(exc).lower() else str(exc))
    con.rollback()
else:
    print('changed')
finally:
    con.close()
"""
            result = subprocess.run([sys.executable, "-c", code, str(db)], check=True,
                                    capture_output=True, text=True)
            observed.append(result.stdout.strip())
        return original(db_path)
    monkeypatch.setattr(update_index, "snapshot_file_digest", check)
    assert update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]
    assert observed == ["locked"]


def test_update_never_reports_success_for_unverified_destination(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    output = tmp_path / "catalog-output.json"
    output.write_bytes(b"unchanged catalog")
    original = update_index.replacement_guard
    replacements = []
    @contextmanager
    def guard(*args, **kwargs):
        with original(*args, **kwargs) as replace:
            def wrong_acknowledgement(candidate):
                replacements.append(replace(candidate))
                return "0" * 64
            yield wrong_acknowledgement
    monkeypatch.setattr(update_index, "replacement_guard", guard)
    with pytest.raises(RuntimeError, match="狀態不確定.*停止更新"):
        update(root, db, catalog_out=output, embedder_factory=lambda _: FakeEmbedder())
    assert len(replacements) == 1 and output.read_bytes() == b"unchanged catalog"
    code = r"""
import hashlib, json, sqlite3, sys
with open(sys.argv[1], 'rb') as stream: digest = hashlib.sha256(stream.read()).hexdigest()
with sqlite3.connect(sys.argv[1]) as con:
    version = json.loads(con.execute("SELECT value FROM meta WHERE key='embedding_text_version'").fetchone()[0])
print(json.dumps([digest, version]))
"""
    result = subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [replacements[0], 2]


def test_worker_does_not_acknowledge_mismatched_destination(monkeypatch, capsys):
    @contextmanager
    def guard(_):
        yield io.BytesIO(b"seed")
    digests = iter([(b"", "a" * 64), (b"", "b" * 64)])
    replacements = []
    monkeypatch.setattr(update_index, "_replacement_guard_local", guard)
    monkeypatch.setattr(update_index, "_check_replacement_target", lambda *args: None)
    monkeypatch.setattr(update_index, "_check_replaced_seed_unlinked", lambda *args: None)
    monkeypatch.setattr(update_index, "snapshot_file_digest", lambda _: next(digests))
    monkeypatch.setattr(update_index, "replace_candidate", lambda candidate, db: replacements.append((candidate, db)))
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"candidate": "candidate"}\n'))
    with pytest.raises(SystemExit):
        update_index._guard_worker("seed", "")
    packets = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert packets[0] == {"ready": True} and "狀態不確定" in packets[1]["error"]
    assert not any(packet.get("replaced") for packet in packets)
    assert replacements == [("candidate", "seed")]


@pytest.mark.parametrize("attempt", range(5))
def test_replacement_acknowledges_actual_destination_in_fresh_process(tmp_path, attempt):
    db, candidate = tmp_path / "seed.sqlite", tmp_path / "candidate.sqlite"
    for path, version in ((db, 1), (candidate, 2)):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE state(value TEXT)")
            connection.execute("INSERT INTO state VALUES (?)", (f"version-{version}",))
            connection.execute(f"PRAGMA user_version={version}")
    code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute(\"INSERT INTO state VALUES ('external')\"); c.commit(); c.close()"
    subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    expected = hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert before != expected
    with update_index.replacement_guard(db, before) as replace:
        replace(candidate)
    code = r"""
import hashlib, json, sqlite3, sys
path = sys.argv[1]
with open(path, 'rb') as stream: digest = hashlib.sha256(stream.read()).hexdigest()
with sqlite3.connect(path) as con:
    version = con.execute('PRAGMA user_version').fetchone()[0]
    rows = con.execute('SELECT value FROM state').fetchall()
print(json.dumps([digest, version, rows]))
"""
    result = subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [expected, 2, [["version-2"]]]
    assert not candidate.exists()


@pytest.mark.parametrize("attempt", range(3))
def test_successful_update_installs_candidate_visible_to_new_process(tmp_path, monkeypatch, attempt):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    original = update_index.replacement_guard
    candidates = []
    @contextmanager
    def guard(*args, **kwargs):
        with original(*args, **kwargs) as replace:
            def audit(candidate):
                candidates.append(hashlib.sha256(candidate.read_bytes()).hexdigest())
                return replace(candidate)
            yield audit
    monkeypatch.setattr(update_index, "replacement_guard", guard)
    assert update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]
    code = r"""
import hashlib, json, sqlite3, sys
with open(sys.argv[1], 'rb') as stream: digest = hashlib.sha256(stream.read()).hexdigest()
with sqlite3.connect(sys.argv[1]) as con:
    version = json.loads(con.execute("SELECT value FROM meta WHERE key='embedding_text_version'").fetchone()[0])
    count = con.execute('SELECT count(*) FROM questions').fetchone()[0]
print(json.dumps([digest, version, count]))
"""
    result = subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True, text=True)
    assert len(candidates) == 1 and json.loads(result.stdout) == [candidates[0], 2, 1]


def test_writer_after_backup_cannot_be_overwritten(tmp_path, monkeypatch):
    from scripts.rag.retrieval import Retriever

    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    output = tmp_path / "catalog-output.json"
    output.write_bytes(b"unchanged catalog")
    original = update_index.build_index
    def build_then_write(corpus, candidate, **kwargs):
        result = original(corpus, candidate, **kwargs)
        code = r"""
import sqlite3, sys
with sqlite3.connect(sys.argv[1], timeout=0) as con:
    con.execute('CREATE TABLE concurrent_data (value TEXT)')
    con.execute("INSERT INTO concurrent_data VALUES ('retained')")
"""
        subprocess.run([sys.executable, "-c", code, str(db)], check=True, capture_output=True)
        return result
    monkeypatch.setattr(update_index, "build_index", build_then_write)
    with pytest.raises(ValueError, match="備份後.*變更.*安全重試"):
        update(root, db, catalog_out=output, embedder_factory=lambda _: FakeEmbedder())
    assert output.read_bytes() == b"unchanged catalog"
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT value FROM concurrent_data").fetchone() == ("retained",)
    reader = Retriever(db, embedder=FakeEmbedder())
    try:
        assert reader.search("題目", mode="vector")
    finally:
        reader.close()


def test_update_reports_reader_lock_and_can_retry(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    before = db.read_bytes()
    output = tmp_path / "catalog-output.json"
    output.write_bytes(b"unchanged catalog")
    ready, release = tmp_path / "reader-ready", tmp_path / "release-reader"
    code = r"""
import sqlite3, sys, time
from pathlib import Path
con = sqlite3.connect(sys.argv[1])
con.execute('BEGIN')
assert con.execute('SELECT count(*) FROM questions').fetchone() == (1,)
Path(sys.argv[2]).write_text('ready')
deadline = time.monotonic() + 30
while not Path(sys.argv[3]).exists():
    if time.monotonic() > deadline: raise RuntimeError('reader timed out')
    time.sleep(.02)
assert con.execute('SELECT count(*) FROM questions').fetchone() == (1,)
con.close()
"""
    reader = subprocess.Popen([sys.executable, "-c", code, str(db), str(ready), str(release)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 25
        while not ready.exists() and reader.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists() and reader.poll() is None
        with pytest.raises(sqlite3.OperationalError, match="安全重試"):
            update(root, db, catalog_out=output, embedder_factory=lambda _: FakeEmbedder())
        assert output.read_bytes() == b"unchanged catalog"
    finally:
        release.write_text("release")
        out, err = reader.communicate(timeout=35)
    assert reader.returncode == 0, out + err
    assert db.read_bytes() == before
    assert update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]


def test_update_does_not_release_same_process_reader_lock(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    before = db.read_bytes()
    reader = sqlite3.connect(db)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM questions").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError, match="安全重試"):
            update(root, db, embedder_factory=lambda _: FakeEmbedder())
        assert reader.execute("SELECT count(*) FROM questions").fetchone() == (1,)
    finally:
        reader.close()
    assert db.read_bytes() == before
    assert update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]


def test_update_rejects_unknown_version_without_replacing_seed(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO meta VALUES ('embedding_text_version', '999')")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="版本"):
        update(root, db, embedder_factory=lambda _: pytest.fail("loaded model"))
    assert db.read_bytes() == before


def test_updated_candidate_persists_new_vector_for_real_retriever(tmp_path, monkeypatch):
    from scripts.rag.retrieval import Retriever

    class InputSensitiveEmbedder(FakeEmbedder):
        def encode(self, texts, **kwargs):
            self.calls.extend(texts)
            return [[1., 0., 0.] if "正確選項：" in text else [0., 1., 0.] for text in texts]

    fake = InputSensitiveEmbedder()
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True, encoder=fake)
    with closing(sqlite3.connect(db)) as connection:
        old_blob = connection.execute("SELECT embedding FROM vectors WHERE vector_id LIKE 'q:%'").fetchone()[0]
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("查詢", mode="vector")[0]["score"] == pytest.approx(0.)
    finally:
        retriever.close()
    result = update(root, db, embedder_factory=lambda _: fake)
    assert result["index_changed"] and result["embedded"] == 1
    with closing(sqlite3.connect(db)) as connection:
        new_blob = connection.execute("SELECT embedding FROM vectors WHERE vector_id LIKE 'q:%'").fetchone()[0]
    assert new_blob != old_blob
    retriever = Retriever(db, embedder=fake)
    try:
        assert retriever.search("查詢", mode="vector")[0]["score"] == pytest.approx(1.)
    finally:
        retriever.close()


@pytest.mark.parametrize("corruption", ["float_schema", "orphan_question", "orphan_vector"])
def test_invalid_schema_or_links_reject_vector_readers_and_seed(tmp_path, monkeypatch, corruption):
    from scripts.rag.retrieval import Retriever, vector_blob
    from scripts.rag.update_index import seed_info

    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=False)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.create_function("rag_model_identity_builder_authorized", 0, lambda: 1)
        question_id = connection.execute("SELECT question_id FROM questions LIMIT 1").fetchone()[0]
        if corruption == "float_schema":
            connection.execute("UPDATE meta SET value='2.0' WHERE key='schema_version'")
        elif corruption == "orphan_question":
            connection.execute("INSERT INTO vectors VALUES ('p:orphan','passage',?)", (vector_blob([1., 0., 0.]),))
            connection.execute("INSERT INTO question_vectors VALUES ('missing-question','p:orphan')")
        else:
            connection.execute("INSERT INTO question_vectors VALUES (?, 'p:missing')", (question_id,))
    before = db.read_bytes()
    retriever = Retriever(db, embedder=FakeEmbedder())
    try:
        assert retriever.search("題目", mode="keyword")
        with pytest.raises(ValueError, match="schema|缺漏或過期"):
            retriever.search("題目", mode="vector")
    finally:
        retriever.close()
    with pytest.raises(ValueError, match="不完整或模型/schema"):
        seed_info(db)
    with pytest.raises(ValueError, match="不完整或模型/schema"):
        update(root, db, embedder_factory=lambda _: pytest.fail("invalid seed loaded model"))
    assert db.read_bytes() == before


def test_candidate_with_orphan_passage_link_is_not_replaced(tmp_path, monkeypatch):
    from scripts.rag.retrieval import vector_blob

    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    before = db.read_bytes()
    original = update_index.build_index
    def corrupt_candidate(corpus, candidate, **kwargs):
        result = original(corpus, candidate, **kwargs)
        with closing(sqlite3.connect(candidate)) as connection, connection:
            connection.create_function("rag_model_identity_builder_authorized", 0, lambda: 1)
            connection.execute("INSERT INTO vectors VALUES ('p:orphan','passage',?)", (vector_blob([1., 0., 0.]),))
            connection.execute("INSERT INTO question_vectors VALUES ('missing-question','p:orphan')")
        return result
    monkeypatch.setattr(update_index, "build_index", corrupt_candidate)
    with pytest.raises(ValueError, match="不完整或模型/schema"):
        update(root, db, embedder_factory=lambda _: FakeEmbedder())
    assert db.read_bytes() == before
