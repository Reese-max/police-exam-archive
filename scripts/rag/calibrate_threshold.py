#!/usr/bin/env python3
"""Calibrate the hybrid low-confidence cosine threshold from labeled queries."""

import argparse
import json
import math
from pathlib import Path
import sqlite3
import sys

if __package__:
    from .retrieval import Retriever, add_search_arguments, parse_search_args, search_arguments
else:
    from retrieval import Retriever, add_search_arguments, parse_search_args, search_arguments


ROOT = Path(__file__).resolve().parents[2]


def read_queries(path):
    queries = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        query = record.get("query") if isinstance(record, dict) else None
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{path}:{line_number} 缺少非空 query")
        queries.append(query)
    if not queries:
        raise ValueError(f"查詢集不可為空：{path}")
    return queries


def measure_queries(retriever, queries, options):
    measurements = []
    for query in queries:
        results = retriever.search(query, k=1, mode="hybrid", **options)
        if not results or results[0].get("top1_vector_score") is None:
            raise ValueError(f"檢索沒有向量分數：{query}")
        measurements.append({
            "score": float(results[0]["top1_vector_score"]),
            "keyword_phrase_hit": bool(results[0]["keyword_phrase_hit"]),
        })
    return measurements


def is_low_confidence(measurement, threshold):
    return (measurement["score"] < threshold and not measurement["keyword_phrase_hit"])


def threshold_candidates(measurements):
    thresholds = {round(step / 20, 2) for step in range(-20, 21)}
    scores = sorted({row["score"] for row in measurements
                     if math.isfinite(row["score"]) and -1 <= row["score"] <= 1})
    thresholds.update((lower + upper) / 2 for lower, upper in zip(scores, scores[1:]))
    return sorted(thresholds)


def calibration_rows(related, offtopic):
    rows = []
    for threshold in threshold_candidates([*related, *offtopic]):
        related_false = sum(is_low_confidence(row, threshold) for row in related) / len(related)
        offtopic_detected = sum(is_low_confidence(row, threshold) for row in offtopic) / len(offtopic)
        rows.append({
            "threshold": threshold,
            "related_false_low_rate": related_false,
            "offtopic_detected_rate": offtopic_detected,
        })
    return rows


def recommend_threshold(rows, *, max_related_false_rate=0.02):
    eligible = [row for row in rows if row["related_false_low_rate"] <= max_related_false_rate]
    if not eligible:
        return None
    return min(eligible, key=lambda row: (
        -row["offtopic_detected_rate"], row["related_false_low_rate"], row["threshold"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("rag/index.sqlite"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument("--mode", choices=("hybrid", "keyword", "vector"), default="hybrid")
    parser.add_argument("--semantic", type=Path, default=ROOT / "rag/eval_semantic.jsonl")
    parser.add_argument("--offtopic", type=Path, default=ROOT / "rag/eval_offtopic.jsonl")
    add_search_arguments(parser)
    retriever = None
    try:
        args = parse_search_args(parser, argv)
        if args.mode != "hybrid":
            raise ValueError("門檻校準只支援 hybrid 檢索")
        related_queries = read_queries(args.semantic)
        offtopic_queries = read_queries(args.offtopic)
        retriever = Retriever(args.db, device=args.device)
        options = search_arguments(args)
        options["min_vector_score"] = None
        related = measure_queries(retriever, related_queries, options)
        offtopic = measure_queries(retriever, offtopic_queries, options)
        rows = calibration_rows(related, offtopic)
        recommendation = recommend_threshold(rows)
    except (ValueError, RuntimeError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        parser.exit(1, f"校準失敗：{exc}\n")
    finally:
        if retriever is not None:
            retriever.close()

    print("| 門檻 | 相關查詢誤標低信心 | 無關查詢正確標出 |")
    print("|---:|---:|---:|")
    for row in rows:
        print(f"| {row['threshold']:.17g} | {row['related_false_low_rate']:.1%} "
              f"| {row['offtopic_detected_rate']:.1%} |")
    if recommendation is None:
        print("建議門檻：無（找不到符合相關查詢誤標低信心 ≤2% 的候選門檻）")
    else:
        print(f"建議門檻：{recommendation['threshold']:.17g} "
              f"（相關查詢誤標 {recommendation['related_false_low_rate']:.1%}；"
              f"無關查詢標出 {recommendation['offtopic_detected_rate']:.1%}）")


if __name__ == "__main__":
    main()
