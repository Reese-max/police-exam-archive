#!/usr/bin/env python3
"""Query local exam questions with original citations; no paid API or generator."""

import argparse
import json
from pathlib import Path
import sqlite3

if __package__:
    from .retrieval import Retriever
else:
    from retrieval import Retriever


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
        citations = item.get("citations", [])
        for citation in citations[:3]:
            lines.append(f"出處：{citation.get('category')}／{citation.get('year')}年／"
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
    args = parser.parse_args(argv)
    retriever = None
    try:
        retriever = Retriever(args.db, device=args.device)
        results = retriever.search(args.query, k=args.k, mode=args.mode)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"查詢失敗：{exc}\n")
    finally:
        if retriever is not None:
            retriever.close()
    print(json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2)
          if args.json else format_results(results))


if __name__ == "__main__":
    main()
