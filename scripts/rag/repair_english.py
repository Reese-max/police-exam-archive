"""Conservative glued-English repair; default is a report-only dry run.

Reuse the OCR repairer's wordninja model, inserting ASCII spaces only. JSON
string literals are patched in place so indentation, line endings, key order,
and every non-target byte survive. Uncertain candidates stay in the report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import json
from math import log
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.parse import ocr_repair


LETTERS = re.compile(r"[A-Za-z]{8,}")
JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
# Protect whole lexical constructs, not just their individual letter runs.
PROTECTED = re.compile(
    r"```[\s\S]*?(?:```|$)|`[^`\n]*(?:`|$)"
    r"|\$[^$\n]*(?:\$|$)|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]"
    r"|(?<![A-Za-z0-9])(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)[^\s<>\"，。；]+"
    r"|(?<![A-Za-z0-9_.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+"
    r"|(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+"
    r"|(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*\([^()\n]*\)"
    r"|(?<![A-Za-z0-9_])(?=[A-Za-z0-9_]*[A-Za-z])(?=[A-Za-z0-9_]*[0-9_])[A-Za-z0-9_]+"
    r"|(?<!\S)\S*[=+*/\\^{}<>|~@#]\S*"
)
FUNCTION_WORDS = frozenset(
    "the of to for in on at and is are was were be been being with from that "
    "this these those which when where who what why how not but than then "
    "they their them you your we our it its have has had do does did will "
    "would should could can must into onto about between during because "
    "while before after through without within until unless whether".split()
)
SHORT_WORDS = FUNCTION_WORDS | {"a", "i", "an", "as", "or", "by", "he", "so", "if", "no", "us", "up"}
COMMON_THREE = SHORT_WORDS | set(
    "all any boy day end few get got law let lot low man may men new now old one "
    "out own put run saw say see set she too try two use war way yet yes".split()
)
CONTEXT_WORDS = frozenset(
    "the and that this these those which when where who what why how their them "
    "you your our with from have has had would should could will must because "
    "while without between is are was were for".split()
)
OTHER_LANGUAGE = re.compile(r"(?:印尼|西班牙|葡萄牙|法|德|越南|泰|韓|俄|日)文")
WHITELIST = {word.casefold() for word in ocr_repair.WHITELIST_TOKENS} | {"ai", "ocg", "ocgs"}
RULES = [
    "Candidates are ASCII letter runs of at least 8 letters absent from the wordninja dictionary.",
    "Keep dictionary words and existing whitespace; never resegment a spaced phrase.",
    "Protect URLs, emails, dotted names, paths, backticks/fences, math, calls, digits/underscores and operator-bearing tokens.",
    "Keep whitelist acronyms, all-uppercase tokens and tokens with noninitial uppercase letters (including chemical formulae/identifiers).",
    "Require a grammatical function word at an edge, or inside a run of at least 16 letters; allow only common short pieces and dictionary rank <= 20000.",
    "Require an English-only subject or 3 distinct English context words in the question; otherwise require a run >= 24 letters with 2 English context words in its proposal.",
    "Only insert ASCII spaces; preserve the exact original letters, case, punctuation and non-ASCII text.",
    "Every proposed component must be dictionary-known, making the output a fixed point.",
]


@lru_cache(maxsize=32768)
def split_candidate(token: str) -> tuple[str, str | None]:
    """Return (replacement, rejection reason); never replace original letters."""
    model = ocr_repair.wordninja.DEFAULT_LANGUAGE_MODEL
    if token.casefold() in WHITELIST or token.isupper():
        return token, "abbreviation"
    if any(char.isupper() for char in token[1:]):
        return token, "mixed_case_identifier_or_formula"
    # Existing OCR code only repairs fragmented words: provide that representation
    # to reuse its splitter, then restore case by slicing the original token.
    proposal = ocr_repair.repair_english_spacing(" ".join(token))
    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)+", proposal):
        return token, "no_split"
    parts = proposal.split(" ")
    if "".join(parts).casefold() != token.casefold():
        return token, "letter_sequence_changed"
    lowered = [part.lower() for part in parts]
    if any(len(part) <= 2 and part not in SHORT_WORDS for part in lowered):
        return token, "uncertain_short_piece"
    if any(len(part) == 3 and part not in COMMON_THREE for part in lowered):
        return token, "uncertain_short_piece"
    # The model's cost is monotonic in dictionary rank; bound rare names/fragments.
    costs = model._wordcost
    max_cost = log(20000 * log(len(costs)))
    if any(part not in costs or costs[part] > max_cost for part in lowered):
        return token, "rare_or_unknown_piece"
    if not (lowered[0] in FUNCTION_WORDS or lowered[-1] in FUNCTION_WORDS
            or (len(token) >= 16 and FUNCTION_WORDS.intersection(lowered))):
        return token, "ambiguous_word_or_compound"
    offset = 0
    restored = []
    for part in parts:
        restored.append(token[offset:offset + len(part)])
        offset += len(part)
    result = " ".join(restored)
    if result.replace(" ", "") != token:
        return token, "letter_sequence_changed"
    return result, None


def repair_text(text: str, english_context: bool = True) -> tuple[str, list[dict], list[dict]]:
    if not ocr_repair.is_available():
        raise RuntimeError("wordninja is required; add its installed site-packages to PYTHONPATH")
    costs = ocr_repair.wordninja.DEFAULT_LANGUAGE_MODEL._wordcost
    protected = [match.span() for match in PROTECTED.finditer(text)]
    changes, skipped = [], []

    def replace(match: re.Match) -> str:
        token = match.group()
        if token.lower() in costs and token.casefold() not in WHITELIST:
            return token
        if any(start < match.end() and match.start() < end for start, end in protected):
            after, reason = token, "protected_construct"
        else:
            after, reason = split_candidate(token)
            if reason is None and not english_context:
                if len(token) < 24 or len(CONTEXT_WORDS.intersection(after.lower().split())) < 2:
                    after, reason = token, "insufficient_english_context"
        entry = {"start": match.start(), "end": match.end(), "before": token}
        if reason:
            skipped.append({**entry, "reason": reason})
        else:
            changes.append({**entry, "after": after})
        return after

    return LETTERS.sub(replace, text), changes, skipped


def has_english_context(subject: str, texts: list[str]) -> bool:
    if "英文" in subject and not OTHER_LANGUAGE.search(subject):
        return True
    # Preview context-independent long repairs so context cannot change on rerun.
    words = {word.lower() for text in texts
             for word in re.findall(r"[A-Za-z]+", repair_text(text, False)[0])}
    return len(words & CONTEXT_WORDS) >= 3


def string_values(value, path=()):
    """Yield JSON keys and string values in lexical order, with value paths."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield None, key
            yield from string_values(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from string_values(child, path + (index,))
    elif isinstance(value, str):
        yield path, value


def patch_json(text: str, data: dict, replacements: dict) -> str:
    """Replace selected string literals, leaving all surrounding bytes intact."""
    spans = iter(JSON_STRING.finditer(text))
    chunks, end = [], 0
    for path, value in string_values(data):
        match = next(spans)
        if json.loads(match.group()) != value:
            raise ValueError("JSON string traversal mismatch; refusing to write")
        if path in replacements:
            chunks.extend((text[end:match.start()], json.dumps(replacements[path], ensure_ascii=False)))
            end = match.end()
    if next(spans, None) is not None:
        raise ValueError("Unexpected JSON string; refusing to write")
    return "".join(chunks) + text[end:]


def scan(root: Path, apply: bool = False) -> dict:
    if not root.is_dir():
        raise ValueError(f"Root directory does not exist: {root}")
    if not ocr_repair.is_available():
        raise RuntimeError("wordninja is required; add its installed site-packages to PYTHONPATH")
    files = sorted(root.rglob("試題.json"), key=lambda p: p.relative_to(root).as_posix())
    changes, skipped = [], []
    question_count = modified_files = repairs_count = 0
    for file in files:
        raw = file.read_bytes()
        text = raw.decode("utf-8-sig")
        data = json.loads(text)
        replacements = {}
        for index, question in enumerate(data.get("questions", [])):
            question_count += 1
            fields = [(field, ("questions", index, field), question.get(field))
                      for field in ("stem", "passage", "passage_intro")]
            fields.extend((f"options.{key}", ("questions", index, "options", key), value)
                          for key, value in question.get("options", {}).items())
            english_context = has_english_context(file.parent.name,
                                                 [value for _, _, value in fields if isinstance(value, str)])
            for field, key, before in fields:
                if not isinstance(before, str):
                    continue
                after, repairs, rejected = repair_text(before, bool(english_context))
                context = {"path": (Path(root.name) / file.relative_to(root)).as_posix(),
                           "question_index": index, "question_number": question.get("number"), "field": field}
                skipped.extend({**context, **item} for item in rejected)
                if repairs:
                    replacements[key] = after
                    repairs_count += len(repairs)
                    changes.append({**context, "before": before, "after": after, "repairs": repairs})
        if replacements:
            modified_files += 1
            updated = patch_json(text, data, replacements)
            if updated.replace(" ", "") != text.replace(" ", ""):
                raise ValueError(f"Noncanonical JSON escapes in {file}; refusing to reformat")
            if apply:
                bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
                file.write_bytes(bom + updated.encode("utf-8"))
    return {
        "mode": "apply" if apply else "dry-run",
        "wordninja_version": ocr_repair.wordninja.__version__,
        "rules": RULES,
        "summary": {"scanned_files": len(files), "scanned_questions": question_count,
                    "detected_candidates": repairs_count + len(skipped),
                    "proposed_modifications": repairs_count,
                    "actual_modifications": repairs_count if apply else 0,
                    "modified_fields": len(changes), "modified_files": modified_files,
                    "skipped": len(skipped),
                    "skip_reasons": dict(sorted(Counter(item["reason"] for item in skipped).items()))},
        "changes": changes,
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("考古題庫"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="reports/english_repair_report.json", help="JSON report path, or - for stdout")
    args = parser.parse_args()
    try:
        report = scan(args.root, args.apply)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report == "-":
        print(serialized, end="")
    else:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(serialized.encode("utf-8"))
        print(json.dumps({"mode": report["mode"], **report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
