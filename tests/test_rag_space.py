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
    assert "年度：民國115年" in result
    assert "此為民國115年試題，法規可能已修正，請以現行條文為準" in result
    assert "[開啟考選部原始試題](https://wwwq.moex.gov.tw/" in result
    assert "&lt;script&gt;" in result and "<script>" not in result
    assert "甲" * 130 in result and "題組文章" in result and "(A) 第一選項" in result
    assert len({entry[1] for entry in calls}) == 1
    assert calls[-1][3]["k"] == 5 and calls[-1][3]["mode"] == "hybrid"
    assert app.search("  ") == "請輸入問題。"
    assert app.search("字" * 2001) == "問題請勿超過 2,000 字。"


def test_render_does_not_show_cli_only_hints(app):
    item = {"rank": 1, "question_id": "x", "type": "essay", "stem": "題目",
            "low_confidence": True,
            "answer_conflicts": [{"value": "A"}, {"value": "B"}],
            "citations": [{"path": str(i), "category": "甲", "year": 115,
                           "subject": "科目", "number": i, "question_pdf_url": None}
                          for i in range(4)]}
    rendered = app.render([item])
    assert rendered.startswith("找不到高度相關的考題，以下結果僅供參考")
    assert "原始答案存在歧異" in rendered and "另有 1 筆出處" in rendered
    assert "--json" not in rendered and "answer_conflicts" not in rendered


def test_law_rendering_truncates_content_and_rejects_non_official_links(app):
    law = {
        "law_name": "測試法", "article_no": "第6條", "law_modified_date": "20251006",
        "content": "法條內容" * 80,
        "url": "https://law.moj.gov.tw.attacker.example/fake",
    }
    rendered = app.render_laws([law])
    assert "民國114年10月6日" in rendered and "內容已截斷" in rendered
    assert "attacker.example" not in rendered and "全國法規資料庫" not in rendered


def test_run_search_puts_low_confidence_notice_before_other_output(app):
    result = {"rank": 1, "question_id": "x", "type": "essay", "stem": "題目",
              "low_confidence": True, "citations": []}
    app.retriever = SimpleNamespace(meta={"embedding_text_version": 2},
                                    search=lambda *args, **kwargs: [result])
    app.mode, app.options = "hybrid", {}

    assert app.run_search("完全無關").startswith("找不到高度相關的考題，以下結果僅供參考")


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


def test_frontend_iframe_uses_relative_gradio_file_url(app, tmp_path):
    html = app._frontend_html(tmp_path / "web" / "dist")
    src = html.split('src="', 1)[1].split('"', 1)[0]
    assert not src.startswith(("/", "http"))
    assert src.endswith("/index.html")
    assert "gradio_api/file=" in src


@pytest.mark.parametrize("has_build", [True, False])
def test_package_space_copies_frontend_build_only_when_present(
        monkeypatch, tmp_path, has_build):
    from scripts.rag import package_space

    root = tmp_path / "repo"
    dist = root / "space" / "web" / "dist"
    if has_build:
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<html>測試</html>", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    monkeypatch.setattr(package_space, "ROOT", root)

    assert package_space._copy_frontend(output) is has_build
    if has_build:
        assert (output / "web" / "dist" / "index.html").read_text(
            encoding="utf-8") == "<html>測試</html>"
    else:
        assert not (output / "web").exists()


def test_space_package_is_self_contained_and_does_not_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "space"
    command = [sys.executable, str(root / "scripts/rag/package_space.py"), "--out", str(target)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert all((target / name).is_file() for name in (
        "app.py", "README.md", "requirements.txt", "scripts/rag/query.py", "scripts/rag/answer.py",
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


def _chat_evidence(stem="查證身分題", *, low_confidence=False):
    question = {
        "rank": 1, "question_id": "q1", "type": "choice", "stem": stem,
        "options": {"A": "依法查證"}, "answer": "A", "answer_status": "normal",
        "answer_source": "moex_official",
        "citations": [{"path": "a", "category": "行政警察", "year": 115,
                       "subject": "警察法規", "number": 1}],
    }
    if low_confidence:
        question["low_confidence"] = True
    law = {
        "law_name": "警察職權行使法", "article_no": "第6條",
        "law_modified_date": "20251006", "content": "警察得依法查證身分。",
        "url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=D0080145",
    }
    return [question], [law]


def _set_chat_search(app, monkeypatch, results=None, laws=None):
    questions, statutes = _chat_evidence()
    results = questions if results is None else results
    laws = statutes if laws is None else laws
    searched = []

    def search(query):
        searched.append((query, threading.get_ident()))
        return results, laws, 12.0, ""

    monkeypatch.setattr(app, "_search_data", search)
    app._answer_cache.clear()
    app._answer_requests.clear()
    return searched


def _run_chat(app, message, history=None):
    updates = list(app.chat(message, history or []))
    return updates, updates[-1][0]


def test_chat_renders_grounded_supplement_and_collapsible_numbered_sources(
        app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    questions, laws = _chat_evidence()
    _set_chat_search(app, monkeypatch, questions, laws)
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "ok", "grounded": "依考題與法條。[題1][條1]",
        "supplement": "額外說明。", "citations": ["[題1]", "[條1]"],
        "invalid_citations": [],
    })

    updates, messages = _run_chat(app, "警察何時可以查證身分？")

    assert len(updates) == 2
    assert "正在整理回答" in updates[0][0][-1]["content"]
    assert updates[-1][1] == ""
    assert "依考題與法條。[題1][條1]" in messages[-2]["content"]
    assert "⚠️ 以下不是出自題庫或法條，是 AI 依自身知識回答，未經查證；條號、數字請自行核對。" \
        in messages[-2]["content"]
    source = messages[-1]
    assert source["metadata"]["title"] == "檢索到的考題與條文（1 題、1 條）"
    assert "[題1]" in source["content"] and "[條1]" in source["content"]


def test_chat_escapes_model_html_and_removes_markdown_links(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    _set_chat_search(app, monkeypatch)
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "ok", "grounded": "<script>alert(1)</script> [危險連結](https://bad.example)",
        "supplement": "", "citations": [], "invalid_citations": [],
    })

    _, messages = _run_chat(app, "問題")
    rendered = messages[-2]["content"]

    assert "&lt;script&gt;" in rendered and "<script>" not in rendered
    assert "bad.example" not in rendered
    assert "危險連結" in rendered


def test_follow_up_retrieval_retries_with_previous_question_and_uses_good_retry(
        app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    low, _ = _chat_evidence("低信心題", low_confidence=True)
    improved, laws = _chat_evidence("合併查詢找到的題目")
    calls = []

    def search(query):
        calls.append(query)
        if len(calls) == 1:
            return low, [], 1, ""
        return improved, laws, 2, ""

    monkeypatch.setattr(app, "_search_data", search)
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "ok", "grounded": "依據回答。[題1]", "supplement": "",
        "citations": ["[題1]"], "invalid_citations": [],
    })
    history = [{"role": "user", "content": "警察查證身分"},
               {"role": "assistant", "content": "上一輪回覆"},
               {"role": "assistant", "content": "舊來源", "metadata": {"title": "檢索來源"}}]

    _, messages = _run_chat(app, "何種情況？", history)

    assert calls == ["何種情況？", "警察查證身分 何種情況？"]
    assert "合併查詢找到的題目" in messages[-1]["content"]


def test_follow_up_retrieval_keeps_first_results_when_retry_remains_low_confidence(
        app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    first, _ = _chat_evidence("第一次結果", low_confidence=True)
    retry, _ = _chat_evidence("仍低信心的重查結果", low_confidence=True)
    calls = []

    def search(query):
        calls.append(query)
        return (first if len(calls) == 1 else retry), [], 1, ""

    monkeypatch.setattr(app, "_search_data", search)
    generated = []

    def generate(*args, **kwargs):
        generated.append(args)
        return {"status": "ok", "grounded": "", "supplement": "補充答覆。",
                "citations": [], "invalid_citations": []}

    monkeypatch.setattr(app, "generate_chat_answer", generate)

    _, messages = _run_chat(app, "追問", [{"role": "user", "content": "前一題"}])

    assert calls == ["追問", "前一題 追問"]
    assert not any(item.get("metadata", {}).get("title") for item in messages)
    assert generated[0][1][0]["stem"] == "第一次結果"


def test_follow_up_with_reliable_first_results_does_not_retry(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    searched = _set_chat_search(app, monkeypatch)
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "ok", "grounded": "回答。[題1]", "supplement": "",
        "citations": ["[題1]"], "invalid_citations": [],
    })

    _run_chat(app, "追問", [{"role": "user", "content": "前一題"}])

    assert [query for query, _ in searched] == ["追問"]


def test_history_answers_bypass_cache_but_first_question_cache_avoids_repeat_call(
        app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "10")
    _set_chat_search(app, monkeypatch)
    calls = []

    def generate(query, results, laws, *, history=()):
        calls.append((query, history))
        return {"status": "ok", "grounded": "依據回答。[題1]", "supplement": "",
                "citations": ["[題1]"], "invalid_citations": []}

    monkeypatch.setattr(app, "generate_chat_answer", generate)
    history = [{"role": "user", "content": "前一題"},
               {"role": "assistant", "content": "前文"},
               {"role": "assistant", "content": "來源", "metadata": {"title": "來源"}}]

    _run_chat(app, "同一追問", history)
    _run_chat(app, "同一追問", history)
    assert len(calls) == 2
    assert not app._answer_cache
    assert all("來源" not in str(history_arg) for _, history_arg in calls)
    assert len(app._answer_requests) == 2

    app._answer_requests.clear()
    app._answer_cache.clear()
    _run_chat(app, "第一則問題")
    _run_chat(app, "第一則問題")
    assert len(calls) == 3
    assert len(app._answer_requests) == 1
    assert list(app._answer_cache) == ["第一則問題".casefold()]


def test_chat_limit_falls_back_to_search_results(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "1")
    _set_chat_search(app, monkeypatch)
    app._answer_requests.append((app.time.monotonic(), object()))
    model_calls = []
    monkeypatch.setattr(app, "generate_chat_answer",
                        lambda *args, **kwargs: model_calls.append(1))

    _, messages = _run_chat(app, "問題")

    assert "AI 回答已達本小時上限，以下是檢索結果：" in messages[-1]["content"]
    assert "題幹：查證身分題" in messages[-1]["content"]
    assert not model_calls
    assert len(app._answer_requests) == 1


def test_chat_model_error_refunds_quota_and_falls_back_to_search_results(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "1")
    _set_chat_search(app, monkeypatch)
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "error", "reason": "模型服務連線逾時或失敗",
    })

    _, messages = _run_chat(app, "問題")

    assert "AI 回答暫時無法產生（模型服務連線逾時或失敗）" in messages[-1]["content"]
    assert "題幹：查證身分題" in messages[-1]["content"]
    assert not app._answer_requests


def test_chat_without_api_key_returns_retrieval_only_without_model_call(app, monkeypatch):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    _set_chat_search(app, monkeypatch)

    _, messages = _run_chat(app, "問題")

    assert "未設定 AI 金鑰，以下是檢索結果：" in messages[-1]["content"]
    assert "題幹：查證身分題" in messages[-1]["content"]
    assert not app._answer_requests


def test_chat_no_data_still_calls_model_and_omits_source_accordion(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "10")
    questions, _ = _chat_evidence("低信心題", low_confidence=True)
    _set_chat_search(app, monkeypatch, questions, [])
    model_calls = []

    def generate(*args, **kwargs):
        model_calls.append((args, kwargs))
        return {"status": "ok", "grounded": "", "supplement": "依自身知識補充。",
                "citations": [], "invalid_citations": []}

    monkeypatch.setattr(app, "generate_chat_answer", generate)

    _, messages = _run_chat(app, "沒有檢索資料")

    assert len(model_calls) == 1 and len(app._answer_requests) == 1
    assert "⚠️ 以下不是出自題庫或法條" in messages[-1]["content"]
    assert not any(item.get("metadata", {}).get("title") for item in messages)


def test_chat_search_runs_in_single_executor_and_invalid_messages_skip_work(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    searched = _set_chat_search(app, monkeypatch)
    model_calls = []
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "ok", "grounded": "回答。[題1]", "supplement": "",
        "citations": ["[題1]"], "invalid_citations": [],
    })
    main_thread = threading.get_ident()

    _, _ = _run_chat(app, "問題")
    assert len(searched) == 1 and searched[0][1] != main_thread
    assert searched[0][1] == app.executor.submit(threading.get_ident).result()

    monkeypatch.setattr(app, "generate_chat_answer",
                        lambda *args, **kwargs: model_calls.append(1))
    searched.clear()
    _, blank = _run_chat(app, " \n ")
    _, long = _run_chat(app, "字" * 2001)
    assert blank[-1]["content"] == "請輸入問題。"
    assert long[-1]["content"] == "問題請勿超過 2,000 字。"
    assert not searched and not model_calls


def test_chat_has_no_hourly_limit_unless_configured(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    monkeypatch.delenv("RAG_LLM_MAX_PER_HOUR", raising=False)
    _set_chat_search(app, monkeypatch)
    calls = []
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: calls.append(1) or {
        "status": "ok", "grounded": "答。[題1]", "supplement": "",
        "citations": ["[題1]"], "invalid_citations": [],
    })

    for index in range(31):
        _, messages = _run_chat(app, f"問題{index}")

    assert len(calls) == 31
    assert all("上限" not in item["content"] for item in messages)


def test_configured_limit_applies_when_only_fallback_key_is_set(app, monkeypatch):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    monkeypatch.setenv("RAG_LLM_FALLBACK_API_KEY", "backup-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "1")
    _set_chat_search(app, monkeypatch)
    app._answer_requests.append((app.time.monotonic(), object()))
    calls = []
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: calls.append(1) or {
        "status": "ok", "grounded": "答。[題1]", "supplement": "",
        "citations": ["[題1]"], "invalid_citations": [],
    })

    _, messages = _run_chat(app, "問題")

    assert not calls
    assert "AI 回答已達本小時上限" in messages[-1]["content"]


def test_chat_unexpected_answer_error_refunds_quota_and_shows_search_results(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "1")
    _set_chat_search(app, monkeypatch)

    def explode(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(app, "generate_chat_answer", explode)

    _, messages = _run_chat(app, "問題")

    assert "AI 回答暫時無法產生" in messages[-1]["content"]
    assert "secret detail" not in messages[-1]["content"]
    assert "題幹：查證身分題" in messages[-1]["content"]
    assert not app._answer_requests


def test_chat_sources_list_only_evidence_the_model_saw(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    _set_chat_search(app, monkeypatch)
    monkeypatch.setattr(app, "generate_chat_answer", lambda *args, **kwargs: {
        "status": "ok", "grounded": "依據回答。[題1]", "supplement": "",
        "citations": ["[題1]"], "invalid_citations": [], "included": {"題": 1, "條": 0}})

    _, messages = _run_chat(app, "問題")

    assert messages[-1]["metadata"]["title"] == "檢索到的考題與條文（1 題、0 條）"
    assert "[條1]" not in messages[-1]["content"]


def test_chat_cache_key_ignores_case_and_spacing_and_cache_is_bounded(app, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-key")
    _set_chat_search(app, monkeypatch)
    monkeypatch.setattr(app, "_ANSWER_CACHE_MAX", 2)
    calls = []

    def generate(query, results, laws, *, history=()):
        calls.append(query)
        return {"status": "ok", "grounded": "依據回答。[題1]", "supplement": "",
                "citations": ["[題1]"], "invalid_citations": []}

    monkeypatch.setattr(app, "generate_chat_answer", generate)

    _run_chat(app, "Miranda  警告")
    _run_chat(app, " miranda 警告 ")
    assert len(calls) == 1

    _run_chat(app, "第二題")
    _run_chat(app, "第三題")
    assert list(app._answer_cache) == ["第二題", "第三題"]


@pytest.mark.parametrize("message", ["[題1] 的答案為什麼是 A？", "【條2】在講什麼", "題 3 呢"])
def test_follow_up_citing_a_source_number_searches_the_previous_question_again(
        app, monkeypatch, message):
    # Seen live: "[題1] 的答案為什麼…" was searched literally and returned unrelated questions.
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    searched = _set_chat_search(app, monkeypatch)
    history = [{"role": "user", "content": "警察查證身分"},
               {"role": "assistant", "content": "前文"}]

    _run_chat(app, message, history)
    assert [query for query, _ in searched] == ["警察查證身分"]

    searched.clear()
    _run_chat(app, message)
    assert [query for query, _ in searched] == [message]


def test_numbered_follow_ups_in_a_row_search_the_last_real_question(app, monkeypatch):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    searched = _set_chat_search(app, monkeypatch)
    history = [{"role": "user", "content": "警察查證身分"},
               {"role": "assistant", "content": "前文"},
               {"role": "user", "content": "[題1] 為什麼"},
               {"role": "assistant", "content": "前文"}]

    _run_chat(app, "[條2] 呢", history)

    assert [query for query, _ in searched] == ["警察查證身分"]


def test_new_question_that_merely_contains_a_count_is_searched_as_written(app, monkeypatch):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    searched = _set_chat_search(app, monkeypatch)
    history = [{"role": "user", "content": "警察查證身分"},
               {"role": "assistant", "content": "前文"}]

    _run_chat(app, "107年刑法選擇題 5 題", history)

    assert searched[0][0] == "107年刑法選擇題 5 題"


def test_numbered_follow_up_repeats_the_expanded_search_of_the_previous_turn(app, monkeypatch):
    # The previous turn was answered from "earlier question + question"; the numbers come from that search.
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    low, _ = _chat_evidence("低信心題", low_confidence=True)
    good, _ = _chat_evidence("重查結果")
    searched = []

    def search(query):
        searched.append(query)
        return (good if query == "警察攔檢 要帶證件嗎" else low), [], 1, ""

    monkeypatch.setattr(app, "_search_data", search)
    history = [{"role": "user", "content": "警察攔檢"},
               {"role": "assistant", "content": "前文"},
               {"role": "user", "content": "要帶證件嗎"},
               {"role": "assistant", "content": "前文"}]

    _, messages = _run_chat(app, "[題1] 的理由是什麼？", history)

    assert searched == ["要帶證件嗎", "警察攔檢 要帶證件嗎"]
    assert "題幹：重查結果" in messages[-1]["content"]


@pytest.mark.parametrize("message", ["題 107 年警察特考試題", "條 10 警察法規定為何"])
def test_new_question_starting_with_a_year_or_article_number_is_searched_as_written(
        app, monkeypatch, message):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    searched = _set_chat_search(app, monkeypatch)
    history = [{"role": "user", "content": "警察查證身分"},
               {"role": "assistant", "content": "前文"}]

    _run_chat(app, message, history)

    assert searched[0][0] == message


def test_numbered_follow_up_skips_an_empty_message_in_the_history(app, monkeypatch):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    searched = _set_chat_search(app, monkeypatch)
    history = [{"role": "user", "content": "警察查證身分"},
               {"role": "assistant", "content": "前文"},
               {"role": "user", "content": " "},
               {"role": "assistant", "content": "請輸入問題。"}]

    _run_chat(app, "[題1] 的理由是什麼？", history)

    assert searched[0][0] == "警察查證身分"
