#!/usr/bin/env python3
"""Validate semantic labels/coverage and reject any shared four-character span."""

import argparse
from collections import Counter
import json
from pathlib import Path
import unicodedata

if __package__:
    from .build_corpus import build_corpus
    from .retrieval import load_abbreviations
else:
    from build_corpus import build_corpus
    from retrieval import load_abbreviations


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_documents(corpus=Path("rag/corpus.jsonl"), root=Path("考古題庫")):
    # Read-only fallback: checking the committed set must not require generated files.
    return read_jsonl(corpus) if Path(corpus).is_file() else build_corpus(Path(root), Path("rag/source_map.json"))[0]


def comparison_text(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                   if not c.isspace() and not unicodedata.category(c).startswith(("P", "Z")))


def shared_four(query, doc):
    query = comparison_text(query)
    spans = {query[i:i + 4] for i in range(len(query) - 3)}
    for text in [doc.get("stem", ""), *doc.get("options", {}).values()]:
        text = comparison_text(text)
        overlap = spans & {text[i:i + 4] for i in range(len(text) - 3)}
        if overlap:
            return sorted(overlap)[0]
    return None


def check_records(records, documents, *, min_queries=150, min_subjects=15,
                  abbreviation_range=(0.15, 0.25), abbreviations=None,
                  require_types=("choice", "essay")):
    docs = {doc["question_id"]: doc for doc in documents}
    aliases = load_abbreviations() if abbreviations is None else abbreviations
    errors, subjects, types, queries = [], set(), Counter(), set()
    abbreviated = 0
    for number, row in enumerate(records, 1):
        query, relevant, rationale = row.get("query"), row.get("relevant_question_ids"), row.get("rationale")
        if not isinstance(query, str) or not query.strip() or len(comparison_text(query)) < 4:
            errors.append(f"line {number}: query must contain at least four characters")
            continue
        if comparison_text(query) in queries:
            errors.append(f"line {number}: duplicate query")
        queries.add(comparison_text(query))
        abbreviated += any(alias in query for alias in aliases)
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(f"line {number}: missing rationale")
        if not isinstance(relevant, list) or not relevant or any(not isinstance(qid, str) for qid in relevant):
            errors.append(f"line {number}: relevant_question_ids must be a nonempty string list")
            continue
        if len(relevant) != len(set(relevant)):
            errors.append(f"line {number}: duplicate relevant ID")
        for qid in relevant:
            if qid not in docs:
                errors.append(f"line {number}: unknown ID {qid}")
                continue
            doc = docs[qid]
            overlap = shared_four(query, doc)
            if overlap:
                errors.append(f"line {number}: {qid} shared four-character span {overlap!r}")
            subjects.update(item["subject"] for item in doc.get("appears_in", []) if item.get("subject"))
            types[doc["type"]] += 1
    ratio = abbreviated / len(records) if records else 0
    if len(records) < min_queries:
        errors.append(f"need >= {min_queries} queries, got {len(records)}")
    if len(subjects) < min_subjects:
        errors.append(f"need >= {min_subjects} subjects, got {len(subjects)}")
    if not set(require_types) <= types.keys():
        errors.append(f"need question types {sorted(require_types)}")
    if not abbreviation_range[0] <= ratio <= abbreviation_range[1]:
        errors.append(f"abbreviation ratio {ratio:.3f} outside {abbreviation_range}")
    return {"queries": len(records), "subjects": sorted(subjects), "types": dict(sorted(types.items())),
            "abbreviated_queries": abbreviated, "abbreviation_ratio": ratio, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", type=Path, default=Path("rag/eval_semantic.jsonl"))
    parser.add_argument("--corpus", type=Path, default=Path("rag/corpus.jsonl"))
    parser.add_argument("--root", type=Path, default=Path("考古題庫"))
    parser.add_argument("--min-queries", type=int, default=150)
    parser.add_argument("--min-subjects", type=int, default=15)
    parser.add_argument("--require-types", nargs="+", default=["choice", "essay"],
                        choices=["choice", "essay"])
    args = parser.parse_args(argv)
    report = check_records(read_jsonl(args.eval_set), load_documents(args.corpus, args.root),
                           min_queries=args.min_queries, min_subjects=args.min_subjects,
                           require_types=tuple(args.require_types))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
