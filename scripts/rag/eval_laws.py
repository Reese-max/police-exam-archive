#!/usr/bin/env python3
"""Evaluate current-law retrieval against a human-written JSONL set."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3

if __package__:
    from .retrieval import Retriever, add_search_arguments, parse_search_args, search_arguments
else:
    from retrieval import Retriever, add_search_arguments, parse_search_args, search_arguments


ROOT = Path(__file__).resolve().parents[2]


def read_eval_set(path):
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("query"), str) or not row["query"].strip():
            raise ValueError(f"{path}:{line_number} 缺少非空 query")
        gold = row.get("gold")
        if (not isinstance(gold, list) or not gold
                or any(not isinstance(item, dict)
                       or not isinstance(item.get("law"), str)
                       or not isinstance(item.get("article"), str)
                       for item in gold)):
            raise ValueError(f"{path}:{line_number} gold 必須包含 law/article")
        rows.append({"query": row["query"], "gold": gold})
    if not rows:
        raise ValueError(f"評估集不可為空：{path}")
    return rows


def _article_key(value):
    return "".join(str(value).split())


def compute_metrics(rows, rankings):
    if len(rows) != len(rankings):
        raise ValueError("評估資料與檢索結果筆數不符")
    reciprocal_ranks = []
    hit1 = hit5 = 0
    law_totals, law_hits = Counter(), Counter()
    misses = []
    for row, ranking in zip(rows, rankings):
        gold = {(item["law"], _article_key(item["article"])) for item in row["gold"]}
        found_rank = next((rank for rank, item in enumerate(ranking, 1)
                           if (item.get("law_name"), _article_key(item.get("article_no", ""))) in gold), None)
        reciprocal_ranks.append(1 / found_rank if found_rank else 0.0)
        hit1 += found_rank == 1
        hit5 += found_rank is not None and found_rank <= 5
        by_law = {}
        for law_name, article in gold:
            by_law.setdefault(law_name, set()).add(article)
        for law_name, articles in by_law.items():
            law_totals[law_name] += 1
            if any((item.get("law_name"), _article_key(item.get("article_no", "")))
                   in {(law_name, article) for article in articles} for item in ranking[:5]):
                law_hits[law_name] += 1
        if found_rank is None or found_rank > 5:
            misses.append({
                "query": row["query"],
                "gold": row["gold"],
                "top5": [{"law": item.get("law_name"), "article": item.get("article_no")}
                         for item in ranking[:5]],
            })
    count = len(rows)
    return {
        "n": count,
        "R@1": hit1 / count,
        "R@5": hit5 / count,
        "MRR": sum(reciprocal_ranks) / count,
        "per_law_hit_rate": {
            name: {"hits": law_hits[name], "n": law_totals[name],
                   "hit_rate": law_hits[name] / law_totals[name]}
            for name in sorted(law_totals)
        },
        "misses": misses,
    }


def evaluate(rows, db, *, device="cpu", **search_options):
    retriever = Retriever(db, device=device)
    try:
        rankings = [retriever.search_laws(row["query"], k=5, **search_options) for row in rows]
        return compute_metrics(rows, rankings)
    finally:
        retriever.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", type=Path, default=ROOT / "rag/eval_laws.jsonl")
    parser.add_argument("--db", type=Path, default=Path("rag/index.sqlite"))
    parser.add_argument("--out", type=Path, help="評估 JSON 輸出路徑")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    add_search_arguments(parser)
    try:
        args = parse_search_args(parser, argv)
        rows = read_eval_set(args.eval)
        options = search_arguments(args)
        law_options = {key: options[key] for key in (
            "keyword_weight", "vector_weight", "rrf_k", "candidates", "expand_abbreviations"
        )}
        law_options["min_vector_score"] = args.law_min_vector_score
        report = evaluate(rows, args.db, device=args.device, **law_options)
    except (ValueError, RuntimeError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        parser.exit(1, f"法條評估失敗：{exc}\n")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
