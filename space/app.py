"""Search exam questions locally, or use a public HF Dataset in a Space."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from html import escape
import os
from pathlib import Path
import sys
from threading import Lock
import time
from urllib.parse import quote

if os.environ.get("SPACES_ZERO_GPU"):
    import spaces

    @spaces.GPU(duration=1)
    def _zero_gpu_marker():
        """Register the required marker; actual retrieval runs on CPU."""
        pass


HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "scripts/rag/retrieval.py").is_file() else HERE.parent
sys.path.insert(0, str(ROOT / "scripts/rag"))
from query import (LOW_CONFIDENCE_NOTICE, MOEX_CORRECTION_INFO_URL, _is_official_exam_pdf,
                   format_law_modified_date, format_results, is_official_law_url,
                   truncate_law_content)
from retrieval import (LEGACY_EMBEDDING_TEXT_VERSION, LEGACY_INDEX_WARNING, Retriever, add_search_arguments,
                       embedding_text_version, parse_search_args, search_arguments)
from answer import generate_answer


executor = ThreadPoolExecutor(max_workers=1)
retriever = None
options = None
mode = None
law_k = 3
law_min_score = None
_answer_cache = {}
_answer_requests = deque()
_answer_lock = Lock()
_ANSWER_CACHE_SECONDS = 3600
_ANSWER_CACHE_MAX = 500


def _answer_limit():
    try:
        return max(0, int(os.environ.get("RAG_LLM_MAX_PER_HOUR", "30")))
    except ValueError:
        return 30


def index_path():
    local = os.environ.get("RAG_INDEX_PATH")
    if local:
        path = Path(local)
        if not path.is_file():
            raise ValueError(f"索引不存在：{path}")
        return path
    repo = os.environ.get("HF_DATASET_REPO")
    if not repo:
        raise ValueError("請設定公開 Dataset 的 HF_DATASET_REPO，或設定本機 RAG_INDEX_PATH")
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download(repo, "index-bge-m3.sqlite", repo_type="dataset",
                                local_dir=ROOT / ".space-data", token=False))


def initialize(db):
    global retriever, options, mode, law_k, law_min_score
    import torch
    torch.set_num_threads(2)
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    parser.add_argument("--mode", default="hybrid")
    parser.add_argument("--law-k", type=int, default=3)
    add_search_arguments(parser)
    args = parse_search_args(parser, ["--profile", str(ROOT / "rag/bench_report.json"), "--db", str(db)])
    if args.use_reranker:
        raise ValueError("此介面不支援需要重排模型的 profile")
    instance = Retriever(args.db, device="cpu")
    try:
        if instance.meta.get("model") != "BAAI/bge-m3":
            raise ValueError("索引模型與 BGE-M3 profile 不符")
        instance._load_vectors()
        instance.search("警察", k=1, mode=args.mode, **search_arguments(args))
    except BaseException:
        instance.close()
        raise
    if args.law_k < 0:
        instance.close()
        raise ValueError("--law-k 不可小於 0")
    retriever, options, mode, law_k = instance, search_arguments(args), args.mode, args.law_k
    law_min_score = args.law_min_vector_score


def _render_questions(results, *, include_notice=True):
    lines = []
    if not results:
        return "查無符合題目。"
    if include_notice and any(item.get("low_confidence") for item in results):
        lines.extend([escape(LOW_CONFIDENCE_NOTICE), ""])
    for item in results:
        for line in format_results([item], include_notice=False).splitlines():
            line = line.replace("（完整內容見 --json）", "").replace("，詳見 --json 的 answer_conflicts", "")
            if line.startswith("題幹："):
                if item.get("passage"):
                    lines.append(escape("題組文章：" + " ".join(item["passage"].split())))
                lines.append(escape("題幹：" + " ".join(item.get("stem", "").split())))
                lines.extend(escape(f"({' '.join(str(key).split())}) {' '.join(str(value).split())}")
                             for key, value in sorted(item.get("options", {}).items()))
                continue
            if line == "更正查詢：" + MOEX_CORRECTION_INFO_URL:
                lines.append(f"更正查詢：[考選部考畢試題與更正答案查詢]({MOEX_CORRECTION_INFO_URL})")
                continue
            if line.startswith("考選部答案 PDF："):
                _, url = line.split("：", 1)
                if _is_official_exam_pdf(url):
                    safe_url = quote(url, safe=":/?&=%#-._~+;,")
                    lines.append(f"考選部答案 PDF：[開啟考選部官方答案]({safe_url})")
                else:
                    lines.append("考選部答案 PDF：非考選部官方答案")
                continue
            if line.startswith(("試題 PDF：", "原始答案 PDF：")):
                label, url = line.split("：", 1)
                if _is_official_exam_pdf(url, file_type="S" if label == "原始答案 PDF" else "Q"):
                    description = "開啟考選部原始試題" if label == "試題 PDF" else "開啟考選部原始答案（須另查更正）"
                    safe_url = quote(url, safe=":/?&=%#-._~+;,")
                    lines.append(f"{label}：[{description}]({safe_url})")
                    continue
                if label == "原始答案 PDF":
                    lines.append(f"{label}：" + ("未解析" if url == "未解析" else "非考選部原始答案"))
                    continue
                lines.append(f"{label}：" + ("未解析" if url == "未解析" else "非考選部試題"))
                continue
            lines.append(escape(line))
        lines.append("")
    return "  \n".join(lines)


def render_laws(laws):
    if not laws:
        return ""
    lines = ["## 相關現行條文"]
    for law in laws:
        title = escape(f"{law.get('law_name', '')} {law.get('article_no', '')}"
                       f"（法規最後修正：{format_law_modified_date(law.get('law_modified_date'))}）")
        lines.extend(["", title, "", escape(truncate_law_content(law.get("content", "")))])
        url = law.get("url")
        if is_official_law_url(url):
            lines.extend(["", f"[全國法規資料庫]({quote(url, safe=':/?&=%#-._~+;,')})"])
    return "  \n".join(lines)


def render(results, *, include_notice=True, laws=None):
    question_text = _render_questions(results, include_notice=include_notice)
    law_text = render_laws(laws or [])
    return question_text + ("\n\n" + law_text if law_text else "")


def _search_data(query):
    started = time.perf_counter()
    results = retriever.search(query, k=5, mode=mode, **options)
    law_results = []
    if law_k and hasattr(retriever, "search_laws"):
        law_options = {key: options[key] for key in (
            "keyword_weight", "vector_weight", "rrf_k", "candidates", "expand_abbreviations"
        ) if key in options}
        law_results = retriever.search_laws(query, k=law_k, min_vector_score=law_min_score, **law_options)
    elapsed_ms = (time.perf_counter() - started) * 1000
    meta = getattr(retriever, "meta", None)
    warning = ""
    if any(item.get("low_confidence") for item in results):
        warning += LOW_CONFIDENCE_NOTICE + "\n\n"
    if (mode != "keyword" and meta is not None
            and embedding_text_version(meta) == LEGACY_EMBEDDING_TEXT_VERSION):
        warning += LEGACY_INDEX_WARNING + "\n\n"
    return results, law_results, elapsed_ms, warning


def _search_output(results, law_results, elapsed_ms, warning):
    return (f"{warning}查詢耗時：{elapsed_ms:.0f} 毫秒\n\n"
            f"{render(results, include_notice=False, laws=law_results)}")


def run_search(query):
    if not query or not query.strip():
        return "請輸入問題。"
    if len(query) > 2000:
        return "問題請勿超過 2,000 字。"
    results, law_results, elapsed_ms, warning = _search_data(query)
    return _search_output(results, law_results, elapsed_ms, warning)


def _store_answer(key, result):
    with _answer_lock:
        _answer_cache.pop(key, None)
        _answer_cache[key] = (time.monotonic() + _ANSWER_CACHE_SECONDS, dict(result))
        while len(_answer_cache) > _ANSWER_CACHE_MAX:
            _answer_cache.pop(next(iter(_answer_cache)))


def _cached_answer(query, results, laws):
    now = time.monotonic()
    # Whitespace variants must not bypass the cache and spend shared quota.
    key = " ".join(query.split())
    with _answer_lock:
        cached = _answer_cache.get(key)
        if cached and cached[0] > now:
            return dict(cached[1])
        _answer_cache.pop(key, None)

    if any(item.get("low_confidence") for item in results) and not laws:
        result = generate_answer(query, results, laws)
        _store_answer(key, result)
        return result

    with _answer_lock:
        cutoff = now - _ANSWER_CACHE_SECONDS
        while _answer_requests and _answer_requests[0] <= cutoff:
            _answer_requests.popleft()
        if len(_answer_requests) >= _answer_limit():
            return {
                "status": "limited",
                "text": "AI 回答已達本小時上限",
                "citations": [],
                "invalid_citations": [],
            }
        _answer_requests.append(now)
    result = generate_answer(query, results, laws)
    if result.get("status") in ("ok", "untrusted", "skipped", "disabled"):
        _store_answer(key, result)
    else:
        # A failed provider call did not produce an answer; give the slot back.
        with _answer_lock:
            try:
                _answer_requests.remove(now)
            except ValueError:
                pass
    return result


def _render_answer(result):
    lines = ["## AI 整理回答（僅供參考，請以考選部公告與現行條文為準）",
             escape(result.get("text", ""))]
    citations = result.get("citations") or []
    if citations:
        lines.extend(["", "引用來源：" + "、".join(escape(value) for value in citations)])
    invalid = result.get("invalid_citations") or []
    if invalid:
        lines.extend(["", "已移除無效引用：" + "、".join(escape(value) for value in invalid)])
    reason = result.get("reason")
    if reason:
        lines.extend(["", escape(reason)])
    return "  \n".join(lines)


def run_answer(query):
    if not query or not query.strip():
        return "請輸入問題。"
    if len(query) > 2000:
        return "問題請勿超過 2,000 字。"
    results, law_results, elapsed_ms, warning = executor.submit(_search_data, query).result()
    answer_result = _cached_answer(query, results, law_results)
    full_results = _search_output(results, law_results, elapsed_ms, warning)
    return _render_answer(answer_result) + "\n\n---\n\n" + full_results


def search(query):
    # SQLite connections and the model stay on their single owning thread.
    return executor.submit(run_search, query).result()


def main():
    import gradio as gr
    executor.submit(initialize, index_path()).result()
    with gr.Blocks(title="警察考古題檢索") as demo:
        gr.Markdown("# 警察考古題檢索\n輸入問題，查找相關考古題及考選部原始試題。")
        question = gr.Textbox(label="問題", placeholder="例如：警察什麼情況可以查證身分？", lines=2)
        button = gr.Button("搜尋", variant="primary")
        answer_button = gr.Button("AI 整理回答") if os.environ.get("RAG_LLM_API_KEY") else None
        answer = gr.Markdown(label="搜尋結果")
        button.click(search, inputs=question, outputs=answer, api_name="search")
        question.submit(search, inputs=question, outputs=answer, api_name=False)
        if answer_button is not None:
            answer_button.click(run_answer, inputs=question, outputs=answer, api_name="answer")
    host = os.environ.get("RAG_HOST", "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1")
    demo.queue(default_concurrency_limit=1).launch(
        server_name=host, server_port=int(os.environ.get("RAG_PORT", "7860")), show_error=True)


if __name__ == "__main__":
    main()
