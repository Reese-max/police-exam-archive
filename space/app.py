"""Search exam questions locally, or use a public HF Dataset in a Space."""

import argparse
import atexit
import hashlib
import io
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from html import escape
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from threading import Lock
import time
from urllib.parse import quote
from urllib.request import urlopen
import zipfile

if os.environ.get("SPACES_ZERO_GPU"):
    import spaces

    @spaces.GPU(duration=1)
    def _zero_gpu_marker():
        """Register the required marker; actual retrieval runs on CPU."""
        pass


HERE = Path(__file__).resolve().parent
WEB = HERE / "web" / "dist"
ROOT = HERE if (HERE / "scripts/rag/retrieval.py").is_file() else HERE.parent
sys.path.insert(0, str(ROOT / "scripts/rag"))
from query import (LOW_CONFIDENCE_NOTICE, MOEX_CORRECTION_INFO_URL, _is_official_exam_pdf,
                   format_law_modified_date, format_results, is_official_law_url,
                   truncate_law_content)
from retrieval import (LEGACY_EMBEDDING_TEXT_VERSION, LEGACY_INDEX_WARNING, Retriever, add_search_arguments,
                       embedding_text_version, parse_search_args, search_arguments)
from answer import (MARKDOWN_LINK, _unlink, _valid_http_url, chat_enabled,
                    essay_enabled, generate_chat_answer, generate_essay)


executor = ThreadPoolExecutor(max_workers=1)
retriever = None
options = None
mode = None
ESSAY_LOCAL = None
law_k = 3
# an essay answers every sub-question from the articles: three hits miss whole sub-questions
ESSAY_LAW_K = 8
law_min_score = None
_answer_cache = {}
_answer_requests = deque()
# "[題1]" anywhere, or a bare "題 3" only at the start; "選擇題 5 題", "題 107 年…" and
# "條 10 …" are new questions (at most 5 questions and 3 articles are listed).
_SOURCE_REFERENCE = re.compile(r"[\[［【](?:題|條)\s*\d+[\]］】]|^\s*(?:題|條)\s*\d(?!\s*[\d年])")
_ESSAY_PREFIX = re.compile(r"^\s*申論(?:題)?\s*[：:]\s*(.+)", re.DOTALL)
_answer_lock = Lock()
_ANSWER_CACHE_SECONDS = 3600
_ANSWER_CACHE_MAX = 500
# 教育部標準楷書 5.1, unmodified: the only font the essay server accepts for the 165 answer sheet
_PAPER_FONT_SHA256 = "e2b6b1bd1d6303672a68d5057a1f1e4b5361e3d8842373ff3bd1c71fb9ea9b98"


def _paper_font(work):
    """Copy the owner-configured 165 answer-sheet font into work; None unless it is the exact file."""
    source = (os.environ.get("RAG_ESSAY_PAPER_FONT") or "").strip()
    if not source:
        return None
    try:
        if source.startswith(("https://", "http://")):
            with urlopen(source, timeout=120) as response:
                data = response.read()
        else:
            path = Path(source)
            data = (path if path.is_absolute() else HERE / path).read_bytes()
        fonts = [data]
        if data[:2] == b"PK":  # the official download is a zip
            archive = zipfile.ZipFile(io.BytesIO(data))
            fonts = (archive.read(name) for name in archive.namelist()
                     if name.lower().endswith(".ttf"))
        for font in fonts:
            if hashlib.sha256(font).hexdigest() == _PAPER_FONT_SHA256:
                target = work / "edukai-5.1.ttf"
                target.write_bytes(font)
                return target
        print("165 原稿紙未啟用：字型檔不是教育部標準楷書 5.1")
    except Exception as exc:
        print(f"165 原稿紙未啟用：{type(exc).__name__}")
    return None


def _start_essay_mcp():
    global ESSAY_LOCAL
    ESSAY_LOCAL = None
    process = None

    def terminate_process():
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass

    try:
        configured_dir = (os.environ.get("RAG_ESSAY_MCP_DIR") or "").strip()
        if not configured_dir or os.environ.get("RAG_ESSAY_MCP_URL"):
            return None
        source = Path(configured_dir)
        if not source.is_absolute():
            source = HERE / source
        if not (source / "dist" / "src" / "index.js").is_file():
            print("申論排版服務未啟動：找不到 dist/src/index.js")
            return None

        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            print("申論排版服務未啟動：找不到 node 或 npm")
            return None

        work = Path(tempfile.mkdtemp(prefix="essay-")).resolve()
        if (source / "node_modules").is_dir():
            run_dir = source
        else:
            run_dir = work / "app"
            shutil.copytree(source, run_dir)

        child_env = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                        "SYSTEMROOT", "TEMP", "TMP")
            if key in os.environ
        }
        if run_dir == work / "app":
            subprocess.run(
                [npm, "ci", "--omit=dev", "--no-audit", "--no-fund", "--ignore-scripts"],
                cwd=run_dir, env=child_env, check=True, timeout=600,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

        answers = work / "answers"
        exports = work / "exports"
        answers.mkdir()
        exports.mkdir()
        paper_font = _paper_font(work)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        token = secrets.token_urlsafe(32)
        child_env.update({
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "MCP_AUTH_TOKEN": token,
            "ESSAY_PUBLIC_BASE_URL": origin,
            "ESSAY_MCP_ANSWER_DIR": str(answers),
            "ESSAY_MCP_EXPORT_DIR": str(exports),
            "ESSAY_MCP_PDF_FONT": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "ESSAY_MCP_PDF_BOLD_FONT": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        })
        if paper_font:
            child_env["ESSAY_MCP_PAPER_FONT"] = str(paper_font)
        process = subprocess.Popen(
            [node, "dist/src/index.js"], cwd=run_dir, env=child_env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        atexit.register(process.terminate)

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                terminate_process()
                return None
            try:
                with urlopen(origin + "/health", timeout=2) as response:
                    ready = response.getcode() == 200
            except Exception:
                ready = False
            if ready:
                folder = work / "downloads"
                folder.mkdir()
                try:
                    os.environ["RAG_ESSAY_MCP_URL"] = origin + "/mcp"
                    os.environ["RAG_ESSAY_MCP_TOKEN"] = token
                    if paper_font:
                        os.environ.setdefault("RAG_ESSAY_TEMPLATE", "police_information_essay_165")
                except Exception:
                    os.environ.pop("RAG_ESSAY_MCP_URL", None)
                    os.environ.pop("RAG_ESSAY_MCP_TOKEN", None)
                    raise
                ESSAY_LOCAL = (origin, folder.resolve())
                return ESSAY_LOCAL
            time.sleep(0.5)
        terminate_process()
        return None
    except Exception as exc:
        terminate_process()
        os.environ.pop("RAG_ESSAY_MCP_URL", None)
        os.environ.pop("RAG_ESSAY_MCP_TOKEN", None)
        print(f"申論排版服務未啟動：{type(exc).__name__}")
        return None


def _public_essay_url(url, format_name):
    if ESSAY_LOCAL is None:
        return url
    try:
        if format_name not in ("pdf", "docx"):
            return ""
        origin, folder = ESSAY_LOCAL
        source_url = str(url or "")
        match = re.fullmatch(
            rf"{re.escape(origin)}/downloads/([0-9a-f-]{{36}})/([^/?#]+)",
            source_url,
        )
        if not match:
            return ""
        handle, filename = match.groups()
        if ".." in filename:
            return ""
        with urlopen(source_url, timeout=30) as response:
            content = response.read(20_000_001)
        if len(content) > 20_000_000:
            return ""
        target = folder / handle / f"申論擬答.{format_name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        # shortcut: 複製出來的檔案不會過期，Space 重啟才清掉；upgrade: 用量大時加清理。
        base = (f"https://{os.environ['SPACE_HOST']}" if os.environ.get("SPACE_HOST")
                else f"http://127.0.0.1:{os.environ.get('RAG_PORT', '7860')}")
        return f"{base}/gradio_api/file={target.as_posix()}"
    except Exception:
        return ""


def _answer_limit():
    """Hourly cap on model calls; None (variable unset) means unlimited."""
    value = (os.environ.get("RAG_LLM_MAX_PER_HOUR") or "").strip()
    if not value:
        return None
    try:
        return max(0, int(value))
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


def _render_questions(results, *, include_notice=True, include_numbers=False):
    lines = []
    if not results:
        return "查無符合題目。"
    if include_notice and any(item.get("low_confidence") for item in results):
        lines.extend([escape(LOW_CONFIDENCE_NOTICE), ""])
    for index, item in enumerate(results, 1):
        if include_numbers:
            lines.append(escape(f"[題{index}]"))
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


def render_laws(laws, *, include_numbers=False):
    if not laws:
        return ""
    lines = ["## 相關現行條文"]
    for index, law in enumerate(laws, 1):
        if include_numbers:
            lines.extend(["", escape(f"[條{index}]")])
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


def _search_data(query, laws=None):
    started = time.perf_counter()
    results = retriever.search(query, k=5, mode=mode, **options)
    law_results = []
    if law_k and hasattr(retriever, "search_laws"):
        law_options = {key: options[key] for key in (
            "keyword_weight", "vector_weight", "rrf_k", "candidates", "expand_abbreviations"
        ) if key in options}
        law_results = retriever.search_laws(query, k=laws or law_k, min_vector_score=law_min_score, **law_options)
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


def _cached_chat_answer(query, results, laws, history=(), *, use_cache=True, generate=None):
    generate_answer = generate or generate_chat_answer
    now = time.monotonic()
    key = " ".join(query.split()).casefold()
    if not chat_enabled():
        return generate_answer(query, results, laws, history=history)

    if use_cache:
        with _answer_lock:
            cached = _answer_cache.get(key)
            if cached and cached[0] > now:
                return dict(cached[1])
            _answer_cache.pop(key, None)

    limit = _answer_limit()
    ticket = (now, object())
    with _answer_lock:
        cutoff = now - _ANSWER_CACHE_SECONDS
        while _answer_requests and _answer_requests[0][0] <= cutoff:
            _answer_requests.popleft()
        if limit is not None:
            if len(_answer_requests) >= limit:
                return {"status": "limited", "citations": [], "invalid_citations": [],
                        "reason": "AI 回答已達本小時上限"}
            _answer_requests.append(ticket)

    try:
        result = generate_answer(query, results, laws, history=history)
    except Exception as exc:
        # Keep the chat usable and the quota slot refunded; the message may hold user text, so log the type only.
        print(f"chat answer failed: {type(exc).__name__}", file=sys.stderr)
        result = {"status": "error", "reason": "內部錯誤"}
    if result.get("status") == "ok":
        if use_cache:
            _store_answer(key, result)
    else:
        with _answer_lock:
            try:
                _answer_requests.remove(ticket)
            except ValueError:
                pass
    return result


def _history_text(history):
    messages = []
    for item in history or []:
        if isinstance(item, dict):
            role, content = item.get("role"), item.get("content")
            metadata = item.get("metadata")
        else:
            role, content = getattr(item, "role", None), getattr(item, "content", None)
            metadata = getattr(item, "metadata", None)
        if isinstance(metadata, dict) and metadata.get("title"):
            continue
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    return messages


def _low_confidence_without_laws(results, laws):
    return (not laws and (not results or any(item.get("low_confidence") for item in results)))


def _safe_model_text(value):
    return escape(MARKDOWN_LINK.sub(_unlink, str(value or "")))


def _essay_reply(essay):
    parts = [f"📝 **申論擬答：{_safe_model_text(essay.get('title'))}**"]
    for section in essay.get("sections") or []:
        heading = _safe_model_text(section.get("heading"))
        if heading:
            parts.append(f"**{heading}**")
        # each numbered item is its own line on the answer sheet: keep the breaks, and keep "1." literal
        parts.append(re.sub(r"(?m)^(\d+)([.)])", r"\1\\\2", _safe_model_text(section.get("text")))
                     .replace("\n", "\n\n"))
    layout = essay.get("layout")
    if layout:
        detail = (f"📄 答題紙版面：共 {layout['totalLines']} 行、{layout['pagesUsed']} 頁，"
                  f"尚餘 {layout['remainingLines']} 行。")
        labels = {"pdf": "下載 PDF", "docx": "下載 Word"}
        urls = {}
        for file in essay.get("files") or []:
            if not isinstance(file, dict) or file.get("format") not in labels:
                continue
            url = _public_essay_url(file.get("url"), file["format"])
            url = quote(str(url or ""), safe=":/?#@!$&*+,;=%-._~")
            if _valid_http_url(url):
                urls.setdefault(file["format"], url)
        links = [f"[{labels[format_name]}]({urls[format_name]})"
                 for format_name in ("pdf", "docx") if format_name in urls]
        if links:
            detail += "　" + "　".join(links) + "　（連結 24 小時內有效）"
        parts.append(detail)
    if essay.get("note"):
        parts.append(str(essay["note"]))
    parts.append("⚠️ 擬答由 AI 撰寫，未逐句查證，請對照下方來源；不保證得分。")
    unverified = essay.get("unverified_articles") or []
    if unverified:
        parts.append("下列條號不在本次檢索到的條文中，請自行核對：" + "、".join(
            _safe_model_text(article) for article in unverified
        ) + "。")
    return "\n\n".join(parts)


def _chat_sources(results, laws, web=(), judgments=()):
    if not results and not laws and not web and not judgments:
        return None
    title = f"檢索到的考題與條文（{len(results)} 題、{len(laws)} 條"
    if web:
        title += f"、網路 {len(web)} 筆"
    if judgments:
        title += f"、裁判 {len(judgments)} 筆"
    title += "）"
    pieces = []
    questions = _render_questions(results, include_notice=False, include_numbers=True)
    if results:
        pieces.append(questions)
    statutes = render_laws(laws, include_numbers=True)
    if statutes:
        pieces.append(statutes)
    if web:
        lines = ["## 網路搜尋結果（非官方來源）"]
        for index, item in enumerate(web, 1):
            safe_url = quote(str(item.get("url") or ""), safe=":/?&=%#-._~+;,")
            web_title = _safe_model_text(item.get("title"))
            date = _safe_model_text(item.get("date")).strip()
            snippet = _safe_model_text(item.get("snippet"))
            if date:
                web_title += f"（{date}）"
            # Labels keep untrusted text from starting a line as "## " or "[條n]" (would break/spoof source pop-ups).
            lines.extend(["", f"[網{index}]", "",
                          f"標題：{web_title}", "", f"摘要：{snippet}", "",
                          f"[開啟來源網頁]({safe_url})"])
        pieces.append("  \n".join(lines))
    if judgments:
        lines = ["## 實務見解（法院裁判摘錄）"]
        for index, item in enumerate(judgments, 1):
            judgment_title = _safe_model_text(item.get("title"))
            court = _safe_model_text(item.get("court")).strip()
            date = _safe_model_text(item.get("date")).strip()
            excerpt = _safe_model_text(item.get("excerpt"))
            details = "，".join(value for value in (court, date) if value)
            if details:
                judgment_title += f"（{details}）"
            safe_url = quote(str(item.get("url") or ""), safe=":/?&=%#-._~+;,")
            lines.extend(["", f"[判{index}]", "",
                          f"字號：{judgment_title}", "",
                          f"摘錄：{excerpt}", "",
                          f"[開啟裁判全文]({safe_url})"])
        pieces.append("  \n".join(lines))
    return {"role": "assistant", "content": "\n\n".join(pieces),
            "metadata": {"title": title}}


def _search_turn(question, earlier=None, laws=None):
    found = executor.submit(_search_data, question, laws).result()
    if earlier and _low_confidence_without_laws(*found[:2]):
        retry = executor.submit(_search_data, f"{earlier} {question}", laws).result()
        if not _low_confidence_without_laws(*retry[:2]):
            return retry
    return found


def chat(message, history):
    messages = list(history or [])
    if not message or not message.strip():
        messages.extend([{"role": "user", "content": message or ""},
                         {"role": "assistant", "content": "請輸入問題。"}])
        yield messages, ""
        return
    if len(message) > 2000:
        messages.extend([{"role": "user", "content": message},
                         {"role": "assistant", "content": "問題請勿超過 2,000 字。"}])
        yield messages, ""
        return

    messages.append({"role": "user", "content": message})
    conversation = _history_text(history)
    questions = [item["content"] for item in conversation
                 if item["role"] == "user" and item["content"].strip()
                 and not _SOURCE_REFERENCE.search(item["content"])]
    essay_match = _ESSAY_PREFIX.match(message)
    essay_question = essay_match.group(1).strip() if essay_match else ""
    is_essay = bool(essay_question and essay_enabled())
    if is_essay:
        results, law_results, elapsed_ms, warning = _search_turn(essay_question, laws=ESSAY_LAW_K)
    elif questions and _SOURCE_REFERENCE.search(message):
        # "[題1] 為什麼…" points at the previous turn's sources: repeat that turn's retrieval so the
        # numbers match. shortcut: history beyond the recent window is not replayed; upgrade: keep
        # each turn's results per session.
        asked = _ESSAY_PREFIX.match(questions[-1]) if essay_enabled() else None
        if asked and asked.group(1).strip():
            # An essay turn searched its question alone, without the prefix.
            results, law_results, elapsed_ms, warning = _search_turn(
                asked.group(1).strip(), laws=ESSAY_LAW_K)
        else:
            results, law_results, elapsed_ms, warning = _search_turn(
                questions[-1], questions[-2] if len(questions) > 1 else None)
    else:
        results, law_results, elapsed_ms, warning = _search_turn(
            message, questions[-1] if questions else None)

    progress = {"role": "assistant",
                "content": (f"已完成檢索（{len(results)} 題考題、{len(law_results)} 條條文），"
                            + ("正在撰寫申論擬答並排版…" if is_essay else "正在整理回答…"))}
    messages.append(progress)
    yield list(messages), ""

    answer_result = _cached_chat_answer(
        essay_question if is_essay else message,
        results, law_results, history=conversation,
        use_cache=not conversation and not is_essay,
        generate=generate_essay if is_essay else None,
    )
    if is_essay and answer_result.get("status") == "ok" and not answer_result.get("essay"):
        answer_result = {"status": "error", "reason": "模型回應格式錯誤"}
    if answer_result.get("status") == "ok":
        if is_essay:
            messages[-1] = {"role": "assistant", "content": _essay_reply(answer_result["essay"])}
            low_confidence_without_laws = _low_confidence_without_laws(results, law_results)
            if not low_confidence_without_laws:
                seen = answer_result.get("included") or {
                    "題": len(results), "條": len(law_results)}
                source_message = _chat_sources(
                    results[:seen.get("題", 0)], law_results[:seen.get("條", 0)])
                if source_message:
                    messages.append(source_message)
            yield list(messages), ""
            return
        web = answer_result.get("web") or []
        judgments = answer_result.get("judgments") or []
        parts = []
        if answer_result.get("grounded"):
            parts.append(_safe_model_text(answer_result["grounded"]))
        if any(isinstance(citation, str) and citation.startswith("[網")
               for citation in answer_result.get("citations") or []):
            parts.append("🌐 標示 [網n] 的內容來自網路搜尋摘要，不是官方來源，請點開來源核對。")
        if any(isinstance(citation, str) and citation.startswith("[判")
               for citation in answer_result.get("citations") or []):
            parts.append(
                "⚖️ 標示 [判n] 的內容是裁判書摘錄，可能是當事人的主張而不是法院的見解，也可能已被變更，請點開全文核對。"
            )
        if answer_result.get("supplement"):
            parts.append(
                "⚠️ 以下不是出自題庫或法條，是 AI 依自身知識回答，未經查證；"
                "條號、數字請自行核對。\n\n"
                + _safe_model_text(answer_result["supplement"])
            )
        messages[-1] = {"role": "assistant", "content": "\n\n".join(parts)}
        low_confidence_without_laws = _low_confidence_without_laws(results, law_results)
        if not low_confidence_without_laws or web or judgments:
            # Number only what the model was given, so citation ids match the answer.
            seen = answer_result.get("included") or {"題": len(results), "條": len(law_results)}
            source_results = [] if low_confidence_without_laws else results[:seen.get("題", 0)]
            source_laws = [] if low_confidence_without_laws else law_results[:seen.get("條", 0)]
            source_message = _chat_sources(
                source_results, source_laws, web=web, judgments=judgments)
            if source_message:
                messages.append(source_message)
    else:
        if answer_result.get("status") == "disabled":
            reason = "未設定 AI 金鑰，以下是檢索結果："
        elif answer_result.get("status") == "limited":
            reason = "AI 回答已達本小時上限，以下是檢索結果："
        else:
            detail = answer_result.get("reason") or "模型服務錯誤"
            reason = f"AI 回答暫時無法產生（{escape(str(detail))}），以下是檢索結果："
        messages[-1] = {
            "role": "assistant",
            "content": reason + "\n\n" + _search_output(
                results, law_results, elapsed_ms, warning
            ),
        }
    yield list(messages), ""


def search(query):
    # SQLite connections and the model stay on their single owning thread.
    return executor.submit(run_search, query).result()


def _frontend_html(web):
    src = f"gradio_api/file={web.as_posix()}/index.html"
    if essay_enabled():
        src += "?essay=1"
    return (
        f'<iframe src="{escape(src, quote=True)}" title="警察考古題 AI 助理" '
        'style="position:fixed;inset:0;width:100%;height:100%;border:0;'
        'z-index:1000;background:#fff"></iframe>'
    )


def main():
    import gradio as gr
    executor.submit(initialize, index_path()).result()
    _start_essay_mcp()
    frontend_built = (WEB / "index.html").is_file()
    static_paths = ([WEB] if frontend_built else [])
    if ESSAY_LOCAL is not None:
        static_paths.append(ESSAY_LOCAL[1])
    if static_paths:
        gr.set_static_paths(paths=static_paths)
    with gr.Blocks(title="警察考古題 AI 助理") as demo:
        if frontend_built:
            gr.HTML(_frontend_html(WEB))
        gr.Markdown("# 警察考古題 AI 助理\n"
                    "AI 回答僅供參考，請以考選部公告與現行條文為準。\n\n"
                    "範例問題：警察何時可以查證身分？｜警察職權行使法第 6 條規定什麼？｜"
                    "考古題中的答案和現行法條不同時應如何判斷？", visible=not frontend_built)
        # Hidden, not removed: the /chat API is defined by these components.
        chatbot = gr.Chatbot(type="messages", height=600, visible=not frontend_built)
        with gr.Row(visible=not frontend_built):
            question = gr.Textbox(label="訊息", placeholder="輸入問題或接續追問…",
                                  lines=1, scale=8)
            submit = gr.Button("送出", variant="primary", scale=1)
        # One shared group: up to 30 people wait on the model at once; retrieval stays on `executor`.
        question.submit(chat, inputs=[question, chatbot], outputs=[chatbot, question],
                        api_name="chat", concurrency_limit=30, concurrency_id="chat")
        submit.click(chat, inputs=[question, chatbot], outputs=[chatbot, question],
                     api_name=False, concurrency_limit=30, concurrency_id="chat")
    host = os.environ.get("RAG_HOST", "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1")
    demo.queue(default_concurrency_limit=1).launch(
        server_name=host, server_port=int(os.environ.get("RAG_PORT", "7860")), show_error=True)


if __name__ == "__main__":
    main()
