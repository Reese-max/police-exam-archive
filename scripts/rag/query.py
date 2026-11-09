#!/usr/bin/env python3
"""Query local exam questions with original citations; no paid API or generator."""

import argparse
import json
from pathlib import Path
import sqlite3

if __package__:
    from .retrieval import Retriever, add_search_arguments, search_arguments, parse_search_args, load_reranker
else:
    from retrieval import Retriever, add_search_arguments, search_arguments, parse_search_args, load_reranker


def group_citations(citations):
    groups = {}
    for citation in citations:
        # Unknown URLs are not evidence of a shared PDF.
        key = citation.get("question_pdf_url") or (citation.get("path"), citation.get("number"))
        groups.setdefault(key, []).append(citation)
    return list(groups.values())


def format_results(results):
    lines = []
    for item in results:
        lines.append(f"{item['rank']}. {item['question_id']} [{item.get('type')}]")
        lines.append("題幹：" + " ".join(item.get("stem", "").split())[:120])
        if item.get("answer") is not None:
            lines.append(f"答案：{item['answer']}")
        elif item.get("answer_status") == "free":
            lines.append("答案：送分")
        if item.get("answer_conflicts"):
            lines.append("注意：原始答案存在歧異，詳見 --json 的 answer_conflicts")
        citations = group_citations(item.get("citations", []))
        for group in citations[:3]:
            citation = group[0]
            categories = "、".join(sorted({str(c.get('category')) for c in group}))
            lines.append(f"出處：{categories}／{citation.get('year')}年／"
                         f"{citation.get('subject')}／第{citation.get('number')}題")
            lines.append("試題 PDF：" + (citation.get("question_pdf_url") or "未解析"))
        if len(citations) > 3:
            lines.append(f"另有 {len(citations) - 3} 筆出處（完整內容見 --json）")
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
