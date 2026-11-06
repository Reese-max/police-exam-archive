#!/usr/bin/env python3
"""CPU semantic quality/latency comparison; never builds or overwrites indexes."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3
import statistics
import time

if __package__:
    from .check_eval_set import check_records, load_documents, read_jsonl
    from .retrieval import DEFAULT_MODEL, Retriever, load_reranker
else:
    from check_eval_set import check_records, load_documents, read_jsonl
    from retrieval import DEFAULT_MODEL, Retriever, load_reranker


def configurations(weights=(1.0, 2.0, 4.0), constants=(20, 60), rerank=False):
    configs = [{"name": "keyword", "mode": "keyword", "phrase_priority": False},
               {"name": "vector", "mode": "vector"},
               {"name": "hybrid_old_equal", "mode": "hybrid", "keyword_weight": 1.0,
                "vector_weight": 1.0, "rrf_k": 60, "phrase_priority": False}]
    for weight in weights:
        for constant in constants:
            for expand in (False, True):
                configs.append({"name": f"hybrid_w{weight:g}_k{constant}" + ("_expanded" if expand else ""),
                                "mode": "hybrid", "keyword_weight": weight, "vector_weight": 1.0,
                                "rrf_k": constant, "phrase_priority": True, "expand_abbreviations": expand})
    configs.append({"name": "keyword_expanded", "mode": "keyword", "expand_abbreviations": True})
    if rerank:
        configs.extend([{**config, "name": config["name"] + "_reranked", "use_reranker": True}
                        for config in list(configs) if config["name"].endswith("_expanded") and config["mode"] == "hybrid"])
    return configs


def percentile(values, fraction):
    # Nearest rank, including tails for small samples.
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def measure(retriever, records, config, *, warmup=3, repeats=1, reranker=None):
    options = {key: value for key, value in config.items() if key not in ("name", "use_reranker")}
    if config.get("use_reranker"):
        if reranker is None:
            raise ValueError("Missing reranker")
        options["reranker"] = reranker
    for index in range(warmup):
        retriever.search(records[index % len(records)]["query"], k=10, **options)
    recalls = {k: 0.0 for k in (1, 5, 10)}
    reciprocal, latencies = 0.0, []
    for row in records:
        results = None
        for _ in range(repeats):
            started = time.perf_counter()
            results = retriever.search(row["query"], k=10, **options)
            latencies.append((time.perf_counter() - started) * 1000)
        identifiers = [result["question_id"] for result in results]
        relevant = set(row["relevant_question_ids"])
        for k in recalls:
            recalls[k] += len(set(identifiers[:k]) & relevant) / len(relevant)
        reciprocal += next((1 / rank for rank, qid in enumerate(identifiers, 1) if qid in relevant), 0)
    return {**{f"recall@{k}": value / len(records) for k, value in recalls.items()},
            "mrr": reciprocal / len(records), "p50_ms": round(statistics.median(latencies), 3),
            "p95_ms": round(percentile(latencies, .95), 3), "queries": len(records),
            "timed_queries": len(latencies), "warmup_queries": warmup}


def choose_default(rows, *, device="cpu", complete=True):
    if not complete or device != "cpu":
        return None
    baselines = [row["metrics"]["recall@5"] for row in rows if row.get("metrics") and row["configuration"]["name"] == "keyword"]
    if not baselines:
        return None
    eligible = [row for row in rows if row.get("metrics") and row["metrics"]["p95_ms"] <= 500
                and row["metrics"]["recall@5"] > max(baselines)]
    if not eligible:
        return None
    return min(eligible, key=lambda row: (-row["metrics"]["recall@5"], -row["metrics"]["mrr"],
                row["metrics"]["p95_ms"], row["model"], row["configuration"]["name"]))


def markdown_report(report):
    lines = ["| Model | Combination | R@1 | R@5 | R@10 | MRR | CPU p50 ms | CPU p95 ms | Status |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in report["results"]:
        metrics = row.get("metrics")
        values = ([f"{metrics[key]:.3f}" for key in ("recall@1", "recall@5", "recall@10", "mrr", "p50_ms", "p95_ms")]
                  if metrics else ["—"] * 6)
        lines.append("| " + " | ".join([row["model"], row["configuration"]["name"], *values,
                                      row.get("error", "measured").replace("|", "/").replace("\n", " ")]) + " |")
    lines += ["", "Selection: " + report["selection_reason"]]
    return "\n".join(lines)


def run_benchmark(indexes, records, configs, *, device="cpu", warmup=3, repeats=1,
                  embedder_factory=None, reranker=None, corpus_hash=None):
    if not records or warmup < 1 or repeats < 1:
        raise ValueError("Nonempty evaluation set and positive warmup/repeats required")
    paths = [Path(db).resolve() for model, db in indexes]
    if len(paths) != len(set(paths)):
        raise ValueError("Each model requires a different --db/index path")
    rows = []
    for model, db in indexes:
        retriever, error, vector_error = None, None, None
        try:
            retriever = Retriever(db, device=device, embedder_factory=embedder_factory)
            if corpus_hash and retriever.meta.get("corpus_sha256") != corpus_hash:
                raise ValueError("Corpus 與索引雜湊不符")
            if retriever.meta.get("model") not in (model, None):
                raise ValueError("Index model does not match requested model")
        except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
            error = str(exc)
        try:
            for config in configs:
                row = {"model": model, "db": Path(db).as_posix(), "configuration": config, "metrics": None}
                if not error and config["mode"] != "keyword" and vector_error is None and retriever.vector_ids is None:
                    try:
                        retriever._load_vectors()
                    except (ValueError, RuntimeError, OSError, ImportError, sqlite3.Error) as exc:
                        vector_error = str(exc)
                row_error = error or (vector_error if config["mode"] != "keyword" else None)
                if row_error:
                    row["error"] = row_error
                else:
                    try:
                        row["metrics"] = measure(retriever, records, config, warmup=warmup,
                                                 repeats=repeats, reranker=reranker)
                    except (ValueError, RuntimeError, OSError, ImportError, sqlite3.Error) as exc:
                        row["error"] = str(exc)
                rows.append(row)
                print(f"{model} {config['name']}: {row.get('error', row['metrics'])}", flush=True)
        finally:
            if retriever:
                retriever.close()
    complete = all(row.get("metrics") for row in rows)
    winner = choose_default(rows, device=device, complete=complete)
    return {"status": "measured" if complete else "incomplete", "device": device,
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "processor": platform.processor()},
            "definitions": {"recall": "macro mean of |top-k intersect labeled relevant| / |labeled relevant|; sparse judgments, unjudged results are not certified irrelevant",
                            "mrr": "first labeled relevant rank reciprocal, truncated at 10",
                            "timing": "sequential single-query wall time including encoding, fusion, optional top-20 reranking and JSON/citations; excludes setup, warmup and index build",
                            "selection": "full supplied evaluation set; exploratory selection, no held-out generalization claim"},
            "results": rows, "selected_default": winner,
            "selection_reason": ("Highest Recall@5 above keyword with CPU p95 <= 500ms; ties: MRR, p95, model/name."
                                 if winner else "No selection: incomplete comparison, non-CPU run, or no combination beats keyword within CPU p95 <= 500ms.")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="append", metavar="MODEL=DB", help="Repeat for each model; indexes are read-only")
    parser.add_argument("--eval-set", type=Path, default=Path("rag/eval_semantic.jsonl"))
    parser.add_argument("--corpus", type=Path, default=Path("rag/corpus.jsonl"))
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--keyword-only", action="store_true")
    parser.add_argument("--weights", nargs="+", type=float, default=[1, 2, 4])
    parser.add_argument("--rrf-constants", nargs="+", type=int, default=[20, 60])
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--reranker", action="store_true", help="Optional BAAI/bge-reranker-v2-m3; only top 20")
    parser.add_argument("--out", type=Path, default=Path("rag/bench_report.json"))
    args = parser.parse_args(argv)
    try:
        records = read_jsonl(args.eval_set)
        checked = check_records(records, load_documents(args.corpus))
        if checked["errors"]:
            raise ValueError("; ".join(checked["errors"]))
        indexes = [(value.split("=", 1)[0], Path(value.split("=", 1)[1])) for value in args.index or
                   [DEFAULT_MODEL + "=rag/index-e5.sqlite", "BAAI/bge-m3=rag/index-bge-m3.sqlite"]]
        reranker = None
        if args.reranker:
            reranker = load_reranker(args.device)
        configs = configurations(args.weights, args.rrf_constants, args.reranker)
        if args.keyword_only:
            configs = [config for config in configs if config["mode"] == "keyword"]
        corpus_hash = hashlib.sha256(args.corpus.read_bytes()).hexdigest() if args.corpus.is_file() else None
        report = run_benchmark(indexes, records, configs, device=args.device, warmup=args.warmup,
                               repeats=args.repeats, reranker=reranker, corpus_hash=corpus_hash)
        report["eval_set_sha256"] = hashlib.sha256(args.eval_set.read_bytes()).hexdigest()
        report["coverage"] = checked
        if args.keyword_only or not {DEFAULT_MODEL, "BAAI/bge-m3"} <= {model for model, db in indexes}:
            report.update(selected_default=None, selection_reason="No selection: required two-model comparison not executed.")
        args.out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(markdown_report(report))
        return 0 if report["status"] == "measured" else 1
    except (ValueError, IndexError, RuntimeError, OSError, ImportError, sqlite3.Error) as exc:
        parser.exit(1, f"Benchmark failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
