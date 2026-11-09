#!/usr/bin/env python3
"""Query local exam questions with original citations; no paid API or generator."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs, quote, urlsplit

if __package__:
    from .retrieval import (LEGACY_EMBEDDING_TEXT_VERSION, LEGACY_INDEX_WARNING, Retriever, add_search_arguments,
                            embedding_text_version, search_arguments, parse_search_args, load_reranker)
else:
    from retrieval import (LEGACY_EMBEDDING_TEXT_VERSION, LEGACY_INDEX_WARNING, Retriever, add_search_arguments,
                           embedding_text_version, search_arguments, parse_search_args, load_reranker)

MOEX_CORRECTION_INFO_URL = "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx"


def _is_official_exam_pdf(url, *, file_type=None):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        return False
    return (parsed.scheme == "https" and parsed.netloc == "wwwq.moex.gov.tw"
            and parsed.path == "/exam/wHandExamQandA_File.ashx"
            and (file_type is None or parse_qs(parsed.query, keep_blank_values=True).get("t") == [file_type]))


def _one_line(value):
    return " ".join(str(value).split())


def group_citations(citations):
    groups = {}
    for index, citation in enumerate(citations):
        # Unknown URLs are not evidence of a shared PDF.
        url = citation.get("question_pdf_url")
        if isinstance(url, str) and url:
            key = ("url", url)
        else:
            key = ("source", citation.get("path"), citation.get("number"))
            try:
                hash(key)
            except TypeError:
                key = ("unresolved", index)
        groups.setdefault(key, []).append(citation)
    return list(groups.values())


def format_results(results):
    lines = []
    for item in results:
        lines.append(f"{_one_line(item['rank'])}. {_one_line(item['question_id'])} [{_one_line(item.get('type'))}]")
        lines.append("題幹：" + " ".join(item.get("stem", "").split())[:120])
        if item.get("answer_conflicts"):
            lines.append("答案：待核實")
            reason = item.get(
                "answer_conflict_reason",
                "原始答案存在歧異，請核對官方答案及更正公告，詳見 --json 的 answer_conflicts",
            )
            lines.append("注意：" + _one_line(reason))
            lines.append("更正查詢：" + MOEX_CORRECTION_INFO_URL)
        elif item.get("answer_source") == "moex_official":
            label = "官方更正" if item.get("answer_correction") else "考選部官方"
            if item.get("answer_status") == "multiple":
                accepted = " 或 ".join(_one_line(value) for value in item.get("answer_values", []))
                lines.append(f"答案：{accepted} 均給分（{label}）")
            elif item.get("answer_status") == "free":
                lines.append(f"答案：一律給分（{label}）")
            elif item.get("answer") is not None:
                lines.append(f"答案：{_one_line(item['answer'])}（{label}）")
            answer_urls = item.get("answer_source_urls", [])
            preferred = next((url for url in answer_urls
                              if _is_official_exam_pdf(url, file_type="M")), None)
            preferred = preferred or next((url for url in answer_urls
                                           if _is_official_exam_pdf(url, file_type="S")), None)
            if preferred:
                lines.append("考選部答案 PDF：" + quote(preferred, safe=":/?&=%#-._~+;,"))
        elif item.get("answer") is not None:
            lines.append(f"答案：{_one_line(item['answer'])}")
        elif item.get("answer_status") == "free":
            lines.append("答案：送分")
        citations = group_citations(item.get("citations", []))
        visible = citations[:3]
        if item.get("answer_conflicts"):
            visible += [group for group in citations[3:]
                        if any(_is_official_exam_pdf(c.get("answer_pdf_url"), file_type="S") for c in group)]
        for group in visible:
            citation = group[0]
            categories = "、".join(sorted({_one_line(c.get('category')) for c in group}))
            label = "（來源資料夾題號，請核對官方試卷）" if item.get("answer_conflicts") else ""
            lines.append(f"出處：{categories}／{_one_line(citation.get('year'))}年／"
                         f"{_one_line(citation.get('subject'))}／第{_one_line(citation.get('number'))}題{label}")
            question_url = citation.get("question_pdf_url")
            question_display = ("未解析" if not isinstance(question_url, str) or not question_url else "非考選部試題"
                                if item.get("answer_conflicts") and not _is_official_exam_pdf(question_url, file_type="Q")
                                else quote(question_url, safe=":/?&=%#-._~+;,"))
            lines.append("試題 PDF：" + question_display)
            if item.get("answer_conflicts"):
                answer_urls = list(dict.fromkeys(c.get("answer_pdf_url") for c in group
                                                 if isinstance(c.get("answer_pdf_url"), str) and c.get("answer_pdf_url")))
                if any(c.get("answer_pdf_url") is not None and not isinstance(c.get("answer_pdf_url"), str) for c in group):
                    answer_urls.append(None)
                for url in answer_urls or [None]:
                    safe_url = ("未解析" if url is None else quote(url, safe=":/?&=%#-._~+;,")
                                if _is_official_exam_pdf(url, file_type="S") else "非考選部原始答案")
                    lines.append("原始答案 PDF：" + safe_url)
        if len(citations) > len(visible):
            lines.append(f"另有 {len(citations) - len(visible)} 筆出處（完整內容見 --json）")
        lines.append("")
    return "\n".join(lines).rstrip() if results else "查無符合題目。"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--db", type=Path, default=Path("rag/index.sqlite"))
    parser.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    add_search_arguments(parser)
    retriever = None
    try:
        args = parse_search_args(parser, argv)
        retriever = Retriever(args.db, device=args.device)
        if args.mode != "keyword" and embedding_text_version(retriever.meta) == LEGACY_EMBEDDING_TEXT_VERSION:
            print(LEGACY_INDEX_WARNING, file=sys.stderr)
        options = search_arguments(args)
        if getattr(args, "use_reranker", False):
            options["reranker"] = load_reranker(args.device)
        results = retriever.search(args.query, k=args.k, mode=args.mode, **options)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"查詢失敗：{exc}\n")
    finally:
        if retriever is not None:
            retriever.close()
    print(json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2)
          if args.json else format_results(results))


if __name__ == "__main__":
    main()
