#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""從官方 PDF 版面回填 115 年漏掉或缺選項的測驗題。

舊文字流解析器偶爾會因題號與題幹分屬不同文字區塊，漏掉版面上完整存在
的題目。本工具以 PyMuPDF 的單字座標辨識左欄題號與 A–D 選項，僅修復
「官方答案表有題號、現有 JSON 卻缺題或選項不完整」的項目。

英文克漏字只有題號與選項、沒有獨立題幹，會保留給
``repair_115_choice_blocks.py`` 重建共用文章與空格題。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.parse import patterns as P  # noqa: E402
from scripts.parse.answer_extractor import parse_answer_pdf  # noqa: E402

EXPECTED_LABELS = {"A", "B", "C", "D"}
LABEL_RE = re.compile(r"^\(([A-D])\)(.*)$")
NUMBER_RE = re.compile(r"^\d{1,3}$")


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int
    line: int
    index: int


@dataclass(frozen=True)
class Candidate:
    number: int
    stem: str
    options: dict[str, str]
    page: int


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


def clean_text(tokens: Iterable[str]) -> str:
    text = " ".join(token for token in tokens if token).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?％%）)])", r"\1", text)
    text = re.sub(r"([（(])\s+", r"\1", text)
    return text.strip()


def page_words(page: pymupdf.Page) -> list[Word]:
    words: list[Word] = []
    for raw in page.get_text("words", sort=True):
        x0, y0, x1, y1, raw_text, block, line, index = raw[:8]
        text = P.replace_pua_chars(str(raw_text)).strip()
        if not text:
            continue
        words.append(
            Word(
                float(x0), float(y0), float(x1), float(y1), text,
                int(block), int(line), int(index),
            )
        )
    return words


def is_left_question_anchor(word: Word, answer_numbers: set[int], page_width: float) -> bool:
    if not NUMBER_RE.fullmatch(word.text):
        return False
    number = int(word.text)
    if number not in answer_numbers:
        return False
    # 考選部題號位於左側約 8–16% 頁寬；文章內空格編號則在正文欄中。
    return word.x0 <= max(110.0, page_width * 0.19)


def label_from_word(word: Word) -> tuple[str, str] | None:
    match = LABEL_RE.match(word.text)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def parse_region(number: int, region: list[Word], page_number: int) -> Candidate | None:
    if not region:
        return None

    first_label = next(
        (index for index, word in enumerate(region) if label_from_word(word)),
        None,
    )
    if first_label is None:
        return None

    stem_tokens = [word.text for word in region[:first_label]]
    stem = clean_text(stem_tokens)

    # 只有「題號 + A–D」而無獨立題幹者通常是英文克漏字，交由下一階段
    # 連同 passage 重建，避免產生沒有語境的假題幹。
    if len(re.sub(r"\W+", "", stem, flags=re.UNICODE)) < 6:
        return None

    option_tokens: dict[str, list[str]] = {}
    current: str | None = None
    for word in region[first_label:]:
        parsed = label_from_word(word)
        if parsed:
            label, suffix = parsed
            # 同一區域一旦完成 A–D 後再碰到 (A)，通常已進入附註或下一區塊。
            if label in option_tokens:
                break
            current = label
            option_tokens[current] = []
            if suffix:
                option_tokens[current].append(suffix)
            continue
        if current is not None:
            option_tokens[current].append(word.text)

    if set(option_tokens) != EXPECTED_LABELS:
        return None

    options = {label: clean_text(option_tokens[label]) for label in "ABCD"}
    if any(not value for value in options.values()):
        return None

    # 避免下一題或頁尾被誤併入 D；題目區域已由下一個左欄題號截斷，
    # 這裡再清除常見跨頁標記。
    options["D"] = re.split(
        r"\s+(?:請接|頁次[:：]|代號[:：]|全[一二三四五六七八九十\d]+頁)\b",
        options["D"],
        maxsplit=1,
    )[0].strip()
    if not options["D"]:
        return None

    return Candidate(number=number, stem=stem, options=options, page=page_number)


def extract_candidates(pdf_path: Path, answer_numbers: set[int]) -> dict[int, Candidate]:
    candidates: dict[int, Candidate] = {}
    with pymupdf.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            words = page_words(page)
            anchors = [
                index
                for index, word in enumerate(words)
                if is_left_question_anchor(word, answer_numbers, page.rect.width)
            ]
            for position, anchor_index in enumerate(anchors):
                anchor = words[anchor_index]
                number = int(anchor.text)
                end = anchors[position + 1] if position + 1 < len(anchors) else len(words)
                candidate = parse_region(
                    number,
                    words[anchor_index + 1:end],
                    page_index + 1,
                )
                if candidate is None:
                    continue
                old = candidates.get(number)
                if old is None or len(candidate.stem) + sum(map(len, candidate.options.values())) < (
                    len(old.stem) + sum(map(len, old.options.values()))
                ):
                    candidates[number] = candidate
    return candidates


def choice_map(questions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    essays: list[dict[str, Any]] = []
    choices: dict[int, dict[str, Any]] = {}
    for question in questions:
        if question.get("type") != "choice":
            essays.append(question)
            continue
        try:
            number = int(question.get("number"))
        except (TypeError, ValueError):
            essays.append(question)
            continue
        # 重複題號時優先保留選項較完整者；後續 cloze 修復會再 canonicalize。
        old = choices.get(number)
        new_options = question.get("options")
        new_score = len(new_options) if isinstance(new_options, dict) else 0
        old_options = old.get("options") if old else None
        old_score = len(old_options) if isinstance(old_options, dict) else -1
        if old is None or new_score > old_score:
            choices[number] = question
    return essays, choices


def repair_json(json_path: Path) -> dict[str, Any]:
    pdf_path = json_path.with_suffix(".pdf")
    answer_path = json_path.parent / "答案.pdf"
    if not pdf_path.exists() or not answer_path.exists():
        return {"path": json_path.as_posix(), "recovered": [], "skipped": True}

    raw_answers = parse_answer_pdf(answer_path)
    answers = {
        int(number): normalized
        for number, value in raw_answers.items()
        if (normalized := normalize_answer(value)) is not None
    }
    if not answers:
        return {"path": json_path.as_posix(), "recovered": [], "skipped": True}

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError(f"questions 非陣列：{json_path}")

    essays, choices = choice_map(questions)
    targets = {
        number
        for number in answers
        if number not in choices
        or not isinstance(choices[number].get("options"), dict)
        or set(choices[number]["options"]) != EXPECTED_LABELS
    }
    if not targets:
        return {"path": json_path.as_posix(), "recovered": [], "skipped": False}

    candidates = extract_candidates(pdf_path, set(answers))
    section = next(
        (q.get("section") for q in choices.values() if q.get("section")),
        "乙、測驗題",
    )
    recovered: list[int] = []
    unresolved: list[int] = []

    for number in sorted(targets):
        candidate = candidates.get(number)
        if candidate is None:
            unresolved.append(number)
            continue
        choices[number] = {
            "number": number,
            "type": "choice",
            "stem": candidate.stem,
            "options": candidate.options,
            "answer": answers[number],
            "section": section,
            "_recovered_from_pdf_page": candidate.page,
        }
        recovered.append(number)

    payload["questions"] = essays + [choices[number] for number in sorted(choices)]
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "path": json_path.as_posix(),
        "recovered": recovered,
        "unresolved": unresolved,
        "candidate_numbers": sorted(candidates),
        "skipped": False,
    }


def run(root: Path) -> dict[str, Any]:
    json_files = sorted(root.glob("*/115年/*/試題.json"))
    if not json_files:
        raise RuntimeError(f"找不到 115 年試題 JSON：{root}")

    reports: list[dict[str, Any]] = []
    for json_path in json_files:
        report = repair_json(json_path)
        reports.append(report)
        if report.get("recovered") or report.get("unresolved"):
            print(
                f"{report['path']}：回填={report.get('recovered', [])}，"
                f"待後續處理={report.get('unresolved', [])}"
            )

    recovered_total = sum(len(report.get("recovered", [])) for report in reports)
    unresolved = [
        {"path": report["path"], "numbers": report.get("unresolved", [])}
        for report in reports
        if report.get("unresolved")
    ]
    summary = {
        "files": len(reports),
        "recovered_total": recovered_total,
        "unresolved_files": unresolved,
        "reports": reports,
    }
    print(
        f"完成 PDF 版面回填：掃描 {len(reports)} 份 JSON，"
        f"共回填 {recovered_total} 題；"
        f"仍待克漏字階段 {len(unresolved)} 份"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="從官方 PDF 版面回填 115 年漏題")
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
