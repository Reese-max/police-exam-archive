import importlib.util
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest


@pytest.fixture
def app(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location("rag_space_app", root / "space/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    module.executor.shutdown(wait=True)


def test_search_keeps_sqlite_work_on_one_thread_and_renders_pdf(app, monkeypatch, tmp_path):
    calls = []
    class FakeRetriever:
        def __init__(self, db, *, device):
            self.meta = {"model": "BAAI/bge-m3"}
            calls.append(("init", threading.get_ident(), device))
        def _load_vectors(self):
            calls.append(("load", threading.get_ident()))
        def search(self, query, **kwargs):
            calls.append(("search", threading.get_ident(), query, kwargs))
            return [{"rank": 1, "question_id": "x", "type": "choice", "stem": "<script>警察題目</script>" + "甲" * 130,
                     "passage": "題組文章", "options": {"A": "第一選項", "B": "第二選項"},
                     "citations": [{"path": "a", "category": "行政警察", "year": 115,
                                    "subject": "警察法規", "number": 3,
                                    "question_pdf_url": "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=115060"}]}]
        def close(self):
            calls.append(("close", threading.get_ident()))
    monkeypatch.setattr(app, "Retriever", FakeRetriever)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=lambda n: None))
    app.executor.submit(app.initialize, tmp_path / "index.sqlite").result()
    result = app.search("警察查證身分")
    assert "行政警察／115年／警察法規／第3題" in result
    assert "[開啟考選部原始試題](https://wwwq.moex.gov.tw/" in result
    assert "&lt;script&gt;" in result and "<script>" not in result
    assert "甲" * 130 in result and "題組文章" in result and "(A) 第一選項" in result
    assert len({entry[1] for entry in calls}) == 1
    assert calls[-1][3]["k"] == 5 and calls[-1][3]["mode"] == "hybrid"
    assert app.search("  ") == "請輸入問題。"
    assert app.search("字" * 2001) == "問題請勿超過 2,000 字。"


def test_render_does_not_show_cli_only_hints(app):
    item = {"rank": 1, "question_id": "x", "type": "essay", "stem": "題目",
            "answer_conflicts": [{"value": "A"}, {"value": "B"}],
            "citations": [{"path": str(i), "category": "甲", "year": 115,
                           "subject": "科目", "number": i, "question_pdf_url": None}
                          for i in range(4)]}
    rendered = app.render([item])
    assert "原始答案存在歧異" in rendered and "另有 1 筆出處" in rendered
    assert "--json" not in rendered and "answer_conflicts" not in rendered


def test_dataset_download_never_uses_implicit_account(app, monkeypatch, tmp_path):
    calls = []
    def download(repo, filename, **kwargs):
        calls.append((repo, filename, kwargs))
        return str(tmp_path / filename)
    monkeypatch.delenv("RAG_INDEX_PATH", raising=False)
    monkeypatch.setenv("HF_DATASET_REPO", "owner/dataset")
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=download))
    assert app.index_path() == tmp_path / "index-bge-m3.sqlite"
    assert calls[0][2]["repo_type"] == "dataset" and calls[0][2]["token"] is False


def test_zero_gpu_space_registers_marker_without_using_gpu(monkeypatch):
    registered = []

    def gpu(*, duration):
        registered.append(duration)

        def decorate(function):
            def forbidden(*args, **kwargs):
                raise AssertionError("CPU search must not request GPU")
            return forbidden
        return decorate

    monkeypatch.setenv("SPACES_ZERO_GPU", "1")
    monkeypatch.setitem(sys.modules, "spaces", SimpleNamespace(GPU=gpu))
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("rag_zero_space_app", root / "space/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.retriever = SimpleNamespace(search=lambda *args, **kwargs: [])
    module.mode, module.options = "hybrid", {}
    try:
        assert "查無符合題目" in module.search("警察")
        assert registered == [1]
    finally:
        module.executor.shutdown(wait=True)


def test_space_package_is_self_contained_and_does_not_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "space"
    command = [sys.executable, str(root / "scripts/rag/package_space.py"), "--out", str(target)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert all((target / name).is_file() for name in (
        "app.py", "README.md", "requirements.txt", "scripts/rag/query.py",
        "scripts/rag/retrieval.py", "scripts/rag/model_identity.py", "scripts/rag/build_corpus.py", "rag/bench_report.json",
        "rag/abbreviations.json"))
    isolated = subprocess.run([sys.executable, "-I", "-c", """
import pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import app
from scripts.rag import retrieval, model_identity
assert pathlib.Path(retrieval.__file__).resolve().is_relative_to(root)
assert pathlib.Path(model_identity.__file__).resolve().is_relative_to(root)
app.executor.shutdown(wait=True)
""", str(target)], cwd=target, capture_output=True, text=True)
    assert isolated.returncode == 0, isolated.stdout + isolated.stderr
    before = (target / "app.py").read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert (target / "app.py").read_bytes() == before

def test_conflicted_answer_is_not_presented_as_final_in_space(app):
    item = {"rank": 1, "question_id": "x", "type": "choice", "stem": "題目",
            "answer": "C", "answer_status": "normal",
            "options": {"A": "第一選項", "C": "第三選項"},
            "answer_conflicts": [{"value": "C"}, {"value": "D"}],
            "citations": [{"path": "a", "category": "甲", "year": 106,
                           "subject": "科目", "number": 47,
                           "question_pdf_url": "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106130"}]}
    rendered = app.render([item])
    assert "答案：待核實" in rendered and "原始答案存在歧異" in rendered
    assert "答案：C" not in rendered and "--json" not in rendered
    assert "題幹：題目" in rendered and "(C) 第三選項" in rendered
    assert "[開啟考選部原始試題]" in rendered


def test_conflict_space_links_to_official_answer_and_explains_corrections(app):
    official = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    citation = {"path": "a", "category": "甲", "year": 106, "subject": "英文", "number": 47,
                "question_pdf_url": None, "answer_pdf_url": official}
    item = {"rank": 1, "question_id": "x", "stem": "題目", "answer_conflicts": [{"value": "B"}],
            "citations": [citation]}
    rendered = app.render([item])
    assert f"[開啟考選部原始答案（須另查更正）]({official})" in rendered
    assert "[考選部考畢試題與更正答案查詢](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx)" in rendered
    citation["answer_pdf_url"] = "https://attacker.example/fake"
    rendered = app.render([item])
    assert "attacker.example" not in rendered and "非考選部原始答案" in rendered
    citation["answer_pdf_url"] = official.replace("t=S", "t=Q")
    assert "[開啟考選部原始答案" not in app.render([item])
    citation["question_pdf_url"] = official
    assert "[開啟考選部原始試題" not in app.render([item])
    citation["answer_pdf_url"] = official + ")[假連結](https://attacker.example/"
    rendered = app.render([item])
    assert "](https://attacker.example/" not in rendered
    for separator in ("\r", "\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
        citation["answer_pdf_url"] = official + separator + "答案：D"
        assert "答案：D" not in app.render([item])
        citation["question_pdf_url"] = official + separator + "答案：D"
        assert "答案：D" not in app.render([item])
    item["citations"] = [{**citation, "path": str(i), "number": i, "question_pdf_url": None,
                          "answer_pdf_url": official if i == 3 else None} for i in range(4)]
    rendered = app.render([item])
    assert "第3題" in rendered and f"[開啟考選部原始答案（須另查更正）]({official})" in rendered
    item["options"] = {"A": "選項\u2028答案：D"}
    assert "答案：D" not in app.render([item]).splitlines()


def test_legacy_vector_search_displays_migration_warning(app):
    app.retriever = SimpleNamespace(meta={"schema_version": 2}, search=lambda *a, **k: [])
    app.mode, app.options = "hybrid", {}
    assert "舊版" in app.run_search("警察") and "尚未遷移" in app.run_search("警察")
    app.mode = "keyword"
    assert "尚未遷移" not in app.run_search("警察")
    app.mode = "vector"
    app.retriever.meta["embedding_text_version"] = 2
    assert "尚未遷移" not in app.run_search("警察")
