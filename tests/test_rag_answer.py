import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from scripts.rag import answer, query


class FakeClient:
    def __init__(self, content=None, error=None, reasoning="忽略我"):
        self.content = content
        self.error = error
        self.reasoning = reasoning
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return {"choices": [{"message": {
            "content": self.content,
            "reasoning_content": self.reasoning,
        }}]}


@pytest.fixture
def evidence():
    results = [
        {
            "stem": "警察依何條件得查證身分？",
            "options": {"A": "依法", "B": "任意"},
            "answer": "A",
            "answer_status": "normal",
            "answer_source": "moex_official",
            "citations": [{"year": 113, "subject": "警察法規"}],
        },
        {
            "stem": "某題答案有爭議",
            "answer": "C",
            "answer_status": "normal",
            "answer_conflicts": [{"value": "C"}, {"value": "D"}],
            "answer_conflict_reason": "來源資料夾答案不一致，待核實",
            "citations": [{"year": 112, "subject": "警察法規"}],
        },
        {
            "stem": "多答案題",
            "answer_status": "multiple",
            "answer_values": ["B", "D"],
            "citations": [{"year": 111, "subject": "警察勤務"}],
        },
        {
            "stem": "送分題",
            "answer_status": "free",
            "citations": [{"year": 110, "subject": "警察法規"}],
        },
    ]
    laws = [{
        "law_name": "警察職權行使法",
        "article_no": "第6條",
        "law_modified_date": "20251006",
        "content": "警察得依法查證身分。",
    }]
    return results, laws


def test_context_numbers_questions_and_preserves_uncertain_answer_states(evidence):
    context = answer.build_context(*evidence)
    assert "[題1]" in context and "[題4]" in context and "[條1]" in context
    assert "113年／警察法規" in context and "答案：A（考選部官方）" in context
    assert "待核實（答案存在歧異" in context and "來源資料夾答案不一致" in context
    assert "多答案：B、D" in context and "送分" in context
    assert "警察職權行使法" in context and "20251006" in context
    assert len(answer.build_context([], [{"content": "x" * 20_000}])) <= answer.MAX_CONTEXT_CHARS


def test_citation_validation_removes_out_of_range_references(evidence, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "do-not-leak")
    client = FakeClient("結論甲。[題1] 結論乙。[條1] 錯誤引用[題8]")
    result = answer.generate_answer("查詢", *evidence, client=client)
    assert result["status"] == "ok"
    assert result["citations"] == ["[題1]", "[條1]"]
    assert result["invalid_citations"] == ["[題8]"]
    assert "[題8]" not in result["text"]
    assert client.calls[0][1]["max_tokens"] >= 4000
    assert client.calls[0][1]["api_key"] == "do-not-leak"
    assert client.calls[0][1]["model"] == "MiniMax-M3.1-Flash"


def test_no_valid_citation_is_untrusted_but_insufficient_answer_passes(evidence, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "test-key")
    invalid = answer.generate_answer("查詢", *evidence, client=FakeClient("結論。[題99]"))
    assert invalid["status"] == "untrusted"
    assert invalid["text"] == answer.UNCITED_ANSWER
    assert invalid["invalid_citations"] == ["[題99]"]

    insufficient = answer.generate_answer(
        "查詢", *evidence, client=FakeClient(answer.INSUFFICIENT_DATA))
    assert insufficient["status"] == "ok"
    assert insufficient["text"] == answer.INSUFFICIENT_DATA
    assert insufficient["citations"] == []


def test_think_is_removed_and_reasoning_content_is_ignored(evidence, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "test-key")
    client = FakeClient("<think>內部推理[題9]</think>答案依據題目。[題1]")
    result = answer.generate_answer("查詢", *evidence, client=client)
    assert result["text"] == "答案依據題目。[題1]"
    assert "內部推理" not in result["text"] and "忽略我" not in result["text"]


def test_api_key_is_not_sent_in_question_or_returned(evidence, monkeypatch):
    key = "sensitive-api-key"
    monkeypatch.setenv("RAG_LLM_API_KEY", key)
    client = FakeClient(f"回答 {key}。[題1]")
    results, laws = evidence
    results[0]["stem"] += " " + key
    result = answer.generate_answer(key, results, laws, client=client)
    assert key not in client.calls[0][0][1]["content"]
    assert key not in result["text"]


def test_malformed_provider_response_is_a_safe_error(evidence, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "test-key")

    class MalformedClient:
        def complete(self, *args, **kwargs):
            return {"choices": [{"message": {"reasoning_content": "no answer"}}]}

    result = answer.generate_answer("查詢", *evidence, client=MalformedClient())
    assert result["status"] == "error"
    assert result["reason"] == "模型回應格式錯誤"


def test_reasoning_exhausting_max_tokens_is_reported(evidence, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "test-key")

    class LengthClient:
        def complete(self, *args, **kwargs):
            return {"choices": [{"finish_reason": "length",
                                 "message": {"content": "", "reasoning_content": "長推理"}}]}

    result = answer.generate_answer("查詢", *evidence, client=LengthClient())
    assert result["status"] == "error"
    assert result["reason"] == "模型推理超出長度上限"


def test_insufficient_answer_with_trailing_period_passes(evidence, monkeypatch):
    monkeypatch.setenv("RAG_LLM_API_KEY", "test-key")
    result = answer.generate_answer("查詢", *evidence,
                                    client=FakeClient(answer.INSUFFICIENT_DATA + "。"))
    assert result["status"] == "ok"


def test_http_payload_requests_low_reasoning_effort(monkeypatch):
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices": []}'

    def fake_urlopen(request, timeout):
        sent.update(json.loads(request.data.decode("utf-8")))
        return Response()

    monkeypatch.setattr(answer, "urlopen", fake_urlopen)
    monkeypatch.delenv("RAG_LLM_REASONING_EFFORT", raising=False)
    answer._http_complete([], model="m", api_key="k", base_url="https://x/v1",
                          timeout=1, max_tokens=10)
    assert sent["reasoning_effort"] == "low"


@pytest.mark.parametrize("error", [
    TimeoutError("secret-value timed out"),
    HTTPError("https://example.invalid", 429, "secret-value", {}, None),
])
def test_provider_errors_do_not_leak_api_key_or_exception_text(evidence, monkeypatch, error):
    key = "secret-value"
    monkeypatch.setenv("RAG_LLM_API_KEY", key)
    result = answer.generate_answer("查詢", *evidence, client=FakeClient(error=error))
    assert result["status"] == "error"
    assert key not in json.dumps(result, ensure_ascii=False)
    assert "secret-value" not in result.get("reason", "")


def test_missing_key_disables_and_low_confidence_without_laws_skips(evidence, monkeypatch):
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    client = FakeClient("不應呼叫")
    disabled = answer.generate_answer("查詢", *evidence, client=client)
    assert disabled["status"] == "disabled" and not client.calls

    monkeypatch.setenv("RAG_LLM_API_KEY", "test-key")
    low = [{"stem": "低信心", "low_confidence": True}]
    skipped = answer.generate_answer("查詢", low, [], client=client)
    assert skipped["status"] == "skipped" and skipped["text"] == answer.LOW_CONFIDENCE_ANSWER
    assert not client.calls


class FakeRetriever:
    meta = {"embedding_text_version": 2}

    def __init__(self, *args, **kwargs):
        pass

    def search(self, *args, **kwargs):
        return [{"rank": 1, "question_id": "q1", "type": "choice",
                 "stem": "查證身分題", "answer": "A", "answer_status": "normal",
                 "citations": [{"year": 113, "subject": "警察法規"}]}]

    def search_laws(self, *args, **kwargs):
        return [{"law_name": "警察職權行使法", "article_no": "第6條",
                 "law_modified_date": "20251006", "content": "法條"}]

    def close(self):
        pass


def test_cli_answer_flag_and_json_include_answer(monkeypatch, capsys):
    monkeypatch.setattr(query, "Retriever", FakeRetriever)
    monkeypatch.setattr(query, "generate_answer", lambda *args: {
        "status": "ok", "text": "整理回答。[題1]", "citations": ["[題1]"],
        "invalid_citations": [],
    })
    query.main(["查證身分", "--db", "unused.sqlite", "--mode", "keyword", "--answer"])
    output = capsys.readouterr().out
    assert output.startswith("AI 整理回答（僅供參考，請以考選部公告與現行條文為準）")
    assert "整理回答。[題1]" in output and "題幹：查證身分題" in output

    query.main(["查證身分", "--db", "unused.sqlite", "--mode", "keyword", "--answer", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["answer"]["status"] == "ok"
    assert payload["answer"]["citations"] == ["[題1]"]


def test_cli_without_key_shows_notice_and_keeps_search_results(monkeypatch, capsys):
    monkeypatch.setattr(query, "Retriever", FakeRetriever)
    monkeypatch.delenv("RAG_LLM_API_KEY", raising=False)
    query.main(["查證身分", "--db", "unused.sqlite", "--mode", "keyword", "--answer"])
    output = capsys.readouterr().out
    assert "未設定 RAG_LLM_API_KEY" in output and "題幹：查證身分題" in output

    query.main(["查證身分", "--db", "unused.sqlite", "--mode", "keyword", "--answer", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["answer"]["status"] == "disabled"
    assert payload["results"][0]["question_id"] == "q1"


def test_space_hourly_limit_and_query_cache_escape_answer(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("RAG_LLM_API_KEY", "space-test-key")
    monkeypatch.setenv("RAG_LLM_MAX_PER_HOUR", "1")
    spec = importlib.util.spec_from_file_location("rag_answer_space_app", root / "space/app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    calls = []
    app.retriever = FakeRetriever()
    app.mode, app.options, app.law_k = "keyword", {}, 1
    app.law_min_score = None
    app._answer_cache.clear()
    app._answer_requests.clear()
    monkeypatch.setattr(app, "generate_answer", lambda *args: calls.append(args) or {
        "status": "ok", "text": "<script>bad</script>。[題1]",
        "citations": ["[題1] <img>"], "invalid_citations": [],
    })
    try:
        first = app.run_answer("查證身分")
        second = app.run_answer("查證身分")
        assert len(calls) == 1
        assert "&lt;script&gt;bad&lt;/script&gt;" in first
        assert "&lt;img&gt;" in first
        assert len(calls) == 1 and "題幹：查證身分題" in second

        limited = app.run_answer("另一個問題")
        assert "AI 回答已達本小時上限" in limited
        assert len(calls) == 1
    finally:
        app.executor.shutdown(wait=True)
