#!/usr/bin/env python3
"""Build a deterministic RAG corpus without modifying the exam archive.

Paths in appears_in/sources are subject directories relative to --root, matching
source_map entries. IDs hash normalized type, stem, sorted options and passage.
In-file collisions with differing/missing answers also hash the passage ordinal
(or question number without passage). Answers never enter the hash itself.

Answer votes include missing/free/other values. Ties prefer normal, free, other,
then none, with JSON lexical order as the final tie breaker. Conflicts retain all
raw values and their paths, including null for missing answers. In-file true
duplicates retain all question numbers but cast only one answer vote.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata


HAN = r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]"
PUNCTUATION = str.maketrans(",;:?!()", "，；：？！（）")
CHINESE_PUNCTUATION = re.compile(
    rf"(?<={HAN})\s*[,;:?!()]+|[,;:?!()]+\s*(?={HAN})"
)
RANGE = re.compile(r"(?:第\s*)?(\d+)\s*題?\s*[-–—~～至到]\s*第?\s*(\d+)\s*題?")


def normalize_text(text: str) -> str:
    text = " ".join(unicodedata.normalize("NFC", text).split())
    return CHINESE_PUNCTUATION.sub(
        lambda match: match.group().translate(PUNCTUATION), text
    )


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def question_id(question: dict, passage: str = "", discriminator=None) -> str:
    options = question.get("options", {}) if question["type"] == "choice" else {}
    identity = [
        normalize_text(question["type"]),
        normalize_text(question["stem"]),
        [[key, normalize_text(options[key])] for key in "ABCD" if key in options],
        normalize_text(passage),
    ]
    if discriminator is not None:
        identity.append(discriminator)
    return hashlib.sha1(json_text(identity).encode("utf-8")).hexdigest()[:16]


def passage_group(question: dict):
    for field in ("passage_question_range", "passage_group", "passage_intro"):
        value = question.get(field)
        if value is None or value == "":
            continue
        match = RANGE.search(str(value))
        if match:
            start, end = map(int, match.groups())
            if start <= end:
                return ("range", start, end)
        if field != "passage_intro":
            return ("group", json_text(value))
    return None


def passage_contexts(questions: list[dict]) -> tuple[list[str], list[int]]:
    """Share explicit group context within the same section and question type."""
    groups = defaultdict(list)
    keys = []
    for question in questions:
        scope = (question.get("section"), question["type"])
        key = passage_group(question)
        keys.append((scope, key))
        if key is not None:
            groups[(scope, key)]  # Register ranges even when context is absent.

    memberships = []
    for question, (scope, key) in zip(questions, keys):
        if key is None:
            number = question.get("number")
            matches = [
                group for group_scope, group in groups
                if group_scope == scope and group[0] == "range"
                and isinstance(number, int) and group[1] <= number <= group[2]
            ]
            # Ambiguous overlapping ranges cannot safely supply missing context.
            key = matches[0] if len(matches) == 1 else None
        membership = (scope, key) if key is not None else None
        memberships.append(membership)
        if membership is not None:
            groups[membership].append(question)

    passages, ordinals = [], []
    positions = Counter()
    for question, membership in zip(questions, memberships):
        members = groups[membership] if membership is not None else [question]
        parts = dict.fromkeys(
            member[field].strip()
            for field in ("passage_intro", "passage")
            for member in members if member.get(field, "").strip()
        )
        passage = "\n".join(parts)
        passages.append(passage)
        # Standalone repeated context also identifies a passage group.
        group = membership or (question.get("section"), question["type"], normalize_text(passage))
        positions[group] += 1
        ordinals.append(positions[group])
    return passages, ordinals


def merge_passages(questions: list[dict]) -> list[str]:
    return passage_contexts(questions)[0]


def folder_aliases(paths: list[Path]) -> list[dict]:
    """Conservative spelling aliases only; no fuzzy subject/department guesses."""
    groups = defaultdict(set)
    for path in paths:
        for kind, name in (("category", path.parts[0]), ("subject", path.parts[2])):
            key = unicodedata.normalize("NFKC", name)
            if kind == "category":
                key = key.replace("學系", "")
            groups[(kind, key)].add(name)
    return [
        {"kind": kind, "normalized_name": key, "names": sorted(names)}
        for (kind, key), names in sorted(groups.items()) if len(names) > 1
    ]


def answer_fields(value) -> dict:
    if isinstance(value, str) and value in ("A", "B", "C", "D"):
        return {"answer": value, "answer_status": "normal"}
    if value == "送分":
        return {"answer": None, "answer_status": "free"}
    if value is None or value == "":
        return {"answer": None, "answer_status": "none"}
    return {"answer": None, "answer_status": "other", "answer_raw": value}


def has_pdf_url(record: dict, field: str) -> bool:
    return any(isinstance(source.get(field), str) and source[field].strip()
               for source in record.get("sources", []))


def build_corpus(
    root: Path, source_map: Path, *, issues: dict | None = None,
    answer_overrides: Path | dict | None = None,
) -> tuple[list[dict], dict]:
    root, source_map = Path(root), Path(source_map)
    if not root.is_dir():
        raise ValueError(f"Archive root is not a directory: {root}")
    entries = {}
    if source_map.exists():
        data = json.loads(source_map.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != 1 or not isinstance(data.get("entries"), dict):
            raise ValueError("source map must have schema_version=1 and object entries")
        entries = data["entries"]
    overrides_path = (source_map.parent / "answer_overrides.json" if answer_overrides is None
                      else answer_overrides)
    if isinstance(overrides_path, dict):
        override_data = overrides_path
    elif Path(overrides_path).is_file():
        override_data = json.loads(Path(overrides_path).read_text(encoding="utf-8-sig"))
    else:
        override_data = {}
    overrides = override_data.get("overrides", {})
    unresolved = override_data.get("unresolved", {})

    files = sorted(root.rglob("試題.json"), key=lambda path: path.relative_to(root).as_posix())
    if issues is None:
        issues = {}
    issues.clear()
    issues.update(in_file_duplicates=[], folder_aliases=[])
    disambiguated = 0
    records, votes, contexts = {}, defaultdict(dict), defaultdict(dict)
    raw_types = Counter()
    for file in files:
        relative = file.parent.relative_to(root)
        if len(relative.parts) != 3 or not re.fullmatch(r"\d+年", relative.parts[1]):
            raise ValueError(f"Expected <category>/<year>年/<subject>/試題.json: {file}")
        category, year, subject = relative.parts
        path = relative.as_posix()
        questions = json.loads(file.read_text(encoding="utf-8-sig"))["questions"]
        passages, ordinals = passage_contexts(questions)
        identifiers = [question_id(question, passage) for question, passage in zip(questions, passages)]
        collisions = defaultdict(list)
        for index, identifier in enumerate(identifiers):
            collisions[identifier].append(index)
        duplicate_indices = set()
        for identifier, indices in collisions.items():
            if len(indices) < 2:
                continue
            answers = [questions[index].get("answer") for index in indices]
            if (all(answer is not None and answer != "" for answer in answers)
                    and len({json_text(answer) for answer in answers}) == 1):
                issues["in_file_duplicates"].append({
                    "path": path, "numbers": [questions[index].get("number") for index in indices],
                    "question_id": identifier,
                })
                duplicate_indices.update(indices[1:])
            else:
                disambiguated += 1
                for index in indices:
                    discriminator = (["passage_ordinal", ordinals[index]] if passages[index]
                                     else ["number", questions[index].get("number")])
                    identifiers[index] = question_id(questions[index], passages[index], discriminator)
                if len({identifiers[index] for index in indices}) != len(indices):
                    raise ValueError(f"Cannot distinguish collision with repeated/missing numbers: {path}")
        for index, (question, passage, identifier) in enumerate(zip(questions, passages, identifiers)):
            qtype = question["type"]
            if qtype not in ("choice", "essay") or not isinstance(question["stem"], str):
                raise ValueError(f"Invalid question type/stem: {file}, {question.get('number')}")
            raw_types[qtype] += 1
            if identifier not in records:
                records[identifier] = {
                    "question_id": identifier, "type": qtype, "stem": question["stem"],
                    **({"options": {key: question["options"][key] for key in "ABCD"
                                    if key in question["options"]}} if qtype == "choice" else {}),
                    "appears_in": [],
                }
            records[identifier]["appears_in"].append({
                "path": path, "category": category, "year": int(year[:-1]),
                "subject": subject, "number": question.get("number"),
            })
            if passage:
                contexts[identifier][passage] = None
            # Keep every original question number, but one answer vote per duplicate group.
            if index in duplicate_indices:
                continue
            raw_answer = question.get("answer") if qtype == "choice" else None
            vote = votes[identifier].setdefault(
                json_text(raw_answer), {"value": raw_answer, "paths": []}
            )
            vote["paths"].append(path)

    status_order = {"normal": 0, "free": 1, "other": 2, "none": 3}
    corpus = []
    for identifier, record in sorted(records.items()):
        record["appears_in"].sort(key=lambda item: (
            item["path"], (0, item["number"]) if isinstance(item["number"], int)
            else (1, json_text(item["number"]))
        ))
        answers = sorted(votes[identifier].values(), key=lambda vote: (
            -len(vote["paths"]), status_order[answer_fields(vote["value"])["answer_status"]],
            json_text(vote["value"])
        ))
        record.update(answer_fields(answers[0]["value"]))
        if len(answers) > 1:
            record["answer_conflicts"] = [
                {"value": vote["value"], "paths": sorted(vote["paths"])} for vote in answers
            ]
        record["passage"] = "\n\n".join(contexts[identifier])
        record["sources"] = [
            {"path": path, "question_pdf_url": entries[path].get("question_pdf_url"),
             "answer_pdf_url": entries[path].get("answer_pdf_url")}
            for path in sorted({item["path"] for item in record["appears_in"]}) if path in entries
        ]
        # Normalize content before adding ASCII option labels, keeping (A)... intact.
        record["text"] = " ".join(" ".join([
            normalize_text(record["passage"]), normalize_text(record["stem"]),
            *(f"({key}){normalize_text(value)}"
              for key, value in record.get("options", {}).items()),
        ]).split())
        corpus.append(record)

    applied_overrides = 0
    for record in corpus:
        if record["type"] != "choice":
            continue
        override = overrides.get(record["question_id"])
        if override:
            record["answer_original"] = {
                key: record[key] for key in
                ("answer", "answer_status", "answer_raw", "answer_conflicts") if key in record
            }
            record["answer"] = override.get("answer")
            record["answer_status"] = override.get("answer_status", "normal")
            record["answer_source"] = "moex_official"
            record["answer_correction"] = bool(override.get("answer_correction"))
            record["answer_source_urls"] = override.get("answer_source_urls", [])
            if record["answer_status"] == "multiple":
                record["answer_values"] = override.get("answer_values", [])
            else:
                record.pop("answer_values", None)
            record.pop("answer_conflicts", None)
            applied_overrides += 1
        if record["question_id"] in unresolved:
            item = unresolved[record["question_id"]]
            record["answer_conflicts"] = item.get("answer_conflicts", [])
            record["answer_conflict_reason"] = item.get("reason", "官方答案來源無法唯一對應")

    issues["folder_aliases"] = folder_aliases([file.parent.relative_to(root) for file in files])
    unique_types = Counter(record["type"] for record in corpus)
    statuses = Counter(record["answer_status"] for record in corpus)
    stats = {
        "file_count": len(files), "raw_question_count": sum(raw_types.values()),
        "raw_questions_by_type": {key: raw_types[key] for key in ("choice", "essay")},
        "deduplicated_question_count": len(corpus),
        "deduplicated_questions_by_type": {key: unique_types[key] for key in ("choice", "essay")},
        "answer_status": {key: statuses[key] for key in ("normal", "free", "none", "other", "multiple")},
        "questions_with_sources": sum(bool(record["sources"]) for record in corpus),
        "questions_with_question_pdf_url": sum(has_pdf_url(record, "question_pdf_url") for record in corpus),
        "questions_with_answer_pdf_url": sum(has_pdf_url(record, "answer_pdf_url") for record in corpus),
        "choice_questions_with_question_pdf_url": sum(
            record["type"] == "choice" and has_pdf_url(record, "question_pdf_url") for record in corpus),
        "choice_questions_with_answer_pdf_url": sum(
            record["type"] == "choice" and has_pdf_url(record, "answer_pdf_url") for record in corpus),
        "answer_conflict_count": sum("answer_conflicts" in record for record in corpus),
        "max_duplicate_count": max((len(record["appears_in"]) for record in corpus), default=0),
        "in_file_duplicate_count": len(issues["in_file_duplicates"]),
        "disambiguated_collision_groups": disambiguated,
        "answer_verification": {
            "counts": override_data.get("summary", {}).get("counts", {}),
            "verifiable_question_count": override_data.get("summary", {}).get(
                "verifiable_question_count", 0),
            "correct_rate": override_data.get("summary", {}).get("correct_rate"),
            "overrides_applied": applied_overrides,
            "unresolved_mismatch_count": override_data.get("summary", {}).get(
                "unresolved_mismatch_count", len(unresolved)),
            "unresolved_question_count": override_data.get("summary", {}).get(
                "unresolved_question_count", len(unresolved)),
        },
    }
    return corpus, stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("考古題庫"))
    parser.add_argument("--source-map", type=Path, default=Path("rag/source_map.json"))
    parser.add_argument("--out", type=Path, default=Path("rag/corpus.jsonl"))
    parser.add_argument("--stats", type=Path, default=Path("rag/corpus_stats.json"))
    parser.add_argument("--issues", type=Path, help="Defaults to corpus_issues.json beside --stats")
    args = parser.parse_args(argv)
    issues = {}
    issues_path = args.issues or args.stats.with_name("corpus_issues.json")
    corpus, stats = build_corpus(args.root, args.source_map, issues=issues)
    for path in (args.out, args.stats, issues_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        for record in corpus:
            stream.write(json_text(record) + "\n")
    with args.stats.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    with issues_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(issues, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
