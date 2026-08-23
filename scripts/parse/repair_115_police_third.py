#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修復 115 年警察人員三等考試 PDF 解析邊界案例。

本腳本只處理 ``考古題庫/*/115年/*/試題.json``，並在 GitHub Actions
下載官方 PDF、執行既有 parser 後運行。主要工作：

* 同時比較 pdfplumber、PyMuPDF、欄位版與 layout 版解析結果；
* 依官方答案題數重建選擇題 1..N 的連續題號；
* 合併被 PDF 換頁誤切成額外題號的選項（例如 40、800）；
* 補救英文克漏字中內嵌於段落的第 51～55 題；
* 以官方答案 PDF 覆寫答案，並套用 4 份官方更正答案；
* 清理頁首頁尾、PUA 私用字及英文連字。
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from scripts.parse import patterns as P  # noqa: E402
from scripts.parse.answer_extractor import parse_answer_pdf  # noqa: E402
from scripts.parse.pdf_to_questions import _try_parse, parse_questions  # noqa: E402

DATA_ROOT = ROOT / "考古題庫"
OFFICIAL_PAGE = (
    "https://wwwq.moex.gov.tw/exam/"
    "wFrmExamQandASearch.aspx?e=115060&y=2026"
)

ALLOWED_LABELS = ("A", "B", "C", "D")
OPTION_MARKER_RE = re.compile(r"[(（]\s*([A-Da-d])\s*[)）]")
QUESTION_LINE_RE = re.compile(r"^\s*(\d{1,3})\s+(.*)$")
PUA_RE = re.compile(r"[\ue000-\uf8ff]")
CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z][a-z]{2,})")

# 以考選部 115060「測驗式試題標準答案更正清冊」為準。
# # 所在題號再由 overrides 指定「多答案／送分」的精確語意。
SPECIAL_ANSWER_SEQUENCES: tuple[dict[str, Any], ...] = (
    {
        "category": "行政警察學系",
        "subject": "警察政策與犯罪預防",
        "sequence": "BCB#BADDBDCABCABDDCACDBBD",
        "overrides": {4: ["A", "C"]},
        "notes": {4: "考選部更正：A 或 C 均給分"},
    },
    {
        "category": "刑事警察學系",
        "subject": "犯罪偵查學",
        "sequence": "BBDCDACACDABDBACDABCDCB#D",
        "overrides": {24: "送分"},
        "notes": {24: "考選部更正：本題一律給分"},
    },
    {
        "category": "刑事警察學系",
        "subject": "刑案現場處理與刑事鑑識",
        "sequence": "BDBBB#AAACCBABCCDACDAADCC",
        "overrides": {6: ["A", "C", "D"]},
        "notes": {6: "考選部更正：A、C 或 D 均給分"},
    },
    {
        "category": "水上警察學系",
        "subject": "海巡法規",
        "sequence": "ACDCBAABBCDDDBDBDCDACD#A#",
        "overrides": {23: "B", 25: "送分"},
        "notes": {
            23: "考選部更正：本題答案為 B",
            25: "考選部更正：本題一律給分",
        },
    },
)


def _matches_subject(actual: str, expected: str) -> bool:
    return actual == expected or actual.startswith(expected) or expected.startswith(actual)


def _special_answer_spec(category: str, subject: str) -> dict[str, Any] | None:
    for spec in SPECIAL_ANSWER_SEQUENCES:
        if spec["category"] == category and _matches_subject(subject, spec["subject"]):
            return spec
    return None


def _special_answers(spec: dict[str, Any]) -> dict[int, Any]:
    sequence = re.sub(r"\s+", "", spec["sequence"])
    answers: dict[int, Any] = {}
    for number, token in enumerate(sequence, start=1):
        if token in ALLOWED_LABELS:
            answers[number] = token
        elif token == "#":
            answers[number] = "送分"
        else:
            raise ValueError(f"未知官方答案 token: {token!r}")
    answers.update(spec.get("overrides", {}))
    return answers


def load_official_answers(category: str, subject: str, subject_dir: Path) -> tuple[dict[int, Any], str, dict[int, str]]:
    spec = _special_answer_spec(category, subject)
    if spec:
        return (
            _special_answers(spec),
            "考選部標準答案更正清冊",
            dict(spec.get("notes", {})),
        )

    corrected = subject_dir / "更正答案.pdf"
    regular = subject_dir / "答案.pdf"
    source = corrected if corrected.exists() else regular
    if not source.exists():
        return {}, "", {}
    answers = parse_answer_pdf(source)
    return answers, source.name, {}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = P.replace_pua_chars(str(value))
    text = PUA_RE.sub("", text)
    text = text.replace("\u00a0", " ")

    # 移除跨頁時混入題幹／選項的固定頁首頁尾。
    text = re.sub(
        r"115年公務人員特種考試警察人員、一般警察人員、\s*"
        r"國家安全局國家安全情報人員及移民行政人員考試試題",
        " ",
        text,
    )
    text = re.sub(r"代號[:：]\s*\d{4,6}", " ", text)
    text = re.sub(r"頁次[:：]\s*\d+\s*[－\-]\s*\d+", " ", text)
    text = re.sub(r"乙、測驗題(?:部分)?[:：]?\s*(?:（\d+\s*分）)?", " ", text)
    text = re.sub(r"(?<![A-Za-z])[-－]\s*、", " ", text)

    # 修正典型 PDF 英文黏字（例如 bankrecords、ZeroTrust 仍需保留語意）。
    text = CAMEL_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip(" \n-、")


def clean_question(question: dict[str, Any]) -> dict[str, Any]:
    q = copy.deepcopy(question)
    q["stem"] = clean_text(q.get("stem"))
    if q.get("passage") is not None:
        q["passage"] = clean_text(q.get("passage"))
    if isinstance(q.get("options"), dict):
        q["options"] = {
            str(label).upper(): clean_text(value)
            for label, value in q["options"].items()
            if str(label).upper() in ALLOWED_LABELS
        }
    return q


def question_score(question: dict[str, Any]) -> float:
    q = clean_question(question)
    stem = q.get("stem", "")
    options = q.get("options") or {}
    score = min(len(stem), 200) / 20.0
    if stem:
        score += 5
    if set(options) == set(ALLOWED_LABELS):
        score += 50
    score += sum(8 for label in ALLOWED_LABELS if options.get(label))
    if re.search(r"乙、測驗|代號[:：]\s*\d{4}", stem):
        score -= 20
    if PUA_RE.search(json.dumps(q, ensure_ascii=False)):
        score -= 20
    return score


def parse_inline_numbered_text(text: str, expected_count: int) -> list[dict[str, Any]]:
    """從保留版面的純文字補抓「題號 + (A)..(D)」題目。"""
    text = P.replace_pua_chars(text)
    lines = [line.rstrip() for line in text.splitlines()]
    starts: list[tuple[int, int, str]] = []
    in_choice_section = False

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if "乙、測驗題" in line:
            in_choice_section = True
        if not in_choice_section and "共" not in line:
            continue
        match = QUESTION_LINE_RE.match(line)
        if not match:
            continue
        number = int(match.group(1))
        if 1 <= number <= expected_count:
            starts.append((index, number, match.group(2)))

    parsed: list[dict[str, Any]] = []
    for position, (line_index, number, first_line) in enumerate(starts):
        next_index = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        block = " ".join([first_line, *lines[line_index + 1:next_index]])
        markers = list(OPTION_MARKER_RE.finditer(block))
        labels = [marker.group(1).upper() for marker in markers]
        if not all(label in labels for label in ALLOWED_LABELS):
            continue

        # 使用第一組按 A→B→C→D 排列的標記，忽略段落中其他括號字母。
        selected = []
        cursor = 0
        for label in ALLOWED_LABELS:
            found = None
            for marker in markers[cursor:]:
                if marker.group(1).upper() == label:
                    found = marker
                    cursor = markers.index(marker) + 1
                    break
            if found is None:
                selected = []
                break
            selected.append(found)
        if len(selected) != 4:
            continue

        stem = clean_text(block[: selected[0].start()])
        options: dict[str, str] = {}
        for idx, marker in enumerate(selected):
            start = marker.end()
            end = selected[idx + 1].start() if idx + 1 < len(selected) else len(block)
            options[ALLOWED_LABELS[idx]] = clean_text(block[start:end])

        # 克漏字題的題幹本來只有空格編號，明確標示其用途。
        if not stem:
            stem = f"請依題組內容選出第 {number} 空最適答案。"
        parsed.append(
            {
                "number": number,
                "type": "choice",
                "stem": stem,
                "section": "乙、測驗題",
                "options": options,
            }
        )
    return parsed


def collect_candidates(pdf_path: Path, existing: dict[str, Any]) -> list[list[dict[str, Any]]]:
    candidate_lists: list[list[dict[str, Any]]] = []
    existing_questions = existing.get("questions") or []
    if existing_questions:
        candidate_lists.append(copy.deepcopy(existing_questions))

    for extractor in ("pdfplumber", "pymupdf", "pymupdf-columns"):
        result, _used_ocr, _error = _try_parse(
            pdf_path,
            extractor,
            enable_ocr=False,
        )
        if result and result.get("questions"):
            candidate_lists.append(result["questions"])

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            variants: list[list[str]] = []
            variants.append([(page.extract_text() or "") for page in pdf.pages])
            variants.append([
                (page.extract_text(layout=True, x_tolerance=2, y_tolerance=3) or "")
                for page in pdf.pages
            ])
            for pages_text in variants:
                result = parse_questions(pages_text)
                if result.get("questions"):
                    candidate_lists.append(result["questions"])
    except Exception as exc:
        print(f"WARN 無法建立 layout 候選 {pdf_path}: {exc}")

    return candidate_lists


def merge_complementary_options(
    base: dict[str, Any],
    number: int,
    candidate_lists: Iterable[list[dict[str, Any]]],
    expected_count: int,
) -> dict[str, Any]:
    result = clean_question(base)
    merged_options = dict(result.get("options") or {})

    for questions in candidate_lists:
        choice_questions = [q for q in questions if q.get("type") == "choice"]
        for index, raw in enumerate(choice_questions):
            if raw.get("number") != number:
                continue
            candidate = clean_question(raw)
            if question_score(candidate) > question_score(result):
                result = candidate
            merged_options.update(
                {k: v for k, v in (candidate.get("options") or {}).items() if v}
            )

            # PDF 換頁有時把同題後半選項誤判為 40、800 等額外題號。
            if index + 1 < len(choice_questions):
                following = clean_question(choice_questions[index + 1])
                following_number = following.get("number")
                following_options = following.get("options") or {}
                if (
                    isinstance(following_number, int)
                    and following_number > expected_count
                    and set(following_options) - set(merged_options)
                ):
                    merged_options.update(
                        {k: v for k, v in following_options.items() if v}
                    )

    if merged_options:
        result["options"] = merged_options
    result["number"] = number
    result["type"] = "choice"
    result["section"] = result.get("section") or "乙、測驗題"
    return clean_question(result)


def rebuild_choices(
    pdf_path: Path,
    existing: dict[str, Any],
    expected_count: int,
) -> tuple[list[dict[str, Any]], list[int]]:
    candidate_lists = collect_candidates(pdf_path, existing)

    # 額外從保留版面的全文抓取內嵌題目（特別是英文第 51～55 題）。
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for layout in (False, True):
                full_text = "\n".join(
                    page.extract_text(layout=layout, x_tolerance=2, y_tolerance=3) or ""
                    for page in pdf.pages
                )
                inline = parse_inline_numbered_text(full_text, expected_count)
                if inline:
                    candidate_lists.append(inline)
    except Exception as exc:
        print(f"WARN 內嵌題目補抓失敗 {pdf_path}: {exc}")

    # 若某個完整候選剛好有 N 題，依實際出現順序重編 1..N，修正 PDF
    # 中把正文數字誤認成題號造成的缺號。
    complete_sequences: list[list[dict[str, Any]]] = []
    for questions in candidate_lists:
        choices = [clean_question(q) for q in questions if q.get("type") == "choice"]
        if len(choices) == expected_count:
            sequence = []
            for number, question in enumerate(choices, start=1):
                question["number"] = number
                sequence.append(question)
            complete_sequences.append(sequence)

    per_number: dict[int, list[dict[str, Any]]] = {
        number: [] for number in range(1, expected_count + 1)
    }
    for questions in candidate_lists:
        for raw in questions:
            if raw.get("type") != "choice":
                continue
            number = raw.get("number")
            if isinstance(number, int) and 1 <= number <= expected_count:
                per_number[number].append(clean_question(raw))
    for sequence in complete_sequences:
        for question in sequence:
            per_number[question["number"]].append(question)

    rebuilt: list[dict[str, Any]] = []
    missing: list[int] = []
    for number in range(1, expected_count + 1):
        candidates = per_number[number]
        if not candidates:
            missing.append(number)
            continue
        best = max(candidates, key=question_score)
        best = merge_complementary_options(
            best,
            number,
            candidate_lists,
            expected_count,
        )
        rebuilt.append(best)
    return rebuilt, missing


def repair_file(json_path: Path) -> dict[str, Any]:
    subject_dir = json_path.parent
    year_dir = subject_dir.parent
    category_dir = year_dir.parent
    category = category_dir.name
    subject = subject_dir.name
    pdf_path = subject_dir / "試題.pdf"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    official_answers, answer_source, answer_notes = load_official_answers(
        category,
        subject,
        subject_dir,
    )

    original_questions = payload.get("questions") or []
    essays = [clean_question(q) for q in original_questions if q.get("type") == "essay"]

    missing: list[int] = []
    if official_answers:
        expected_count = max(official_answers)
        choices, missing = rebuild_choices(pdf_path, payload, expected_count)
        by_number = {q["number"]: q for q in choices}
        for number in range(1, expected_count + 1):
            question = by_number.get(number)
            if not question:
                continue
            question["answer"] = official_answers.get(number, "送分")
            if number in answer_notes:
                question["_answer_note"] = answer_notes[number]

            options = question.get("options") or {}
            if len(set(options.values())) < len(options):
                question["_note"] = (
                    "官方試題或 PDF 文字抽取呈現重複選項；已保留原文供核對"
                )
        questions = essays + [by_number[n] for n in sorted(by_number)]
    else:
        questions = [clean_question(q) for q in original_questions]

    # 最後一層結構修正與診斷。
    invalid_options: list[int] = []
    invalid_answers: list[int] = []
    for question in questions:
        if question.get("type") != "choice":
            continue
        number = question.get("number")
        options = question.get("options") or {}
        if set(options) != set(ALLOWED_LABELS) or any(not options[k] for k in ALLOWED_LABELS):
            invalid_options.append(number)
        answer = question.get("answer")
        valid_answer = (
            answer in ALLOWED_LABELS
            or answer == "送分"
            or (
                isinstance(answer, list)
                and answer
                and all(item in ALLOWED_LABELS for item in answer)
            )
        )
        if not valid_answer:
            invalid_answers.append(number)

    payload["questions"] = questions
    payload["year"] = 115
    payload["category"] = category
    payload["subject"] = subject
    payload["source_pdf"] = str(pdf_path.relative_to(ROOT))
    payload["file_type"] = "試題"
    payload["_official_source"] = OFFICIAL_PAGE
    if official_answers:
        payload["_answer_source"] = answer_source
        payload["_answers_merged"] = len(official_answers) - len(missing)
    payload["_quality"] = {
        "score": 1.0 if not (missing or invalid_options or invalid_answers) else 0.5,
        "issues": [
            *(f"missing_questions:{missing}" for _ in [0] if missing),
            *(f"invalid_options:{invalid_options}" for _ in [0] if invalid_options),
            *(f"invalid_answers:{invalid_answers}" for _ in [0] if invalid_answers),
        ],
        "strategies_tried": [
            "pdfplumber",
            "pymupdf",
            "pymupdf-columns",
            "pdfplumber-layout",
            "inline-numbered-repair",
        ],
    }

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "path": str(json_path.relative_to(ROOT)),
        "questions": len(questions),
        "choice": sum(q.get("type") == "choice" for q in questions),
        "essay": sum(q.get("type") == "essay" for q in questions),
        "missing": missing,
        "invalid_options": invalid_options,
        "invalid_answers": invalid_answers,
    }


def main() -> int:
    json_files = sorted(DATA_ROOT.glob("*/115年/*/試題.json"))
    if not json_files:
        print("找不到 115 年試題 JSON", file=sys.stderr)
        return 2

    reports = [repair_file(path) for path in json_files]
    failed = [
        report for report in reports
        if report["missing"] or report["invalid_options"] or report["invalid_answers"]
    ]
    summary = {
        "files": len(reports),
        "questions": sum(report["questions"] for report in reports),
        "choice": sum(report["choice"] for report in reports),
        "essay": sum(report["essay"] for report in reports),
        "failed_files": len(failed),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for report in failed:
        print("REPAIR_ISSUE " + json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
