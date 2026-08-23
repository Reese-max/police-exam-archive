#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""嚴格驗證 115 年警察人員三等考試匯入資料。"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "考古題庫"
REPORT_PATH = ROOT / "reports" / "import_115_police_third.json"
SOURCE_PAGE = (
    "https://wwwq.moex.gov.tw/exam/"
    "wFrmExamQandASearch.aspx?e=115060&y=2026"
)

EXPECTED_COUNTS = {
    "行政警察學系": 7,
    "外事警察學系": 6,
    "刑事警察學系": 7,
    "公共安全學系社安組": 7,
    "犯罪防治學系預防組": 7,
    "消防學系": 7,
    "交通學系交通組": 7,
    "資訊管理學系": 7,
    "鑑識科學學系": 7,
    "國境警察學系境管組": 7,
    "水上警察學系": 7,
    "法律學系": 7,
    "行政管理學系": 7,
}

EXPECTED_TOTALS = {
    "files": 90,
    "questions": 1924,
    "choice": 1695,
    "essay": 229,
}

EXPECTED_SIGNATURES = {
    "行政警察學系": ("警察學與警察勤務", "警察政策與犯罪預防", "偵查法學與犯罪偵查"),
    "外事警察學系": ("外事警察學", "國際警察合作與跨國(境)犯罪防制"),
    "刑事警察學系": ("犯罪偵查學", "偵查法學", "刑案現場處理與刑事鑑識"),
    "公共安全學系社安組": ("國土安全與非傳統安全", "情報學", "國家安全情報法制"),
    "犯罪防治學系預防組": ("諮商輔導與婦幼保護", "犯罪學與犯罪預防", "犯罪分析"),
    "消防學系": ("火災學與消防化學", "消防安全設備", "消防戰術"),
    "交通學系交通組": ("交通警察學", "交通統計與分析", "交通工程與管制"),
    "資訊管理學系": ("電腦犯罪偵查", "數位鑑識執法", "警政資訊管理與應用"),
    "鑑識科學學系": ("犯罪偵查", "物理鑑識", "刑事生物", "刑事化學"),
    "國境警察學系境管組": ("移民情勢與政策分析", "國土安全與國境安全管理", "國境執法"),
    "水上警察學系": ("水上警察學", "國際海洋法", "海上犯罪偵查法學"),
    "法律學系": ("行政法與警察行政違規調查裁處作業", "警察法制作業", "偵查法學與刑事司法作業"),
    "行政管理學系": ("警察人事行政與法制", "警察危機應變與安全管理", "警察組織與事務管理"),
}

SPECIAL_EXPECTATIONS = (
    ("行政警察學系", "警察政策與犯罪預防", 4, ["A", "C"]),
    ("刑事警察學系", "犯罪偵查學", 24, "送分"),
    ("刑事警察學系", "刑案現場處理與刑事鑑識", 6, ["A", "C", "D"]),
    ("水上警察學系", "海巡法規", 23, "B"),
    ("水上警察學系", "海巡法規", 25, "送分"),
)

ALLOWED_OPTIONS = {"A", "B", "C", "D"}
PUA_RE = re.compile(r"[\ue000-\uf8ff]")
CAMEL_RE = re.compile(r"[a-z]{2,}[A-Z][a-z]{2,}")
METADATA_RE = re.compile(r"乙、測驗|代號[:：]\s*\d{4}")


def subject_matches(actual: str, expected: str) -> bool:
    return actual == expected or actual.startswith(expected) or expected.startswith(actual)


def valid_answer(answer: Any) -> bool:
    if isinstance(answer, str):
        return answer in ALLOWED_OPTIONS or answer == "送分" or bool(
            re.fullmatch(r"[A-D](?:或[A-D])+", answer)
        )
    if isinstance(answer, list):
        return bool(answer) and len(answer) == len(set(answer)) and all(
            item in ALLOWED_OPTIONS for item in answer
        )
    return False


def add_error(errors: list[dict[str, Any]], code: str, **context: Any) -> None:
    errors.append({"code": code, **context})


def all_text(question: dict[str, Any]) -> list[str]:
    values = []
    for key in ("stem", "passage"):
        if question.get(key):
            values.append(str(question[key]))
    values.extend(str(value) for value in (question.get("options") or {}).values())
    return values


def main() -> int:
    errors: list[dict[str, Any]] = []
    category_stats: dict[str, Any] = {}
    total_files = total_questions = total_choice = total_essay = 0
    loaded: dict[tuple[str, str], dict[str, Any]] = {}

    for category, expected_file_count in EXPECTED_COUNTS.items():
        year_dir = DATA_ROOT / category / "115年"
        files = sorted(year_dir.glob("*/試題.json")) if year_dir.is_dir() else []
        total_files += len(files)
        if len(files) != expected_file_count:
            add_error(
                errors,
                "subject_count",
                category=category,
                expected=expected_file_count,
                actual=len(files),
            )

        subjects = [path.parent.name for path in files]
        for signature in EXPECTED_SIGNATURES[category]:
            if not any(subject_matches(subject, signature) for subject in subjects):
                add_error(errors, "missing_subject", category=category, subject=signature)

        cat_questions = cat_choice = cat_essay = 0
        for path in files:
            subject = path.parent.name
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                add_error(errors, "invalid_json", path=str(path.relative_to(ROOT)), error=str(exc))
                continue
            loaded[(category, subject)] = payload

            if payload.get("year") != 115:
                add_error(errors, "wrong_year", category=category, subject=subject, value=payload.get("year"))
            if payload.get("category") != category:
                add_error(errors, "wrong_category", category=category, subject=subject, value=payload.get("category"))
            if payload.get("subject") != subject:
                add_error(errors, "wrong_subject", category=category, subject=subject, value=payload.get("subject"))

            questions = payload.get("questions")
            if not isinstance(questions, list) or not questions:
                add_error(errors, "empty_questions", category=category, subject=subject)
                continue

            choices = [q for q in questions if isinstance(q, dict) and q.get("type") == "choice"]
            essays = [q for q in questions if isinstance(q, dict) and q.get("type") == "essay"]
            cat_questions += len(questions)
            cat_choice += len(choices)
            cat_essay += len(essays)

            if choices:
                numbers = [q.get("number") for q in choices]
                expected_numbers = list(range(1, len(choices) + 1))
                if numbers != expected_numbers:
                    add_error(errors, "choice_number_sequence", category=category, subject=subject, numbers=numbers)
                if payload.get("_answers_merged") != len(choices):
                    add_error(
                        errors,
                        "answer_merge_count",
                        category=category,
                        subject=subject,
                        expected=len(choices),
                        actual=payload.get("_answers_merged"),
                    )
                if not payload.get("_answer_source"):
                    add_error(errors, "missing_answer_source", category=category, subject=subject)

            for question in questions:
                if not isinstance(question, dict):
                    add_error(errors, "invalid_question_record", category=category, subject=subject)
                    continue
                stem = str(question.get("stem") or "").strip()
                if not stem and not str(question.get("passage") or "").strip():
                    add_error(errors, "empty_stem", category=category, subject=subject, number=question.get("number"))
                if question.get("type") == "choice":
                    options = question.get("options")
                    if not isinstance(options, dict) or set(options) != ALLOWED_OPTIONS or any(
                        not str(options[label]).strip() for label in ALLOWED_OPTIONS
                    ):
                        add_error(errors, "invalid_options", category=category, subject=subject, number=question.get("number"))
                    if not valid_answer(question.get("answer")):
                        add_error(
                            errors,
                            "invalid_answer",
                            category=category,
                            subject=subject,
                            number=question.get("number"),
                            answer=question.get("answer"),
                        )
                for text in all_text(question):
                    if PUA_RE.search(text):
                        add_error(errors, "pua_character", category=category, subject=subject, number=question.get("number"))
                    if CAMEL_RE.search(text):
                        add_error(errors, "camelcase_concat", category=category, subject=subject, number=question.get("number"), text=text[:160])
                if METADATA_RE.search(stem):
                    add_error(errors, "metadata_in_stem", category=category, subject=subject, number=question.get("number"), stem=stem[:240])

        category_stats[category] = {
            "files": len(files),
            "questions": cat_questions,
            "choice": cat_choice,
            "essay": cat_essay,
        }
        total_questions += cat_questions
        total_choice += cat_choice
        total_essay += cat_essay

    actual_totals = {
        "files": total_files,
        "questions": total_questions,
        "choice": total_choice,
        "essay": total_essay,
    }
    for key, expected in EXPECTED_TOTALS.items():
        if actual_totals[key] != expected:
            add_error(errors, "total_mismatch", metric=key, expected=expected, actual=actual_totals[key])

    for category, expected_subject, number, expected_answer in SPECIAL_EXPECTATIONS:
        matches = [
            payload for (cat, subject), payload in loaded.items()
            if cat == category and subject_matches(subject, expected_subject)
        ]
        if len(matches) != 1:
            add_error(errors, "special_subject_match", category=category, subject=expected_subject, matches=len(matches))
            continue
        questions = {
            q.get("number"): q for q in matches[0].get("questions", [])
            if isinstance(q, dict) and q.get("type") == "choice"
        }
        actual_answer = questions.get(number, {}).get("answer")
        if actual_answer != expected_answer:
            add_error(
                errors,
                "corrected_answer_mismatch",
                category=category,
                subject=expected_subject,
                number=number,
                expected=expected_answer,
                actual=actual_answer,
            )
        if matches[0].get("_answer_source") != "考選部標準答案更正清冊":
            add_error(
                errors,
                "corrected_answer_source",
                category=category,
                subject=expected_subject,
                actual=matches[0].get("_answer_source"),
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "authority": "考選部",
            "exam_code": "115060",
            "url": SOURCE_PAGE,
            "year": 115,
            "level": "三等",
        },
        "summary": {**actual_totals, "categories": len(EXPECTED_COUNTS), "errors": len(errors)},
        "categories": category_stats,
        "errors": errors,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"驗證報告：{REPORT_PATH.relative_to(ROOT)}")
    for error in errors[:50]:
        print("ERROR " + json.dumps(error, ensure_ascii=False), file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
