#!/usr/bin/env python3
"""Evaluate seeded middle-15-character retrieval; timing includes query encoding."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import time

if __package__:
    from .retrieval import Retriever, normalize_text
else:
    from retrieval import Retriever, normalize_text


def middle_query(stem):
    start = max(0, (len(stem) - 15) // 2)
    return stem[start:start + 15]


def matching_text(text):
    # Corpus normalization depends on neighboring Han characters. Fold punctuation
    # on both sides so an excerpt cut at punctuation keeps the same meaning.
    return normalize_text(text).translate(str.maketrans("，；：？！（）", ",;:?!()"))


def evaluate(corpus, db, *, n=500, seed=0, modes=("keyword", "vector", "hybrid"),
             embedder=None, device="auto"):
    if n <= 0:
        raise ValueError("n 必須大於 0")
    raw = Path(corpus).read_bytes()
    documents = sorted((json.loads(line) for line in raw.decode("utf-8-sig").splitlines()
                        if line.strip()), key=lambda doc: doc["question_id"])
    sample = random.Random(seed).sample(documents, min(n, len(documents)))
    if not sample:
        raise ValueError("Corpus is empty")
    stem_counts = Counter(normalize_text(doc["stem"]) for doc in documents)
    query_counts = Counter(normalize_text(middle_query(doc["stem"])) for doc in documents)
    texts = [matching_text(doc["text"]) for doc in documents]
    # ponytail: scan at most 500 queries over ~10k texts; add an FTS prefilter if corpus growth makes this slow.
    relevance = {query: sum(query in text for text in texts)
                 for query in sorted({matching_text(middle_query(doc["stem"])) for doc in sample})}
    groups = {doc["question_id"]: ("unique" if relevance[matching_text(middle_query(doc["stem"]))] == 1
                                   else "ambiguous" if relevance[matching_text(middle_query(doc["stem"]))] > 1
                                   else None) for doc in sample}
    group_counts = Counter(groups.values())
    retriever = Retriever(db, embedder=embedder, device=device)
    try:
        corpus_hash = hashlib.sha256(raw).hexdigest()
        if corpus_hash != retriever.meta["corpus_sha256"]:
            raise ValueError("Corpus 與索引雜湊不符；請先重跑 build_index.py")
        report = {"n": len(sample), "requested_n": n, "seed": seed,
                  "query_method": "middle contiguous 15 characters of original stem; full stem if shorter",
                  "corpus_sha256": corpus_hash, "model": retriever.meta.get("model"),
                  "definitions": {
                      "matching": "NFC, collapsed whitespace, ASCII/fullwidth ,;:?!() equivalence on query and text; case-sensitive substring, no stemming or fuzzy match",
                      "unique": "Query occurs in exactly one corpus question's full text (including options and passage); strict question_id top1/top5",
                      "ambiguous": "Query occurs in more than one corpus question's full text; relevant_at1/relevant_at5 means at least one result in the first k contains the query; strict question_id scores also retained",
                      "overall": "Original strict question_id top1/top5 over the entire unchanged seeded sample",
                      "reason": "A middle-stem excerpt shared by multiple questions cannot identify one question_id; count containment in full text, not equal middle excerpts",
                      "unresolved": "Zero containing texts are listed separately, never silently dropped from overall metrics; empty-group metrics and unrun acceptance gates are null",
                      "timing": "Mean query latency includes query encoding; initial model/matrix setup is separate; measured timing varies between runs",
                  },
                  "groups": {name: {"n": group_counts[name], "proportion": group_counts[name] / len(sample)}
                             for name in ("unique", "ambiguous")},
                  "unresolved_queries": [{"question_id": doc["question_id"], "query": middle_query(doc["stem"])}
                                         for doc in sample if groups[doc["question_id"]] is None],
                  "targets": {"unique_keyword_top1": 0.95, "unique_hybrid_top1": 0.95,
                              "unique_hybrid_top5": 0.98, "ambiguous_keyword_relevant_at1": 0.95,
                              "ambiguous_hybrid_relevant_at1": 0.95},
                  "corpus_ambiguity": {
                      "question_count": len(documents), "distinct_normalized_queries": len(query_counts),
                      "whole_corpus_deterministic_top1_ceiling": len(query_counts) / len(documents),
                      "note": "Whole-corpus bound from identical normalized queries, not the sampled score.",
                  }, "modes": {}}
        for mode in dict.fromkeys(modes):
            # Load model/matrix once, outside measured steady-state query latency.
            setup_start = time.perf_counter()
            if mode in ("vector", "hybrid") and retriever.vector_ids is None:
                retriever._load_vectors()
            setup_ms = (time.perf_counter() - setup_start) * 1000
            top1 = top5 = 0
            elapsed = 0.0
            misses = []
            grouped_hits = {name: Counter() for name in ("unique", "ambiguous")}
            for doc in sample:
                query = middle_query(doc["stem"])
                match_query = matching_text(query)
                group = groups[doc["question_id"]]
                started = time.perf_counter()
                results = retriever.search(query, k=5, mode=mode)
                elapsed += time.perf_counter() - started
                identifiers = [result["question_id"] for result in results]
                hit1 = bool(identifiers) and identifiers[0] == doc["question_id"]
                hit5 = doc["question_id"] in identifiers
                top1 += hit1
                top5 += hit5
                relevant1 = bool(results) and match_query in matching_text(results[0]["text"])
                relevant5 = any(match_query in matching_text(result["text"]) for result in results)
                if group is not None:
                    grouped_hits[group].update(top1=hit1, top5=hit5,
                                               relevant_at1=relevant1, relevant_at5=relevant5)
                if not hit1:
                    misses.append({"question_id": doc["question_id"], "query": query,
                                   "top5_ids": identifiers, "hit_top5": hit5,
                                   "group": group, "containing_text_count": relevance[match_query],
                                   "relevant_at1": relevant1, "relevant_at5": relevant5,
                                   "same_normalized_stem_count": stem_counts[normalize_text(doc["stem"])],
                                   "same_middle_query_count": query_counts[normalize_text(query)]})
            report["modes"][mode] = {"top1": top1 / len(sample), "top5": top5 / len(sample),
                                     "mean_query_ms": round(elapsed * 1000 / len(sample), 3),
                                     "setup_ms": round(setup_ms, 3), "top1_misses": misses}
            for name, hits in grouped_hits.items():
                keys = ("top1", "top5") if name == "unique" else ("top1", "top5", "relevant_at1", "relevant_at5")
                report["modes"][mode][name] = {
                    key: hits[key] / group_counts[name] if group_counts[name] else None for key in keys}
        report["acceptance"] = {}
        for target, threshold in report["targets"].items():
            group, mode, metric = target.split("_", 2)
            score = report["modes"].get(mode, {}).get(group, {}).get(metric)
            report["acceptance"][target] = score >= threshold if score is not None else None
        return report
    finally:
        retriever.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--corpus", type=Path, default=Path("rag/corpus.jsonl"))
    parser.add_argument("--db", type=Path, default=Path("rag/index.sqlite"))
    parser.add_argument("--modes", nargs="+", choices=("keyword", "vector", "hybrid"),
                        default=["keyword", "vector", "hybrid"])
    parser.add_argument("--out", type=Path, default=Path("rag/eval_report.json"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.corpus, args.db, n=args.n, seed=args.seed, modes=args.modes, device=args.device)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"評估失敗：{exc}\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({mode: {key: value for key, value in scores.items() if key != "top1_misses"}
                      for mode, scores in report["modes"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
