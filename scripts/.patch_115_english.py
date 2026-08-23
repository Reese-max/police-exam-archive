#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把全 115 年英文黏字與誤併閱讀文章修補加入主修復器。"""

from pathlib import Path

path = Path("scripts/remediate_115_audit.py")
text = path.read_text(encoding="utf-8")
marker = "def patch_115_english_spacing_and_passages() -> None:"

if marker not in text:
    anchor = "\ndef canonical_path_for("
    if anchor not in text:
        raise SystemExit("cannot locate canonical_path_for insertion point")

    insertion = r'''

ENGLISH_TOKEN_RE = re.compile(r"[A-Za-z]{12,}")
EMBEDDED_PASSAGE_RE = re.compile(
    r"\s*請依下文回答第\s*(\d{1,3})\s*題至第\s*(\d{1,3})\s*題\s*(.+)$",
    re.DOTALL,
)


def repair_english_spacing(value: str) -> str:
    """以保守的語言模型分詞修復 PDF 抽取造成的英文黏字。"""
    import wordninja

    common = {
        "a", "an", "and", "as", "at", "before", "by", "for", "from",
        "how", "in", "into", "is", "it", "of", "on", "or", "that", "the",
        "their", "this", "to", "was", "were", "what", "when", "which",
        "who", "why", "with", "without",
    }

    def replace(match: re.Match[str]) -> str:
        original = match.group(0)
        if sum(char.isupper() for char in original) > 1:
            return original
        lower = original.lower()
        parts = wordninja.split(lower)
        if len(parts) < 2 or "".join(parts) != lower:
            return original
        if any(len(part) == 1 and part not in {"a", "i", "s"} for part in parts):
            return original
        if len(original) < 18 and len(parts) < 3 and not common.intersection(parts):
            return original

        if (
            match.start() > 0
            and match.string[match.start() - 1] in {"'", "’"}
            and parts[0] == "s"
        ):
            return "s" + (" " + " ".join(parts[1:]) if len(parts) > 1 else "")

        joined = " ".join(parts)
        if original[0].isupper():
            joined = joined[0].upper() + joined[1:]
        return joined

    previous = None
    current = value
    for _ in range(3):
        if current == previous:
            break
        previous = current
        current = ENGLISH_TOKEN_RE.sub(replace, current)
    current = re.sub(r"[ \t]{2,}", " ", current)
    return current.strip()


def patch_115_english_spacing_and_passages() -> None:
    """修復所有 115 年英文長黏字，並把誤併入選項的閱讀文章回填題組。"""
    paths = sorted(DATA_DIR.glob("*/115年/*/試題.json"))
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        questions = payload.get("questions")
        if not isinstance(questions, list):
            continue
        by_number = {
            q.get("number"): q
            for q in questions
            if isinstance(q, dict) and isinstance(q.get("number"), int)
        }
        changed = False

        for question in questions:
            if not isinstance(question, dict):
                continue
            candidates: list[tuple[str, str | None, str]] = []
            stem = question.get("stem")
            if isinstance(stem, str):
                candidates.append(("stem", None, stem))
            options = question.get("options")
            if isinstance(options, dict):
                for label, option in list(options.items()):
                    if isinstance(option, str):
                        candidates.append(("option", str(label), option))

            for kind, label, value in candidates:
                match = EMBEDDED_PASSAGE_RE.search(value)
                if not match:
                    continue
                start = int(match.group(1))
                end = int(match.group(2))
                if start > end or any(number not in by_number for number in range(start, end + 1)):
                    raise RuntimeError(f"題組範圍無法對應：{path} {start}-{end}")
                prefix = value[:match.start()].rstrip(" -、；;:")
                passage = repair_english_spacing(match.group(3))
                if not prefix or not passage:
                    raise RuntimeError(f"題組抽離結果為空：{path} {start}-{end}")
                if kind == "stem":
                    question["stem"] = prefix
                else:
                    assert isinstance(question.get("options"), dict) and label is not None
                    question["options"][label] = prefix
                for number in range(start, end + 1):
                    target = by_number[number]
                    if target.get("passage") != passage:
                        target["passage"] = passage
                changed = True

        for question in questions:
            if not isinstance(question, dict):
                continue
            for field in ("stem", "passage"):
                value = question.get(field)
                if isinstance(value, str):
                    repaired = repair_english_spacing(value)
                    if repaired != value:
                        question[field] = repaired
                        changed = True
            options = question.get("options")
            if isinstance(options, dict):
                for label, value in list(options.items()):
                    if not isinstance(value, str):
                        continue
                    repaired = repair_english_spacing(value)
                    if repaired != value:
                        options[label] = repaired
                        changed = True

        leftovers: list[tuple[object, str]] = []
        for question in questions:
            if not isinstance(question, dict):
                continue
            values = [question.get("stem"), question.get("passage")]
            options = question.get("options")
            if isinstance(options, dict):
                values.extend(options.values())
            for value in values:
                if not isinstance(value, str):
                    continue
                found = re.search(r"\b[a-z]{25,}\b", value)
                if found:
                    leftovers.append((question.get("number"), found.group(0)))
        if leftovers:
            raise RuntimeError(f"仍有英文長黏字：{path}：{leftovers[:20]}")
        if changed:
            write_json(path, payload)
'''
    text = text.replace(anchor, insertion + anchor, 1)

call = "\n    patch_common_english()\n"
extended_call = call + "    patch_115_english_spacing_and_passages()\n"
if "    patch_115_english_spacing_and_passages()\n" not in text:
    if call not in text:
        raise SystemExit("cannot locate patch_common_english call")
    text = text.replace(call, extended_call, 1)

path.write_text(text, encoding="utf-8")
