#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""驗證 115 年警察人員三等考試匯入結果。

驗證重點：
- 13 個既有學系資料夾皆建立 115 年資料；
- 共 90 份 ``試題.json``；
- 關鍵專業科目未因類別辨識錯誤而遺漏；
- JSON 欄位、題號、選項與測驗題答案具基本完整性；
- 官方更正答案優先於原始答案。
"""

from __future__ import annotations

import json
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

EXPECTED_SIGNATURES = {
    "行政警察學系": (
        "警察學與警察勤務",
        "警察政策與犯罪預防",
        "偵查法學與犯罪偵查",
    ),
    "外事警察學系": (
        "外事警察學",
        "國際警察合作與跨國(境)犯罪防制",
    ),
    "刑事警察學系": (
        "犯罪偵查學",
        "偵查法學",
        "刑案現場處理與刑事鑑識",
    ),
    "公共安全學系社安組": (
        "國土安全與非傳統安全",
        "情報學",
        "國家安全情報法制",
    ),
    "犯罪防治學系預防組": (
        "諮商輔導與婦幼保護",
        "犯罪學與犯罪預防",
        "犯罪分析",
    ),
    "消防學系": (
        "火災學與消防化學",
        "消防安全設備",
        "消防戰術",
    ),
    "交通學系交通組": (
        "交通警察學",
        "交通統計與分析",
        "交通工程與管制",
    ),
    "資訊管理學系": (
        "電腦犯罪偵查",
        "數位鑑識執法",
        "警政資訊管理與應用",
    ),
    "鑑識科學學系": (
        "犯罪偵查",
        "物理鑑識",
        "刑事生物",
        "刑事化學",
    ),
    "國境警察學系境管組": (
        "移民情勢與政策分析",
        "國土安全與國境安全管理",
        "國境執法",
    ),
    "水上警察學系": (
        "水上警察學",
        "國際海洋法",
        "海上犯罪偵查法學",
    ),
    "法律學系": (
        "行政法與警察行政違規調查裁處作業",
        "警察法制作業",
        "偵查法學與刑事司法作業",
    ),
    "行政管理學系": (
        "警察人事行政與法制",
        "警察危機應變與安全管理",
        "警察組織與事務管理",
    ),
}

CORRECTED_ANSWER_SUBJECTS = (
    ("行政警察學系", "警察政策與犯罪預防"),
    ("刑事警察學系", "犯罪偵查學"),
    ("刑事警察學系", "刑案現場處理與刑事鑑識"),
    ("水上警察學系", "海巡法規"),
)

ALLOWED_ANSWERS = {"A", "B", "C", "D"}


def add_issue(items: list[dict[str, Any]], code: str, message: str, **context: Any) -> None:
    issue = {"code": code, "message": message}
    issue.update(context)
    items.append(issue)


def subject_matches(subject: str, needle: str) -> bool:
    """資料夾名稱可能經 80 字截斷，因此採前綴／包含比對。"""
    return needle in subject or subject in needle


def validate_question(
    question: dict[str, Any],
    *,
    category: str,
    subject: str,
    json_path: Path,
    errors: list[dict[str, Any]],
) -> None:
    q_type = question.get("type")
    number = question.get("number")
    stem = question.get("stem")

    if q_type not in {"choice", "essay"}:
        add_issue(
            errors,
            "invalid_question_type",
            "題型必須為 choice 或 essay",
            category=category,
            subject=subject,
            path=str(json_path.relative_to(ROOT)),
            number=number,
            value=q_type,
        )
    if not isinstance(stem, str) or not stem.strip():
        add_issue(
            errors,
            "empty_stem",
            "題幹為空",
            category=category,
            subject=subject,
            path=str(json_path.relative_to(ROOT)),
            number=number,
        )

    if q_type != "choice":
        return

    options = question.get("options")
    if not isinstance(options, dict) or set(options) != ALLOWED_ANSWERS:
        add_issue(
            errors,
            "invalid_options",
            "選擇題必須具有 A-D 四個選項",
            category=category,
            subject=subject,
            path=str(json_path.relative_to(ROOT)),
            number=number,
            option_keys=sorted(options) if isinstance(options, dict) else None,
        )
    elif any(not isinstance(value, str) or not value.strip() for value in options.values()):
        add_issue(
            errors,
            "empty_option",
            "選擇題含空白選項",
            category=category,
            subject=subject,
            path=str(json_path.relative_to(ROOT)),
            number=number,
        )

    if "answer" in question:
        answer = question["answer"]
        if answer is None:
            return
        if isinstance(answer, str) and answer in ALLOWED_ANSWERS:
            return
        if (
            isinstance(answer, list)
            and answer
            and all(value in ALLOWED_ANSWERS for value in answer)
        ):
            return
        add_issue(
            errors,
            "invalid_answer",
            "答案不是 A-D、複數合法答案或送分值",
            category=category,
            subject=subject,
            path=str(json_path.relative_to(ROOT)),
            number=number,
            answer=answer,
        )


def main() -> int:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    category_stats: dict[str, Any] = {}
    total_files = 0
    total_questions = 0
    total_choice = 0
    total_essay = 0

    for category, expected_count in EXPECTED_COUNTS.items():
        year_dir = DATA_ROOT / category / "115年"
        if not year_dir.is_dir():
            add_issue(
                errors,
                "missing_category",
                "缺少 115 年類別資料夾",
                category=category,
                path=str(year_dir.relative_to(ROOT)),
            )
            continue

        json_files = sorted(year_dir.glob("*/試題.json"))
        subjects = [path.parent.name for path in json_files]
        total_files += len(json_files)

        if len(json_files) != expected_count:
            add_issue(
                errors,
                "unexpected_subject_count",
                "科目檔案數與考選部官方頁面不符",
                category=category,
                expected=expected_count,
                actual=len(json_files),
                subjects=subjects,
            )

        for signature in EXPECTED_SIGNATURES[category]:
            if not any(subject_matches(subject, signature) for subject in subjects):
                add_issue(
                    errors,
                    "missing_signature_subject",
                    "缺少用於辨識類別的專業科目",
                    category=category,
                    subject=signature,
                    available=subjects,
                )

        category_choice = 0
        category_essay = 0
        category_questions = 0
        quality_scores: list[float] = []

        for json_path in json_files:
            subject = json_path.parent.name
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as exc:
                add_issue(
                    errors,
                    "invalid_json",
                    "JSON 無法解析",
                    category=category,
                    subject=subject,
                    path=str(json_path.relative_to(ROOT)),
                    error=str(exc),
                )
                continue

            if payload.get("year") != 115:
                add_issue(
                    errors,
                    "wrong_year",
                    "year 欄位不是 115",
                    category=category,
                    subject=subject,
                    value=payload.get("year"),
                )
            if payload.get("category") != category:
                add_issue(
                    errors,
                    "wrong_category",
                    "category 欄位與資料夾不一致",
                    category=category,
                    subject=subject,
                    value=payload.get("category"),
                )
            if payload.get("subject") != subject:
                add_issue(
                    errors,
                    "wrong_subject",
                    "subject 欄位與資料夾不一致",
                    category=category,
                    subject=subject,
                    value=payload.get("subject"),
                )

            questions = payload.get("questions")
            if not isinstance(questions, list) or not questions:
                add_issue(
                    errors,
                    "empty_questions",
                    "試題未解析出任何題目",
                    category=category,
                    subject=subject,
                    path=str(json_path.relative_to(ROOT)),
                )
                continue

            seen_choice: set[int] = set()
            seen_essay: set[str] = set()
            choice_count = 0
            essay_count = 0

            for question in questions:
                if not isinstance(question, dict):
                    add_issue(
                        errors,
                        "invalid_question_record",
                        "questions 陣列含非物件資料",
                        category=category,
                        subject=subject,
                        path=str(json_path.relative_to(ROOT)),
                    )
                    continue

                validate_question(
                    question,
                    category=category,
                    subject=subject,
                    json_path=json_path,
                    errors=errors,
                )

                q_type = question.get("type")
                q_number = question.get("number")
                if q_type == "choice":
                    choice_count += 1
                    if not isinstance(q_number, int):
                        add_issue(
                            errors,
                            "invalid_choice_number",
                            "選擇題題號必須為整數",
                            category=category,
                            subject=subject,
                            value=q_number,
                        )
                    elif q_number in seen_choice:
                        add_issue(
                            errors,
                            "duplicate_choice_number",
                            "選擇題題號重複",
                            category=category,
                            subject=subject,
                            number=q_number,
                        )
                    else:
                        seen_choice.add(q_number)
                elif q_type == "essay":
                    essay_count += 1
                    key = str(q_number)
                    if key in seen_essay:
                        add_issue(
                            errors,
                            "duplicate_essay_number",
                            "申論題題號重複",
                            category=category,
                            subject=subject,
                            number=q_number,
                        )
                    else:
                        seen_essay.add(key)

            answer_source = payload.get("_answer_source")
            merged = payload.get("_answers_merged")
            if choice_count:
                if not answer_source:
                    add_issue(
                        errors,
                        "missing_answer_source",
                        "含選擇題但未合併官方答案",
                        category=category,
                        subject=subject,
                        choice_questions=choice_count,
                    )
                elif merged != choice_count:
                    add_issue(
                        errors,
                        "incomplete_answer_merge",
                        "官方答案合併數量與選擇題數不一致",
                        category=category,
                        subject=subject,
                        choice_questions=choice_count,
                        merged=merged,
                        answer_source=answer_source,
                    )

            for corrected_category, corrected_subject in CORRECTED_ANSWER_SUBJECTS:
                if category == corrected_category and subject_matches(subject, corrected_subject):
                    if answer_source != "更正答案.pdf":
                        add_issue(
                            errors,
                            "corrected_answer_not_used",
                            "未優先採用考選部更正答案",
                            category=category,
                            subject=subject,
                            answer_source=answer_source,
                        )

            quality = payload.get("_quality") or {}
            score = quality.get("score")
            if isinstance(score, (int, float)):
                quality_scores.append(float(score))
                if score < 0.55:
                    add_issue(
                        errors,
                        "very_low_quality",
                        "解析品質分數低於 0.55",
                        category=category,
                        subject=subject,
                        score=score,
                        issues=quality.get("issues", []),
                    )
                elif score < 0.70:
                    add_issue(
                        warnings,
                        "low_quality",
                        "解析品質分數低於 0.70，需人工抽查",
                        category=category,
                        subject=subject,
                        score=score,
                        issues=quality.get("issues", []),
                    )

            category_choice += choice_count
            category_essay += essay_count
            category_questions += len(questions)

        total_choice += category_choice
        total_essay += category_essay
        total_questions += category_questions
        category_stats[category] = {
            "files": len(json_files),
            "subjects": subjects,
            "questions": category_questions,
            "choice": category_choice,
            "essay": category_essay,
            "quality_min": min(quality_scores) if quality_scores else None,
            "quality_max": max(quality_scores) if quality_scores else None,
        }

    expected_total = sum(EXPECTED_COUNTS.values())
    if total_files != expected_total:
        add_issue(
            errors,
            "unexpected_total_file_count",
            "115 年三等警察試題總檔案數不符",
            expected=expected_total,
            actual=total_files,
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
        "summary": {
            "expected_categories": len(EXPECTED_COUNTS),
            "actual_categories": sum(
                1 for category in EXPECTED_COUNTS
                if (DATA_ROOT / category / "115年").is_dir()
            ),
            "expected_files": expected_total,
            "actual_files": total_files,
            "questions": total_questions,
            "choice": total_choice,
            "essay": total_essay,
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "categories": category_stats,
        "errors": errors,
        "warnings": warnings,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"驗證報告：{REPORT_PATH.relative_to(ROOT)}")

    if errors:
        for error in errors[:30]:
            print(f"ERROR {error['code']}: {error['message']} | {error}", file=sys.stderr)
        if len(errors) > 30:
            print(f"...另有 {len(errors) - 30} 項錯誤", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
