"""Search exam questions locally, or use a public HF Dataset in a Space."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from html import escape
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "scripts/rag/retrieval.py").is_file() else HERE.parent
sys.path.insert(0, str(ROOT / "scripts/rag"))
from query import format_results
from retrieval import Retriever, add_search_arguments, parse_search_args, search_arguments


executor = ThreadPoolExecutor(max_workers=1)
retriever = None
options = None
mode = None


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
    global retriever, options, mode
    import torch
    torch.set_num_threads(2)
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    parser.add_argument("--mode", default="hybrid")
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
    retriever, options, mode = instance, search_arguments(args), args.mode


def render(results):
    lines = []
    if not results:
        return "查無符合題目。"
    for item in results:
        for line in format_results([item]).splitlines():
            line = line.replace("（完整內容見 --json）", "").replace("，詳見 --json 的 answer_conflicts", "")
            if line.startswith("題幹："):
                if item.get("passage"):
                    lines.append(escape("題組文章：" + " ".join(item["passage"].split())))
                lines.append(escape("題幹：" + " ".join(item.get("stem", "").split())))
                lines.extend(escape(f"({key}) {value}") for key, value in sorted(item.get("options", {}).items()))
                continue
            if line.startswith("試題 PDF："):
                url = line.removeprefix("試題 PDF：")
                parsed = urlsplit(url)
                if (parsed.scheme == "https" and parsed.netloc == "wwwq.moex.gov.tw"
                        and parsed.path == "/exam/wHandExamQandA_File.ashx"):
                    lines.append(f"試題 PDF：[開啟考選部原始試題]({url})")
                    continue
            lines.append(escape(line))
        lines.append("")
    return "  \n".join(lines)


def run_search(query):
    if not query or not query.strip():
        return "請輸入問題。"
    if len(query) > 2000:
        return "問題請勿超過 2,000 字。"
    started = time.perf_counter()
    results = retriever.search(query, k=5, mode=mode, **options)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return f"查詢耗時：{elapsed_ms:.0f} 毫秒\n\n{render(results)}"


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
        answer = gr.Markdown(label="搜尋結果")
        button.click(search, inputs=question, outputs=answer, api_name="search")
        question.submit(search, inputs=question, outputs=answer, api_name=False)
    host = os.environ.get("RAG_HOST", "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1")
    demo.queue(default_concurrency_limit=1).launch(
        server_name=host, server_port=int(os.environ.get("RAG_PORT", "7860")), show_error=True)


if __name__ == "__main__":
    main()
