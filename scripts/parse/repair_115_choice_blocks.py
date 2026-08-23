#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修復 115 年 PDF 中「題號直接接選項」的克漏字／閱讀題。

考選部英文克漏字的排版會同時出現：
- 文章中的空格編號，例如 ``53 and taken ...``
- 後方獨立選項列，例如 ``53 (A) dismissed ... (D) discharged``

舊解析器可能把文章內的編號誤認為題目起點，造成 51–55 題缺漏或選項
不完整。本工具直接從官方 PDF 的獨立選項列重建題目，並把共同文章放入
``passage`` 欄位；同時可修復其他具有相同排版的缺選項題目。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.parse import patterns as P  # noqa: E402
from scripts.parse.answer_extractor import parse_answer_pdf  # noqa: E402

EXPECTED_LABELS = {"A", "B", "C", "D"}
OPTION_MARKER = re.compile(r"\(([A-D])\)")
OPTION_ONLY_START = re.compile(
    r"(?m)^[ \t]*(\d{1,3})[ \t]*(?:\r?\n[ \t]*)?(?=\(A\))"
)
PASSAGE_HEADING = re.compile(
    r"請依下文回答第\s*(\d{1,3})\s*題至第\s*(\d{1,3})\s*題"
)
STOP_AFTER_LAST_OPTION = re.compile(
    r"\n\s*(?:"
    r"請依下文回答|"
    r"代號\s*[:：]|頁次\s*[:：]|"
    r"\d{5}(?:\s*[-、,]\s*\d{5})*\s*$|"
    r"\d{1,3}\s+(?:What|Which|How|Why|Who|Where|When|According|The|In|Under|As)\b"
    r")",
    re.MULTILINE,
)


def extract_pdf_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as document:
        text = "\n".join(page.get_text("text") for page in document)
    return P.replace_pua_chars(text).replace("\r\n", "\n")


def clean_option(value: str, *, last: bool = False) -> str:
    value = value.strip()
    if last:
        value = STOP_AFTER_LAST_OPTION.split(value, maxsplit=1)[0]
    value = re.sub(r"\s+", " ", value).strip(" ;；")
    return value


def parse_option_block(block: str) -> dict[str, str] | None:
    markers = list(OPTION_MARKER.finditer(block))
    if [m.group(1) for m in markers[:4]] != ["A", "B", "C", "D"]:
        return None

    options: "OrderedDict[str, str]" = OrderedDict()
    for index, marker in enumerate(markers[:4]):
        label = marker.group(1)
        end = markers[index + 1].start() if index + 1 < 4 else len(block)
        value = clean_option(
            block[marker.end():end],
            last=(label == "D"),
        )
        if not value:
            return None
        options[label] = value

    if set(options) != EXPECTED_LABELS:
        return None
    return dict(options)


def extract_option_candidates(text: str) -> tuple[dict[int, dict[str, str]], dict[int, int]]:
    starts = list(OPTION_ONLY_START.finditer(text))
    candidates: dict[int, dict[str, str]] = {}
    positions: dict[int, int] = {}

    for index, start in enumerate(starts):
        number = int(start.group(1))
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        options = parse_option_block(text[start.end():end])
        if not options:
            continue

        # 同一題若被 PDF 頁首／重複版面擷取多次，保留文字總長較短者，
        # 避免最後一個 D 選項意外夾帶後續頁面內容。
        old = candidates.get(number)
        if old is None or sum(map(len, options.values())) < sum(map(len, old.values())):
            candidates[number] = options
            positions[number] = start.start()

    return candidates, positions


def clean_passage(raw: str, start: int, end: int) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if PASSAGE_HEADING.search(line):
            continue
        if P.is_header_line(line) or P.is_note_line(line):
            continue
        if re.fullmatch(r"\d{5}(?:\s*[-、,]\s*\d{5})*", line):
            continue
        lines.append(line)

    passage = re.sub(r"\s+", " ", " ".join(lines)).strip()
    for number in range(start, end + 1):
        passage = re.sub(
            rf"(?<!\d)\b{number}\b(?!\d)",
            f"____({number})____",
            passage,
        )
    return passage


def extract_cloze_passages(
    text: str,
    option_positions: dict[int, int],
) -> list[tuple[int, int, str]]:
    headings = list(PASSAGE_HEADING.finditer(text))
    results: list[tuple[int, int, str]] = []

    for index, heading in enumerate(headings):
        start = int(heading.group(1))
        end = int(heading.group(2))
        first_option = option_positions.get(start)
        if first_option is None or first_option <= heading.end():
            continue
        block_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        if first_option >= block_end:
            continue
        if not all(number in option_positions for number in range(start, end + 1)):
            continue
        passage = clean_passage(text[heading.end():first_option], start, end)
        if passage:
            results.append((start, end, passage))

    return results


def normalize_answer(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", "", str(value).upper())
    if text in EXPECTED_LABELS or text == "送分":
        return text
    letters = [letter for letter in "ABCD" if letter in text]
    if letters:
        return "或".join(letters)
    return None


def repair_json(json_path: Path) -> dict[str, Any]:
    pdf_path = json_path.with_suffix(".pdf")
    answer_path = json_path.parent / "答案.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"缺少試題 PDF：{pdf_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError(f"questions 非陣列：{json_path}")

    text = extract_pdf_text(pdf_path)
    option_candidates, option_positions = extract_option_candidates(text)
    cloze_ranges = extract_cloze_passages(text, option_positions)

    answers: dict[int, str] = {}
    if answer_path.exists():
        answers = {
            int(number): normalized
            for number, value in parse_answer_pdf(answer_path).items()
            if (normalized := normalize_answer(value)) is not None
        }

    essay_questions = [q for q in questions if q.get("type") != "choice"]
    choices: dict[int, dict[str, Any]] = {}
    duplicate_numbers: set[int] = set()
    for question in questions:
        if question.get("type") != "choice":
            continue
        try:
            number = int(question.get("number"))
        except (TypeError, ValueError):
            continue
        if number in choices:
            duplicate_numbers.add(number)
        choices[number] = question

    repaired_numbers: set[int] = set()
    section = next(
        (q.get("section") for q in choices.values() if q.get("section")),
        "乙、測驗題",
    )

    # 克漏字區塊直接以 PDF 的獨立選項列重建，排除文章內空格編號被
    # 誤判為題號所造成的重複、缺題與錯誤題幹。
    for start, end, passage in cloze_ranges:
        for number in range(start, end + 1):
            options = option_candidates.get(number)
            if not options:
                raise RuntimeError(f"{json_path} 第 {number} 題找不到完整選項列")
            rebuilt: dict[str, Any] = {
                "number": number,
                "type": "choice",
                "stem": f"請依上文選出第 {number} 題空格最適當的答案。",
                "options": options,
                "section": section,
                "passage": passage,
            }
            answer = answers.get(number)
            if answer:
                rebuilt["answer"] = answer
            choices[number] = rebuilt
            repaired_numbers.add(number)

    # 其他題目只在選項不完整時以 PDF 的 canonical option-only block 修復。
    for number, question in list(choices.items()):
        current_options = question.get("options")
        current_labels = set(current_options) if isinstance(current_options, dict) else set()
        if current_labels == EXPECTED_LABELS:
            continue
        options = option_candidates.get(number)
        if options:
            question["options"] = options
            answer = answers.get(number)
            if answer:
                question["answer"] = answer
            repaired_numbers.add(number)

    # 有官方測驗答案的題號必須全部存在，且 A–D 四個選項完整。
    missing: list[int] = []
    incomplete: list[int] = []
    for number in sorted(answers):
        question = choices.get(number)
        if question is None:
            missing.append(number)
            continue
        options = question.get("options")
        if not isinstance(options, dict) or set(options) != EXPECTED_LABELS:
            incomplete.append(number)
            continue
        question["answer"] = answers[number]

    if missing or incomplete:
        raise RuntimeError(
            f"{json_path} 修復後仍有問題：缺題={missing}，選項不完整={incomplete}；"
            f"可用獨立選項列={sorted(option_candidates)}"
        )

    payload["questions"] = essay_questions + [choices[n] for n in sorted(choices)]
    if answers:
        payload["_answers_merged"] = len(answers)
        payload["_answer_source"] = answer_path.name
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "path": json_path.as_posix(),
        "answers": len(answers),
        "choice_questions": len(choices),
        "cloze_ranges": [[start, end] for start, end, _ in cloze_ranges],
        "repaired_numbers": sorted(repaired_numbers),
        "duplicates_removed": sorted(duplicate_numbers),
    }


def run(root: Path) -> dict[str, Any]:
    json_files = sorted(root.glob("*/115年/*/試題.json"))
    if not json_files:
        raise RuntimeError(f"找不到 115 年試題 JSON：{root}")

    reports: list[dict[str, Any]] = []
    for json_path in json_files:
        report = repair_json(json_path)
        reports.append(report)
        if report["repaired_numbers"] or report["duplicates_removed"]:
            print(
                f"修復 {report['path']}："
                f"題號={report['repaired_numbers']}，"
                f"移除重複={report['duplicates_removed']}，"
                f"克漏區間={report['cloze_ranges']}"
            )

    summary = {
        "files": len(reports),
        "files_repaired": sum(
            bool(r["repaired_numbers"] or r["duplicates_removed"]) for r in reports
        ),
        "questions_repaired": sum(len(r["repaired_numbers"]) for r in reports),
        "reports": reports,
    }
    print(
        f"完成選項區塊修復：{summary['files']} 份 JSON，"
        f"{summary['files_repaired']} 份有變更，"
        f"共修復 {summary['questions_repaired']} 題"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="修復 115 年克漏字與缺選項題目")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("考古題庫"),
        help="考古題庫根目錄",
    )
    args = parser.parse_args()
    try:
        run(args.root)
    except Exception as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
