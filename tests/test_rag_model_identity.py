"""Identity compatibility, interrupted writes, and previous-writer boundaries."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from types import SimpleNamespace

import pytest

from scripts.rag.build_index import build_index
from scripts.rag.retrieval import Retriever, metadata
from scripts.rag import update_index
from test_rag_index import FakeEmbedder, document, write_corpus
from test_rag_update import legacy_update_fixture


class Identified(FakeEmbedder):
    def __init__(self, content="original"):
        super().__init__()
        self.rag_identity = hashlib.sha256(content.encode()).hexdigest()


@pytest.fixture
def offline_hub(monkeypatch, tmp_path):
    import socket

    def no_network(*args, **kwargs):
        pytest.fail("revision tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("RAG_MODEL_CACHE", str(tmp_path / "cache"))
    first, second = "a" * 40, "b" * 40
    state = {"main": first, "first": first, "second": second, "downloads": [], "loads": [],
             "contents": {first: "original", second: "changed"}, "local_content": "local"}

    def download(repo, filename, *, revision, cache_dir, token):
        state["downloads"].append((repo, filename, revision))
        assert filename == "modules.json" and revision == "main" and token is False
        path = (Path(cache_dir) / ("models--" + repo.replace("/", "--")) / "snapshots" /
                state["main"] / filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")
        return str(path)

    def load(model, **kwargs):
        state["loads"].append((model, kwargs))
        revision = kwargs.get("revision")
        if "unavailable_revision" in state and state["unavailable_revision"] == revision:
            raise RuntimeError("pinned revision unavailable")
        content = state["local_content"] if revision is None else state["contents"][revision]
        if state.get("interrupt"):
            class Interrupted(Identified):
                def encode(self, texts, **options):
                    if self.calls:
                        raise RuntimeError("interrupted")
                    return super().encode(texts, **options)
            return Interrupted(content)
        return Identified(content)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=load))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    return state


def info(db):
    with closing(sqlite3.connect(db)) as connection:
        return metadata(connection)


_LOCK_PROBE = r"""
import os, sys
with open(sys.argv[1], 'a+b') as stream:
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError:
        print('locked')
    else:
        print('free')
"""


def test_concurrent_builders_hold_lock_across_committed_batches(tmp_path):
    import struct

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    paused, release, checked = (tmp_path / name for name in ("paused", "release", "checked"))
    write_corpus(corpus, [document(key, "題目" + key) for key in "abc"])
    runner = r"""
import os, sys, time
from pathlib import Path
from scripts.rag.build_index import build_index
role, corpus, db, paused, release, checked = sys.argv[1:7]
class Encoder:
    rag_identity = ('a' if role == 'a' else 'b') * 64
    def __init__(self): self.calls = 0
    def encode(self, texts, **kwargs):
        self.calls += 1
        if role == 'a' and self.calls == 2:
            Path(paused).write_text('ready')
            deadline = time.monotonic() + 30
            while not Path(release).exists():
                if time.monotonic() > deadline: raise RuntimeError('release timed out')
                time.sleep(.02)
        return [[1., 0., 0.] if role == 'a' else [0., 1., 0.] for _ in texts]
if role == 'b':
    lock = Path(db).parent / ('.' + Path(db).name + '.rag-write.lock')
    import subprocess
    result = subprocess.run([sys.executable, '-c', sys.argv[7], str(lock)], capture_output=True, text=True, check=True)
    Path(checked).write_text(result.stdout.strip())
build_index(corpus, db, model=role, batch_size=1, embedder_factory=lambda _: Encoder())
"""
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    args = [str(corpus), str(db), str(paused), str(release), str(checked), _LOCK_PROBE]
    first = subprocess.Popen([sys.executable, "-c", runner, "a", *args], cwd=root, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    second = None
    def wait_for(path, process):
        deadline = time.monotonic() + 25
        while not path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert path.exists(), f"process did not reach {path.name}: {process.poll()}"
    try:
        wait_for(paused, first)
        second = subprocess.Popen([sys.executable, "-c", runner, "b", *args], cwd=root, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        wait_for(checked, second)
        assert checked.read_text() == "locked"
    finally:
        release.write_text("go")
    first_out, first_err = first.communicate(timeout=35)
    assert first.returncode == 0, first_out + first_err
    assert second is not None
    second_out, second_err = second.communicate(timeout=35)
    assert second.returncode == 0, second_out + second_err
    with closing(sqlite3.connect(db)) as connection:
        assert metadata(connection)["model"] == "b"
        vectors = [struct.unpack("<3f", row[0]) for row in connection.execute("SELECT embedding FROM vectors")]
        assert len(vectors) == 3 and all(vector == (0., 1., 0.) for vector in vectors)


def test_updater_holds_seed_lock_through_candidate_and_replacement(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    original = update_index.build_index
    started, acquired, corpus = (tmp_path / name for name in ("started", "acquired", "later.jsonl"))
    runner = r"""
import sys
from pathlib import Path
from contextlib import contextmanager
from scripts.rag import build_index as builder
original = builder.index_write_lock
@contextmanager
def traced(db):
    Path(sys.argv[3]).write_text('waiting')
    with original(db):
        Path(sys.argv[4]).write_text('acquired')
        yield
builder.index_write_lock = traced
class Encoder:
    rag_identity = 'a' * 64
    def encode(self, texts, **kwargs): return [[1., 2., 3.] for _ in texts]
builder.build_index(sys.argv[1], sys.argv[2], model='BAAI/bge-m3', embedder_factory=lambda _: Encoder())
"""
    worker = None
    def build_and_pause(candidate_corpus, candidate, **kwargs):
        nonlocal worker
        result = original(candidate_corpus, candidate, **kwargs)
        corpus.write_text(Path(candidate_corpus).read_text(encoding="utf-8") +
                          json.dumps(document("later", "並行新增題目"), ensure_ascii=False) + "\n", encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        worker = subprocess.Popen([sys.executable, "-c", runner, str(corpus), str(db), str(started), str(acquired)],
                                  cwd=Path(__file__).resolve().parents[1], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        deadline = time.monotonic() + 25
        while not started.exists() and worker.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert started.exists() and worker.poll() is None and not acquired.exists()
        lock = db.parent / ("." + db.name + ".rag-write.lock")
        probe = subprocess.run([sys.executable, "-c", _LOCK_PROBE, str(lock)],
                               capture_output=True, text=True, check=True)
        assert probe.stdout.strip() == "locked" and not acquired.exists()
        return result
    monkeypatch.setattr(update_index, "build_index", build_and_pause)
    try:
        assert update_index.update(root, db, embedder_factory=lambda _: FakeEmbedder())["index_changed"]
    finally:
        if worker is not None:
            out, err = worker.communicate(timeout=35)
    assert worker is not None and worker.returncode == 0, out + err
    assert acquired.exists()
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT count(*) FROM questions").fetchone()[0] == 2
        assert connection.execute("SELECT 1 FROM questions WHERE question_id='later'").fetchone()
        assert metadata(connection)["embedding_text_version"] == 2


def test_hardlinked_index_is_never_written_through_either_name(tmp_path):
    corpus, db, alias = (tmp_path / name for name in ("corpus.jsonl", "index.sqlite", "alias.sqlite"))
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
    try:
        os.link(db, alias)
    except OSError as exc:
        pytest.skip(f"hard links are unavailable: {exc}")
    before = db.read_bytes()
    write_corpus(corpus, [document("a"), document("b")])
    for path in (db, alias):
        with pytest.raises(ValueError, match="硬連結"):
            build_index(corpus, path, model="same-model", embedder_factory=lambda _: Identified())
        assert db.read_bytes() == alias.read_bytes() == before




def test_reader_lock_reports_retry_and_preserves_index(tmp_path, monkeypatch):
    from scripts.rag import build_index as builder

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
    before = db.read_bytes()
    reader = sqlite3.connect(db)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM questions").fetchone()[0] == 1
        write_corpus(corpus, [document("a"), document("b")])
        original = sqlite3.connect
        def immediate(*args, **kwargs):
            kwargs["timeout"] = 0
            return original(*args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(builder.sqlite3, "connect", immediate)
            with pytest.raises(sqlite3.OperationalError, match="安全重試"):
                build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
        assert reader.execute("SELECT count(*) FROM questions").fetchone()[0] == 1
    finally:
        reader.close()
    assert db.read_bytes() == before
    retriever = Retriever(db, embedder=Identified())
    try:
        assert retriever.search("警察", mode="vector")
    finally:
        retriever.close()
    assert build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())["embedded"] == 1


def test_hub_commit_is_resolved_once_and_reused_when_main_moves(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    model = "owner/model"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model=model, device="cpu")
    first, second = offline_hub["first"], offline_hub["second"]
    assert info(db)["model_revision"] == first
    assert offline_hub["downloads"] == [(model, "modules.json", "main")]
    assert offline_hub["loads"][-1][1]["revision"] == first
    offline_hub["main"] = second
    before = db.read_bytes()
    assert not build_index(corpus, db, model=model, device="cpu")["index_changed"]
    assert db.read_bytes() == before and len(offline_hub["downloads"]) == 1
    write_corpus(corpus, [document("a"), document("b", "新增內容")])
    assert build_index(corpus, db, model=model, device="cpu")["embedded"] == 1
    assert offline_hub["loads"][-1][1]["revision"] == first
    reader = Retriever(db, device="cpu")
    try:
        assert reader.search("警察", mode="vector")
        assert offline_hub["loads"][-1][1]["revision"] == first
    finally:
        reader.close()
    assert len(offline_hub["downloads"]) == 1
    second_db = tmp_path / "new-index.sqlite"
    build_index(corpus, second_db, model=model, device="cpu")
    assert info(second_db)["model_revision"] == second
    assert offline_hub["loads"][-1][1]["revision"] == second
    # A matching commit is only a locator: changed actual content is rejected.
    before = db.read_bytes()
    offline_hub["contents"][first] = "tampered"
    write_corpus(corpus, [document("a"), document("b", "新增內容"), document("c", "再新增")])
    with pytest.raises(ValueError, match="模型身分"):
        build_index(corpus, db, model=model, device="cpu")
    assert db.read_bytes() == before


def test_interrupted_hub_build_resumes_with_original_commit(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "partial.sqlite"
    model = "owner/model"
    write_corpus(corpus, [document(key, "題目" + key) for key in "abc"])
    offline_hub["interrupt"] = True
    with pytest.raises(RuntimeError, match="interrupted"):
        build_index(corpus, db, model=model, device="cpu", batch_size=1)
    assert info(db)["model_revision"] == offline_hub["first"]
    offline_hub["interrupt"] = False
    offline_hub["main"] = offline_hub["second"]
    assert build_index(corpus, db, model=model, device="cpu")["embedded"] == 2
    assert offline_hub["loads"][-1][1]["revision"] == offline_hub["first"]
    assert len(offline_hub["downloads"]) == 1


def test_unavailable_pinned_commit_never_falls_back_to_changed_main(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    model = "owner/model"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model=model, device="cpu")
    before = db.read_bytes()
    offline_hub["main"] = offline_hub["second"]
    offline_hub["unavailable_revision"] = offline_hub["first"]
    write_corpus(corpus, [document("a"), document("b", "新增")])
    with pytest.raises(RuntimeError, match="pinned revision unavailable"):
        build_index(corpus, db, model=model, device="cpu")
    assert db.read_bytes() == before and len(offline_hub["downloads"]) == 1
    reader = Retriever(db, device="cpu")
    try:
        with pytest.raises(RuntimeError, match="pinned revision unavailable"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()
    assert len(offline_hub["downloads"]) == 1


def test_existing_identity_without_revision_is_never_backfilled(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "existing.sqlite"
    model = "owner/model"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model=model, embedder_factory=lambda _: Identified())
    assert "model_revision" not in info(db)
    write_corpus(corpus, [document("a"), document("b", "新增內容")])
    assert build_index(corpus, db, model=model, device="cpu")["embedded"] == 1
    assert "model_revision" not in info(db)
    reader = Retriever(db, device="cpu")
    try:
        assert reader.search("警察", mode="vector")
    finally:
        reader.close()
    assert "model_revision" not in info(db)
    offline_hub["main"] = offline_hub["second"]
    reader = Retriever(db, device="cpu")
    try:
        assert reader.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="模型身分"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()
    assert "model_revision" not in info(db)


def test_local_snapshot_path_is_never_inferred_as_hub_revision(tmp_path, offline_hub):
    model = tmp_path / "models--owner--model" / "snapshots" / offline_hub["first"]
    model.mkdir(parents=True)
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "local.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model=str(model), device="cpu")
    assert not offline_hub["downloads"] and "model_revision" not in info(db)
    assert "revision" not in offline_hub["loads"][-1][1]
    reader = Retriever(db, device="cpu")
    try:
        assert reader.search("警察", mode="vector")
    finally:
        reader.close()
    assert not offline_hub["downloads"] and "revision" not in offline_hub["loads"][-1][1]


def test_local_builder_accepts_legacy_two_argument_loader(tmp_path, monkeypatch):
    from scripts.rag import build_index as builder

    model = tmp_path / "local-model"
    model.mkdir()
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    calls = []
    def loader(name, device):
        calls.append((name, device))
        return Identified()
    monkeypatch.setattr(builder, "load_embedder", loader)
    assert build_index(corpus, db, model=str(model), device="cpu")["embedded"] == 1
    assert calls == [(str(model), "cpu")] and "model_revision" not in info(db)


def test_explicit_change_to_local_model_drops_old_hub_locator(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="owner/model", device="cpu")
    local = tmp_path / "local-model"
    local.mkdir()
    build_index(corpus, db, model=str(local), device="cpu")
    assert "model_revision" not in info(db)
    assert "revision" not in offline_hub["loads"][-1][1]


def test_unresolvable_or_invalid_revision_fails_before_loading_or_writing(tmp_path, offline_hub, monkeypatch):
    from scripts.rag import retrieval

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    model = "owner/model"
    write_corpus(corpus, [document("a")])
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        hf_hub_download=lambda *a, **k: str(tmp_path / "snapshots" / "main" / "modules.json")))
    with pytest.raises(ValueError, match="revision"):
        build_index(corpus, db, model=model, device="cpu")
    assert not offline_hub["loads"]
    with closing(sqlite3.connect(db)) as connection:
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='vectors'").fetchone()

    # An existing malformed revision cannot be passed to a model or silently ignored.
    build_index(corpus, db, model=model, embedder_factory=lambda _: Identified())
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("INSERT INTO meta VALUES ('model_revision', ?)", (json.dumps("main"),))
    before = db.read_bytes()
    reader = Retriever(db, device="cpu")
    try:
        assert reader.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="revision"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()
    write_corpus(corpus, [document("a"), document("b", "新增")])
    with pytest.raises(ValueError, match="revision"):
        build_index(corpus, db, model=model, device="cpu")
    assert not offline_hub["loads"] and db.read_bytes() == before
    with pytest.raises(ValueError, match="revision"):
        retrieval.load_embedder(str(tmp_path), device="cpu", revision="a" * 40)


def test_pinned_factory_receives_revision_and_cannot_ignore_content_check(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    model = "owner/model"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model=model, device="cpu")
    seen = []
    def factory(name, *, revision):
        seen.append((name, revision))
        return Identified()
    write_corpus(corpus, [document("a"), document("b", "新增")])
    build_index(corpus, db, model=model, embedder_factory=factory)
    reader = Retriever(db, embedder_factory=factory)
    try:
        assert reader.search("警察", mode="vector")
    finally:
        reader.close()
    assert seen == [(model, offline_hub["first"])] * 2
    reader = Retriever(db, embedder_factory=lambda _: Identified())
    try:
        with pytest.raises(ValueError, match="factory.*revision"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()


@pytest.mark.parametrize("changed", ["weights", "tokenizer", "pooling", "encoding"])
def test_changed_identity_rejects_incremental_build_and_vector_query(tmp_path, changed):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    original, different = Identified(), Identified(changed)
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: original)
    original_bytes = db.read_bytes()
    # A no-op does not load or hash the replacement model.
    assert not build_index(corpus, db, model="same-model",
                           embedder_factory=lambda _: pytest.fail("no-op loaded model"))["index_changed"]
    retriever = Retriever(db, embedder=different)
    try:
        assert retriever.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="模型身分"):
            retriever.search("警察", mode="vector")
        assert not different.calls
    finally:
        retriever.close()
    write_corpus(corpus, [document("a"), document("b", "新增內容")])
    with pytest.raises(ValueError, match="模型身分"):
        build_index(corpus, db, model="same-model", embedder_factory=lambda _: different)
    assert db.read_bytes() == original_bytes and not different.calls
    assert build_index(corpus, db, model="same-model", embedder_factory=lambda _: original)["embedded"] == 1


def test_no_embed_preserves_identity_and_mismatched_backfill_preserves_pending(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    original = Identified()
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: original)
    identity = info(db)["model_identity"]
    write_corpus(corpus, [document("a", "已修改內容")])
    build_index(corpus, db, embed=False)
    before = db.read_bytes()
    assert info(db)["model_identity"] == identity
    with pytest.raises(ValueError, match="模型身分"):
        build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified("other"))
    assert db.read_bytes() == before
    assert build_index(corpus, db, model="same-model", embedder_factory=lambda _: original)["embedded"] == 1




@pytest.mark.parametrize("before_first_search", [True, False])
def test_retriever_refreshes_snapshot_when_index_changes(tmp_path, before_first_search):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    old = Identified("old")
    build_index(corpus, db, model="old", embedder_factory=lambda _: old)
    reader = Retriever(db, embedder=old)
    try:
        if not before_first_search:
            assert reader.search("警察", mode="vector")
        write_corpus(corpus, [document("b", "新的警察題目")])
        build_index(corpus, db, model="new", embedder_factory=lambda _: Identified("new"))
        assert reader.search("警察", mode="keyword")[0]["question_id"] == "b"
        with pytest.raises(ValueError, match="模型身分"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()


def test_search_reads_matching_documents_from_one_snapshot(tmp_path, monkeypatch):
    from scripts.rag import retrieval

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "警察題目")])
    build_index(corpus, db, embedder_factory=lambda _: Identified())
    with closing(sqlite3.connect(db)) as setup:
        setup.execute("PRAGMA journal_mode=WAL")
    reader = Retriever(db)
    original = retrieval.keyword_search
    changed = []
    def search_then_commit(connection, query, limit):
        rows = original(connection, query, limit)
        if not changed:
            with closing(sqlite3.connect(db)) as writer, writer:
                doc = json.loads(writer.execute("SELECT doc_json FROM questions WHERE question_id='a'").fetchone()[0])
                doc["stem"] = "更新後內容"
                writer.execute("UPDATE questions SET doc_json=? WHERE question_id='a'", (json.dumps(doc),))
            changed.append(True)
        return rows
    monkeypatch.setattr(retrieval, "keyword_search", search_then_commit)
    try:
        assert reader.search("警察", mode="keyword")[0]["stem"] == "警察題目"
        assert reader.search("警察", mode="keyword")[0]["stem"] == "更新後內容"
    finally:
        reader.close()


def test_retriever_detects_atomic_index_replacement(tmp_path):
    corpus, db, candidate = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite", tmp_path / "candidate.sqlite"
    write_corpus(corpus, [document("a", "警察舊題")])
    old = Identified("old")
    build_index(corpus, db, model="old", embedder_factory=lambda _: old)
    write_corpus(corpus, [document("b", "警察新題")])
    build_index(corpus, candidate, model="new", embedder_factory=lambda _: Identified("new"))
    reader = Retriever(db, embedder=old)
    try:
        assert reader.search("警察", mode="vector")[0]["question_id"] == "a"
        try:
            os.replace(candidate, db)
        except PermissionError:
            pytest.skip("operating system forbids replacing an open SQLite file")
        assert reader.search("警察", mode="keyword")[0]["question_id"] == "b"
        with pytest.raises(ValueError, match="模型身分"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()


def test_retriever_reopens_when_file_generation_changes(tmp_path, monkeypatch):
    from scripts.rag import retrieval

    corpus, db, candidate = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite", tmp_path / "candidate.sqlite"
    write_corpus(corpus, [document("a", "警察舊題")])
    old = Identified("old")
    build_index(corpus, db, model="old", embedder_factory=lambda _: old)
    write_corpus(corpus, [document("b", "警察新題")])
    build_index(corpus, candidate, model="new", embedder_factory=lambda _: Identified("new"))
    reader = Retriever(db, embedder=old)
    try:
        assert reader.search("警察", mode="vector")[0]["question_id"] == "a"
        new_key = (reader._file_key[0], reader._file_key[1] + 1)
        original_open = retrieval.open_index
        monkeypatch.setattr(reader, "_index_file_key", lambda: new_key)
        monkeypatch.setattr(retrieval, "open_index", lambda _: original_open(candidate))
        assert reader.search("警察", mode="keyword")[0]["question_id"] == "b"
        with pytest.raises(ValueError, match="模型身分"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()


def test_interrupted_batches_keep_identity_and_reject_wrong_resume(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document(key, "題目" + key) for key in "abc"])

    class Interrupted(Identified):
        def encode(self, texts, **kwargs):
            if self.calls:
                raise RuntimeError("interrupted")
            return super().encode(texts, **kwargs)

    with pytest.raises(RuntimeError, match="interrupted"):
        build_index(corpus, db, model="same-model", batch_size=1, embedder_factory=lambda _: Interrupted())
    before = db.read_bytes()
    assert info(db)["model_identity"]["version"] == 3
    with pytest.raises(ValueError, match="模型身分"):
        build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified("other"))
    assert db.read_bytes() == before
    assert build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())["embedded"] == 2




def test_model_change_with_empty_corpus_clears_old_identity(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="old", embedder_factory=lambda _: Identified("old"))
    write_corpus(corpus, [])
    build_index(corpus, db, model="new", embedder_factory=lambda _: pytest.fail("empty corpus loaded model"))
    assert info(db)["model"] == "new" and "model_identity" not in info(db)
    write_corpus(corpus, [document("b", "新的題目")])
    assert build_index(corpus, db, model="new", embedder_factory=lambda _: Identified("new"))["embedded"] == 1


def test_model_change_restores_equal_identity_and_revision(tmp_path, offline_hub):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="owner/first", device="cpu")
    before = info(db)
    build_index(corpus, db, model="owner/second", device="cpu")
    after = info(db)
    assert after["model"] == "owner/second"
    assert after["model_identity"] == before["model_identity"]
    assert after["model_revision"] == before["model_revision"] == offline_hub["first"]
    reader = Retriever(db, device="cpu")
    try:
        assert reader.search("警察", mode="vector")
    finally:
        reader.close()


@pytest.mark.parametrize("old_version", [1, 2])
def test_old_fingerprint_version_is_not_reinterpreted(tmp_path, old_version):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
    with closing(sqlite3.connect(db)) as connection, connection:
        old = info(db)["model_identity"]
        old["version"] = old_version
        connection.execute("UPDATE meta SET value=? WHERE key='model_identity'", (json.dumps(old),))
    before = db.read_bytes()
    reader = Retriever(db, embedder=Identified())
    try:
        assert reader.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="模型身分"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()
    assert not build_index(corpus, db, model="same-model", embedder_factory=lambda _: pytest.fail("loaded model"))["index_changed"]
    assert db.read_bytes() == before
    write_corpus(corpus, [document("a"), document("b", "新增題目")])
    with pytest.raises(ValueError, match="模型身分"):
        build_index(corpus, db, model="same-model", embedder_factory=lambda _: pytest.fail("loaded model"))
    assert db.read_bytes() == before and info(db)["model_identity"] == old


@pytest.mark.parametrize("identity", [None, "not-a-sha256", "A" * 64])
def test_injected_encoder_without_explicit_valid_contract_is_rejected(tmp_path, identity):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document()])

    class Unverified:
        rag_identity = identity
        def encode(self, texts, **kwargs):
            pytest.fail("unverified encoder must not run")

    with pytest.raises(ValueError, match="rag_identity"):
        build_index(corpus, db, embedder_factory=lambda _: Unverified())
    with closing(sqlite3.connect(db)) as connection:
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='vectors'").fetchone()


def _run_previous_builder(corpus, db):
    fixture = Path(__file__).parent / "fixtures/rag_pre_model_identity"
    script = """
import sqlite3, sys
sys.path.insert(0, sys.argv[1])
from build_index import build_index
class Fake:
    def encode(self, texts, **kwargs):
        return [[3., 2., 1.] for _ in texts]
try:
    build_index(sys.argv[2], sys.argv[3], model='same-model', embedder_factory=lambda _: Fake())
except sqlite3.Error as exc:
    print('blocked:', exc)
else:
    print('completed')
"""
    result = subprocess.run([sys.executable, "-c", script, str(fixture), str(corpus), str(db)],
                            capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_previous_builder_cannot_write_bound_vectors_and_user_trigger_survives(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
    user_sql = "CREATE TRIGGER user_vector_trigger AFTER INSERT ON vectors BEGIN SELECT 42; END"
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(user_sql)
    before = db.read_bytes()
    write_corpus(corpus, [document("a"), document("b", "新增內容")])
    assert "blocked:" in _run_previous_builder(corpus, db)
    assert db.read_bytes() == before
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT sql FROM sqlite_master WHERE name='user_vector_trigger'").fetchone()[0] == user_sql
        assert connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 1


def test_previous_index_remains_usable_for_keyword_and_noop_but_cannot_be_attested(tmp_path):
    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "legacy.sqlite"
    write_corpus(corpus, [document("a")])
    assert "completed" in _run_previous_builder(corpus, db)
    before = db.read_bytes()
    assert "model_identity" not in info(db)
    assert not build_index(corpus, db, model="same-model",
                           embedder_factory=lambda _: pytest.fail("legacy no-op loaded model"))["index_changed"]
    assert db.read_bytes() == before
    reader = Retriever(db, embedder_factory=lambda _: pytest.fail("legacy vector query loaded model"))
    try:
        assert reader.search("警察", mode="keyword")
        with pytest.raises(ValueError, match="新的 --db"):
            reader.search("警察", mode="vector")
    finally:
        reader.close()
    write_corpus(corpus, [document("a"), document("b", "新增內容")])
    with pytest.raises(ValueError, match="新的 --db"):
        build_index(corpus, db, model="same-model", embedder_factory=lambda _: pytest.fail("loaded model"))
    assert db.read_bytes() == before
    with pytest.raises(ValueError, match="新的 --db"):
        build_index(corpus, db, embed=False)
    assert db.read_bytes() == before
    write_corpus(corpus, [])
    with pytest.raises(ValueError, match="新的 --db"):
        build_index(corpus, db, model="same-model")
    assert db.read_bytes() == before


def test_update_candidate_with_wrong_identity_never_replaces_seed(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    before = db.read_bytes()
    with pytest.raises(ValueError, match="模型身分"):
        update_index.update(root, db, embedder_factory=lambda _: Identified("different"))
    assert db.read_bytes() == before


def test_update_rejects_candidate_that_invents_revision(tmp_path, monkeypatch):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    before = db.read_bytes()
    original = update_index.build_index
    def corrupt_revision(corpus, candidate, **kwargs):
        result = original(corpus, candidate, **kwargs)
        with closing(sqlite3.connect(candidate)) as connection, connection:
            connection.execute("INSERT INTO meta VALUES ('model_revision', ?)", (json.dumps("a" * 40),))
        return result
    monkeypatch.setattr(update_index, "build_index", corrupt_revision)
    with pytest.raises(ValueError, match="模型 revision"):
        update_index.update(root, db, embedder_factory=lambda _: FakeEmbedder())
    assert db.read_bytes() == before


@pytest.mark.parametrize("corruption", ["removed", "changed", "null"])
def test_update_rejects_candidate_with_altered_pinned_revision(tmp_path, monkeypatch, corruption):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=True)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("INSERT INTO meta VALUES ('model_revision', ?)", (json.dumps("a" * 40),))
    before = db.read_bytes()
    original = update_index.build_index
    def corrupt_revision(corpus, candidate, **kwargs):
        result = original(corpus, candidate, **kwargs)
        with closing(sqlite3.connect(candidate)) as connection, connection:
            if corruption == "removed":
                connection.execute("DELETE FROM meta WHERE key='model_revision'")
            else:
                value = "b" * 40 if corruption == "changed" else None
                connection.execute("UPDATE meta SET value=? WHERE key='model_revision'", (json.dumps(value),))
        return result
    monkeypatch.setattr(update_index, "build_index", corrupt_revision)
    def factory(_, *, revision):
        assert revision == "a" * 40
        return FakeEmbedder()
    with pytest.raises(ValueError, match="revision"):
        update_index.update(root, db, embedder_factory=factory)
    assert db.read_bytes() == before


@pytest.mark.parametrize("disputed", [False, True])
def test_update_legacy_unknown_seed_is_preserved_for_noop_or_required_rebuild(tmp_path, monkeypatch, disputed):
    root, db, _ = legacy_update_fixture(tmp_path, monkeypatch, disputed=disputed)
    with closing(sqlite3.connect(db)) as connection, connection:
        for operation in ("insert", "update", "delete"):
            connection.execute(f"DROP TRIGGER rag_model_identity_{operation}_guard")
        connection.execute("DELETE FROM meta WHERE key='model_identity'")
    before = db.read_bytes()
    if disputed:
        with pytest.raises(ValueError, match="模型身分"):
            update_index.update(root, db, embedder_factory=lambda _: pytest.fail("loaded legacy model"))
    else:
        result = update_index.update(root, db, embedder_factory=lambda _: pytest.fail("no-op loaded model"))
        assert not result["index_changed"] and result["embedded"] == 0
    assert db.read_bytes() == before


def test_trusted_schema_off_is_not_disabled(tmp_path, monkeypatch):
    from scripts.rag import build_index as builder

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a")])
    build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
    before = db.read_bytes()
    write_corpus(corpus, [document("a"), document("b", "新增內容")])
    original_connect = sqlite3.connect
    states = []

    class GuardedConnection(sqlite3.Connection):
        def close(self):
            states.append(self.execute("PRAGMA trusted_schema").fetchone()[0])
            super().close()

    def open_guarded(*args, **kwargs):
        connection = original_connect(*args, factory=GuardedConnection, **kwargs)
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection

    monkeypatch.setattr(builder.sqlite3, "connect", open_guarded)
    with pytest.raises(sqlite3.OperationalError, match="unsafe use"):
        build_index(corpus, db, model="same-model", embedder_factory=lambda _: Identified())
    assert states == [0] and db.read_bytes() == before


def test_supported_pipeline_fingerprint_covers_live_state_and_rejects_unknown_modules(monkeypatch):
    """Small in-memory pipeline isolates the fingerprint without model downloads."""
    from scripts.rag.retrieval import embedder_identity

    class Tensor:
        is_sparse = is_quantized = False
        dtype = "float32"
        shape = (1,)
        def __init__(self): self.data = b"abcd"
        def detach(self): return self
        def to(self, _): return self
        def contiguous(self): return self
        def reshape(self, _): return self
        def view(self, _): return self
        def numpy(self): return self.data

    class Tokenizer:
        padding_side = "right"
        truncation_side = "right"
        model_max_length = 32
        clean_up_tokenization_spaces = True
        split_special_tokens = False
        model_input_names = ["input_ids", "attention_mask"]
        special_tokens_map = {"unk_token": "[UNK]"}
        def __init__(self):
            self.vocabulary = {"a": 1}
            self.backend_tokenizer = self
        def to_str(self): return json.dumps({"model": self.vocabulary})

    class Config:
        __module__ = "transformers.test"
        _attn_implementation = "eager"
        def to_dict(self): return {"hidden_size": 1}

    class XLMModel:
        __module__ = "transformers.test"
        def __init__(self):
            self.config = Config()
        def named_modules(self, **kwargs): return [("", self)]

    class BertModel(XLMModel):
        __module__ = "transformers.test"

    class Transformer:
        __module__ = "sentence_transformers.test"
        def __init__(self):
            self.auto_model, self.tokenizer = XLMModel(), Tokenizer()
            self.do_lower_case = False
            self.model_forward_params = {"input_ids", "attention_mask"}
        def get_config_dict(self): return {"do_lower_case": self.do_lower_case}

    class Pooling:
        __module__ = "sentence_transformers.test"
        def __init__(self): self.mode = "cls"
        def get_config_dict(self): return {"mode": self.mode}

    class Normalize:
        __module__ = "sentence_transformers.test"

    class SentenceTransformer:
        __module__ = "sentence_transformers.test"
        max_seq_length, truncate_dim = 32, None
        prompts, default_prompt_name = {}, None
        def __init__(self):
            self.transformer, self.pooling, self.tensor = Transformer(), Pooling(), Tensor()
            self.later, self.buffer, self.reverse = Tensor(), Tensor(), False
            self._modules = {"0": self.transformer, "1": self.pooling, "2": Normalize()}
        def state_dict(self):
            items = [("first", self.tensor), ("later", self.later)]
            return dict(reversed(items) if self.reverse else items)
        def named_parameters(self, **kwargs): return list(self.state_dict().items())
        def named_buffers(self, **kwargs): return [("nonpersistent", self.buffer)]
        def modules(self): return [self, *self._modules.values(), self.transformer.auto_model]

    hooks = SimpleNamespace(_global_forward_hooks={}, _global_forward_pre_hooks={})
    fake_torch = SimpleNamespace(Tensor=Tensor, uint8="uint8", __version__="test",
                                 nn=SimpleNamespace(modules=SimpleNamespace(module=hooks)))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(__version__="test"))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(
        SentenceTransformer=SentenceTransformer, __version__="test",
        models=SimpleNamespace(Transformer=Transformer, Pooling=Pooling, Normalize=Normalize)))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        BertModel=BertModel, XLMRobertaModel=XLMModel, XLMRobertaTokenizer=Tokenizer, __version__="test"))
    encoder = SentenceTransformer()
    initial = embedder_identity(encoder, "same-model")
    fake_torch.__version__ = "2.7.1+cu118"
    gpu_identity = embedder_identity(encoder, "same-model")
    fake_torch.__version__ = "2.7.1+cpu"
    assert embedder_identity(encoder, "same-model") == gpu_identity
    fake_torch.__version__ = "2.7.2+cpu"
    assert embedder_identity(encoder, "same-model") != gpu_identity
    fake_torch.__version__ = "test"
    encoder.reverse = True
    assert embedder_identity(encoder, "same-model") == initial
    encoder.reverse = False
    for mutate, restore in (
        (lambda: setattr(encoder.tensor, "data", b"abce"), lambda: setattr(encoder.tensor, "data", b"abcd")),
        (lambda: setattr(encoder.later, "data", b"abce"), lambda: setattr(encoder.later, "data", b"abcd")),
        (lambda: setattr(encoder.buffer, "data", b"abce"), lambda: setattr(encoder.buffer, "data", b"abcd")),
        (lambda: encoder.transformer.tokenizer.vocabulary.update(a=2),
         lambda: encoder.transformer.tokenizer.vocabulary.update(a=1)),
        (lambda: setattr(encoder.transformer.tokenizer, "model_input_names", ["input_ids"]),
         lambda: setattr(encoder.transformer.tokenizer, "model_input_names", ["input_ids", "attention_mask"])),
        (lambda: setattr(encoder.pooling, "mode", "mean"), lambda: setattr(encoder.pooling, "mode", "cls")),
        (lambda: setattr(encoder.transformer, "do_lower_case", True),
         lambda: setattr(encoder.transformer, "do_lower_case", False)),
        (lambda: encoder.transformer.model_forward_params.remove("attention_mask"),
         lambda: encoder.transformer.model_forward_params.add("attention_mask")),
        (lambda: setattr(encoder.transformer.auto_model.config, "_attn_implementation", "sdpa"),
         lambda: setattr(encoder.transformer.auto_model.config, "_attn_implementation", "eager")),
        (lambda: setattr(encoder, "truncate_dim", 1), lambda: setattr(encoder, "truncate_dim", None)),
    ):
        mutate()
        assert embedder_identity(encoder, "same-model") != initial
        restore()
        assert embedder_identity(encoder, "same-model") == initial
    encoder.transformer.auto_model = BertModel()
    assert embedder_identity(encoder, "same-model") != initial
    encoder.transformer.auto_model = XLMModel()
    encoder._modules["3"] = object()
    with pytest.raises(ValueError, match="不支援"):
        embedder_identity(encoder, "same-model")
    encoder._modules.pop("3")
    for global_hooks in (hooks._global_forward_hooks, hooks._global_forward_pre_hooks):
        global_hooks[1] = object()
        with pytest.raises(ValueError, match="hook"):
            embedder_identity(encoder, "same-model")
        global_hooks.clear()
    encoder.pooling._forward_hooks = {1: object()}
    with pytest.raises(ValueError, match="hook"):
        embedder_identity(encoder, "same-model")
