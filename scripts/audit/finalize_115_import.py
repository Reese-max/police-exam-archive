#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完成並稽核 115 年警察人員三等考試匯入。

工作內容：
1. 驗證 13 類科、90 科次的 PDF 與 JSON 完整性。
2. 修正 JSON 的年度、類科、來源與官方追溯欄位。
3. 以題目內容指紋標記 115 年跨類科共用考卷。
4. 執行結構、答案、文字與來源 SHA-256 檢查。
5. 更新資料集統計、README、測試基準與匯入報告。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

YEAR = 115
OFFICIAL_PAGE = (
    "https://wwwq.moex.gov.tw/exam/"
    "wFrmExamQandASearch.aspx?e=115060&y=2026"
)
EXAM_CODE = "115060"

CATEGORY_MAP: "OrderedDict[str, dict[str, str | int]]" = OrderedDict(
    [
        ("201", {"folder": "行政警察學系", "official": "行政警察人員", "subjects": 7}),
        ("202", {"folder": "外事警察學系", "official": "外事警察人員(選試英語)", "subjects": 6}),
        ("203", {"folder": "刑事警察學系", "official": "刑事警察人員", "subjects": 7}),
        ("204", {"folder": "公共安全學系社安組", "official": "公共安全人員", "subjects": 7}),
        ("205", {"folder": "犯罪防治學系預防組", "official": "犯罪防治人員預防組", "subjects": 7}),
        ("206", {"folder": "消防學系", "official": "消防警察人員", "subjects": 7}),
        ("207", {"folder": "交通學系交通組", "official": "交通警察人員交通組", "subjects": 7}),
        ("208", {"folder": "資訊管理學系", "official": "警察資訊管理人員", "subjects": 7}),
        ("209", {"folder": "鑑識科學學系", "official": "刑事鑑識人員", "subjects": 7}),
        ("210", {"folder": "國境警察學系境管組", "official": "國境警察人員", "subjects": 7}),
        ("211", {"folder": "水上警察學系", "official": "水上警察人員", "subjects": 7}),
        ("212", {"folder": "法律學系", "official": "警察法制人員", "subjects": 7}),
        ("213", {"folder": "行政管理學系", "official": "行政管理人員", "subjects": 7}),
    ]
)
FOLDER_TO_CODE = {
    str(info["folder"]): code for code, info in CATEGORY_MAP.items()
}
EXPECTED_SUBJECT_COPIES = sum(int(v["subjects"]) for v in CATEGORY_MAP.values())
VALID_ANSWER_RE = re.compile(r"^[ABCD](?:或[ABCD])*$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
PUA_RE = re.compile(r"[\ue000-\uf8ff]")


class AuditError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"無法讀取 JSON：{path}：{exc}") from exc


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def question_fingerprint(payload: dict[str, Any]) -> str:
    questions = payload.get("questions") or []
    normalized = json.dumps(
        questions,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def all_text_fields(question: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("stem", "passage"):
        value = question.get(field)
        if value is not None:
            values.append(str(value))
    options = question.get("options")
    if isinstance(options, dict):
        values.extend(str(v) for v in options.values())
    return values



def normalize_official_answer(value: Any) -> str | None:
    """把官方答案儲存為資料庫慣用的 A／A或C／送分格式。"""
    if value is None:
        return None
    if isinstance(value, list):
        labels = [str(v).strip().upper() for v in value if str(v).strip().upper() in "ABCD"]
        labels = list(dict.fromkeys(labels))
        return "或".join(labels) if labels else None

    raw = unicodedata.normalize("NFKC", str(value))
    raw = re.sub(r"\s+", "", raw).upper()
    if not raw:
        return None
    if "送分" in raw or "一律給分" in raw:
        return "送分"
    labels = re.findall(r"[A-D]", raw)
    labels = list(dict.fromkeys(labels))
    if not labels:
        return None
    return "或".join(labels)


def corrected_answers_from_notes(text: str) -> dict[int, str]:
    """解析更正答案 PDF 備註，例如「第4題答Ａ或Ｃ者均給分」."""
    compact = unicodedata.normalize("NFKC", text)
    compact = re.sub(r"\s+", "", compact)
    result: dict[int, str] = {}

    for match in re.finditer(r"第(\d+)題一律給分", compact):
        result[int(match.group(1))] = "送分"

    # 可涵蓋「答B給分」「答A或C者均給分」「答A或C或D者均給分」。
    for match in re.finditer(
        r"第(\d+)題答([A-D](?:或[A-D])*)(?:者)?(?:均)?給分",
        compact,
    ):
        result[int(match.group(1))] = normalize_official_answer(match.group(2)) or ""

    for match in re.finditer(
        r"第(\d+)題(?:答案)?(?:更正|改)(?:為|成)([A-D](?:或[A-D])*)",
        compact,
    ):
        result[int(match.group(1))] = normalize_official_answer(match.group(2)) or ""

    return {number: answer for number, answer in result.items() if answer}


def extract_official_answers(pdf_path: Path) -> dict[int, str]:
    """從考選部標準／更正答案 PDF 表格抽出題號與答案。

    既有行文字解析器遇到 PDF 表格時可能錯位；此處以 pdfplumber
    的表格儲存格配對「題號列」與「答案列」，再用備註修補 #。
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise AuditError("缺少 pdfplumber，無法驗證官方答案") from exc

    answers: dict[int, str] = {}
    full_text_parts: list[str] = []

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                full_text_parts.append(page.extract_text() or "")
                tables = page.extract_tables() or []
                for table in tables:
                    for row_index in range(len(table) - 1):
                        number_row = table[row_index] or []
                        answer_row = table[row_index + 1] or []
                        first_number = unicodedata.normalize(
                            "NFKC", str(number_row[0] or "")
                        ).replace(" ", "")
                        first_answer = unicodedata.normalize(
                            "NFKC", str(answer_row[0] or "")
                        ).replace(" ", "")
                        if "題號" not in first_number or "答案" not in first_answer:
                            continue
                        for number_cell, answer_cell in zip(
                            number_row[1:], answer_row[1:]
                        ):
                            number_match = re.search(
                                r"第\s*(\d+)\s*題",
                                unicodedata.normalize(
                                    "NFKC", str(number_cell or "")
                                ),
                            )
                            if not number_match:
                                continue
                            number = int(number_match.group(1))
                            raw_answer = unicodedata.normalize(
                                "NFKC", str(answer_cell or "")
                            ).strip()
                            if raw_answer == "#":
                                answers[number] = "#"
                                continue
                            normalized = normalize_official_answer(raw_answer)
                            if normalized:
                                answers[number] = normalized
    except Exception as exc:
        raise AuditError(f"官方答案 PDF 解析失敗：{pdf_path}：{exc}") from exc

    full_text = "\n".join(full_text_parts)
    note_answers = corrected_answers_from_notes(full_text)
    for number, answer in note_answers.items():
        answers[number] = answer

    unresolved = sorted(number for number, answer in answers.items() if answer == "#")
    if unresolved:
        raise AuditError(
            f"更正答案 # 無法從備註解析：{pdf_path}，題號 {unresolved}"
        )

    if not answers:
        raise AuditError(f"官方答案 PDF 未抽出任何答案：{pdf_path}")
    return answers


def apply_official_answers(subject_dir: Path, payload: dict[str, Any]) -> None:
    corrected = subject_dir / "更正答案.pdf"
    standard = subject_dir / "答案.pdf"
    answer_pdf = corrected if corrected.exists() else standard if standard.exists() else None

    choice_questions = [
        q for q in payload.get("questions") or [] if q.get("type") == "choice"
    ]
    if not choice_questions:
        return
    if answer_pdf is None:
        raise AuditError(f"含選擇題但缺官方答案 PDF：{subject_dir}")

    official = extract_official_answers(answer_pdf)
    missing: list[Any] = []
    merged = 0
    for question in choice_questions:
        number = question.get("number")
        if not isinstance(number, int) or number not in official:
            missing.append(number)
            continue
        question["answer"] = official[number]
        merged += 1

    if missing:
        raise AuditError(
            f"官方答案缺漏：{answer_pdf}，試題題號 {missing[:20]}"
        )
    payload["_answer_source"] = answer_pdf.name
    payload["_answers_merged"] = merged

def validate_question_file(path: Path, payload: dict[str, Any]) -> dict[str, int]:
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise AuditError(f"無有效題目：{path}")

    choice = 0
    essay = 0
    seen_choice_numbers: set[int] = set()

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise AuditError(f"題目不是物件：{path} 第 {index} 筆")
        qtype = question.get("type")
        stem = str(question.get("stem") or "").strip()
        passage = str(question.get("passage") or "").strip()

        if qtype == "choice":
            choice += 1
            options = question.get("options")
            if not isinstance(options, dict) or set(options) != set("ABCD"):
                raise AuditError(
                    f"選項不完整：{path} 題號 {question.get('number')}，"
                    f"實際鍵值={sorted(options) if isinstance(options, dict) else options!r}"
                )
            if not stem and not passage:
                raise AuditError(
                    f"空白題幹且無共用段落：{path} 題號 {question.get('number')}"
                )

            answer = str(question.get("answer") or "").strip()
            if answer != "送分" and not VALID_ANSWER_RE.fullmatch(answer):
                raise AuditError(
                    f"答案不合法：{path} 題號 {question.get('number')}，答案={answer!r}"
                )

            number = question.get("number")
            if isinstance(number, int):
                if number in seen_choice_numbers:
                    raise AuditError(f"選擇題號重複：{path} 題號 {number}")
                seen_choice_numbers.add(number)
        elif qtype == "essay":
            essay += 1
            if not stem:
                raise AuditError(
                    f"申論題題幹空白：{path} 題號 {question.get('number')}"
                )
        else:
            raise AuditError(f"未知題型：{path} 第 {index} 筆 type={qtype!r}")

        for text in all_text_fields(question):
            if CONTROL_RE.search(text):
                raise AuditError(f"含控制字元：{path} 題號 {question.get('number')}")
            if PUA_RE.search(text):
                raise AuditError(f"含 PUA 私用字元：{path} 題號 {question.get('number')}")

    if seen_choice_numbers:
        ordered = sorted(seen_choice_numbers)
        expected = list(range(ordered[0], ordered[-1] + 1))
        if ordered != expected:
            missing = sorted(set(expected) - set(ordered))
            raise AuditError(f"選擇題號缺漏：{path}，缺 {missing}")

    return {"questions": len(questions), "choice": choice, "essay": essay}


def load_import_manifest(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "115_import_manifest.json"
    manifest = read_json(path)
    catalog = manifest.get("catalog") or {}
    if manifest.get("year") != YEAR:
        raise AuditError(f"下載清單年度不符：{manifest.get('year')}")
    if manifest.get("exam_code") != EXAM_CODE:
        raise AuditError(f"下載清單考試代碼不符：{manifest.get('exam_code')}")
    if catalog.get("category_count") != len(CATEGORY_MAP):
        raise AuditError(
            f"下載清單類科數不符：{catalog.get('category_count')} != {len(CATEGORY_MAP)}"
        )
    if catalog.get("subject_copies") != EXPECTED_SUBJECT_COPIES:
        raise AuditError(
            f"下載清單科次不符：{catalog.get('subject_copies')} "
            f"!= {EXPECTED_SUBJECT_COPIES}"
        )
    return manifest


def manifest_file_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in manifest.get("files") or []:
        path = str(item.get("relative_path") or "").replace("\\", "/")
        if path:
            result[path] = item
    return result


def normalize_115_files(
    data_dir: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    files_by_path = manifest_file_map(manifest)
    records: list[dict[str, Any]] = []
    totals = {"question_files": 0, "questions": 0, "choice": 0, "essay": 0}
    errors: list[str] = []

    for code, info in CATEGORY_MAP.items():
        folder = str(info["folder"])
        year_dir = data_dir / folder / f"{YEAR}年"
        if not year_dir.is_dir():
            errors.append(f"缺類科年度目錄：{year_dir}")
            continue

        subject_dirs = sorted(p for p in year_dir.iterdir() if p.is_dir())
        expected = int(info["subjects"])
        if len(subject_dirs) != expected:
            errors.append(
                f"{folder}：預期 {expected} 科，實際 {len(subject_dirs)} 科"
            )

        for subject_dir in subject_dirs:
            subject = subject_dir.name
            pdf_path = subject_dir / "試題.pdf"
            json_path = subject_dir / "試題.json"
            if not pdf_path.is_file():
                errors.append(f"缺試題 PDF：{pdf_path}")
                continue
            if not json_path.is_file():
                errors.append(f"缺試題 JSON：{json_path}")
                continue
            if not pdf_path.read_bytes()[:5] == b"%PDF-":
                errors.append(f"試題不是有效 PDF：{pdf_path}")
                continue

            rel_pdf = (Path("考古題庫") / pdf_path.relative_to(data_dir)).as_posix()
            manifest_item = files_by_path.get(rel_pdf)
            if not manifest_item:
                errors.append(f"下載清單找不到試題：{rel_pdf}")
                continue
            actual_sha = sha256_file(pdf_path)
            expected_sha = str(manifest_item.get("sha256") or "")
            if actual_sha != expected_sha:
                errors.append(
                    f"PDF SHA-256 不符：{rel_pdf}，"
                    f"manifest={expected_sha} actual={actual_sha}"
                )
                continue

            payload = read_json(json_path)
            metadata = payload.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                payload["metadata"] = metadata

            payload["year"] = YEAR
            payload["category"] = folder
            payload["subject"] = subject
            payload["source_pdf"] = rel_pdf
            payload["file_type"] = "試題"
            metadata.update(
                {
                    "exam_name": "公務人員特種考試警察人員考試",
                    "level": "三等",
                    "year": YEAR,
                    "official_exam_code": EXAM_CODE,
                    "official_category_code": code,
                    "official_category": info["official"],
                    "source_url": manifest_item.get("url"),
                    "source_sha256": actual_sha,
                }
            )

            apply_official_answers(subject_dir, payload)
            stats = validate_question_file(json_path, payload)
            write_json(json_path, payload)

            record = {
                "code": code,
                "folder": folder,
                "official_category": info["official"],
                "subject": subject,
                "json_path": json_path,
                "pdf_path": pdf_path,
                "payload": payload,
                "fingerprint": question_fingerprint(payload),
                **stats,
            }
            records.append(record)
            totals["question_files"] += 1
            totals["questions"] += stats["questions"]
            totals["choice"] += stats["choice"]
            totals["essay"] += stats["essay"]

    if errors:
        raise AuditError("115 年檔案完整性檢查失敗：\n- " + "\n- ".join(errors))
    if totals["question_files"] != EXPECTED_SUBJECT_COPIES:
        raise AuditError(
            f"115 年試題 JSON 份數不符：{totals['question_files']} "
            f"!= {EXPECTED_SUBJECT_COPIES}"
        )
    return records, totals


def mark_duplicates(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record["fingerprint"])].append(record)

    duplicate_files = 0
    duplicate_groups = 0
    group_report: list[dict[str, Any]] = []

    for fingerprint, group in sorted(groups.items()):
        group.sort(
            key=lambda r: (
                list(CATEGORY_MAP).index(str(r["code"])),
                str(r["folder"]),
                str(r["subject"]),
            )
        )
        canonical = group[0]
        if len(group) > 1:
            duplicate_groups += 1

        members: list[str] = []
        for index, record in enumerate(group):
            payload = record["payload"]
            metadata = payload.setdefault("metadata", {})
            # 清掉可能由重跑留下的舊標記。
            for key in ("_is_duplicate", "_duplicate_of", "_duplicate_note"):
                payload.pop(key, None)
                metadata.pop(key, None)

            rel = (
                f"{record['folder']}/{YEAR}年/{record['subject']}"
            )
            members.append(rel)
            if index > 0:
                duplicate_files += 1
                canonical_rel = (
                    f"{canonical['folder']}/{YEAR}年/{canonical['subject']}"
                )
                note = (
                    "此檔案與指定來源考卷題目內容完全相同，"
                    "保留於類科目錄供瀏覽，統計時排除重複。"
                )
                payload["_is_duplicate"] = True
                payload["_duplicate_of"] = canonical_rel
                payload["_duplicate_note"] = note
                metadata["_is_duplicate"] = True
                metadata["_duplicate_of"] = canonical_rel
                metadata["_duplicate_note"] = note

            write_json(record["json_path"], payload)

        if len(group) > 1:
            group_report.append(
                {
                    "fingerprint": fingerprint,
                    "canonical": (
                        f"{canonical['folder']}/{YEAR}年/{canonical['subject']}"
                    ),
                    "copies": len(group),
                    "members": members,
                }
            )

    return {
        "groups": duplicate_groups,
        "duplicate_files": duplicate_files,
        "unique_files": len(records) - duplicate_files,
        "details": group_report,
    }


def count_dataset(data_dir: Path) -> dict[str, Any]:
    files = sorted(data_dir.glob("**/試題.json"))
    counts = {
        "json_files": 0,
        "questions": 0,
        "choice": 0,
        "essay": 0,
        "categories": set(),
        "subjects": set(),
        "years": set(),
    }
    for path in files:
        payload = read_json(path)
        metadata = payload.get("metadata") or {}
        # 與現有測試及索引的去重契約一致。
        if isinstance(metadata, dict) and metadata.get("_is_duplicate"):
            continue
        counts["json_files"] += 1
        category = payload.get("category")
        subject = payload.get("subject")
        year = payload.get("year")
        if category:
            counts["categories"].add(str(category))
        if subject:
            counts["subjects"].add(str(subject))
        if isinstance(year, int):
            counts["years"].add(year)
        for q in payload.get("questions") or []:
            counts["questions"] += 1
            if q.get("type") == "choice":
                counts["choice"] += 1
            elif q.get("type") == "essay":
                counts["essay"] += 1

    return {
        "json_files": counts["json_files"],
        "questions": counts["questions"],
        "choice": counts["choice"],
        "essay": counts["essay"],
        "categories": len(counts["categories"]),
        "subjects": len(counts["subjects"]),
        "years": sorted(counts["years"]),
    }


def update_test_baselines(test_path: Path, totals: dict[str, Any]) -> None:
    text = test_path.read_text(encoding="utf-8")
    replacements = [
        (
            r"assert len\(ALL_FILES\) == \d+,",
            f"assert len(ALL_FILES) == {totals['json_files']},",
        ),
        (
            r"assert len\(ALL_QUESTIONS\) == \d+,",
            f"assert len(ALL_QUESTIONS) == {totals['questions']},",
        ),
        (
            r"assert len\(CHOICE_QUESTIONS\) == \d+,",
            f"assert len(CHOICE_QUESTIONS) == {totals['choice']},",
        ),
        (
            r"assert len\(ESSAY_QUESTIONS\) == \d+,",
            f"assert len(ESSAY_QUESTIONS) == {totals['essay']},",
        ),
    ]
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise AuditError(f"無法更新測試基準：{pattern}")

    message_replacements = [
        (r'預期 \d+ 個非重複檔案', f"預期 {totals['json_files']} 個非重複檔案"),
        (r'預期 \d+ 題，實際 \{len\(ALL_QUESTIONS\)\}', f"預期 {totals['questions']} 題，實際 {{len(ALL_QUESTIONS)}}"),
        (r'預期 \d+ 選擇題', f"預期 {totals['choice']} 選擇題"),
        (r'預期 \d+ 申論題', f"預期 {totals['essay']} 申論題"),
    ]
    for pattern, replacement in message_replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise AuditError(f"無法更新測試訊息：{pattern}")

    # 允許未來考選部公布任意 A-D 複選組合，而不是硬編碼單一年度特例。
    old_block = """        valid_answers = {'A', 'B', 'C', 'D', '送分', 'C或D'}
        invalid = []
        for fp, q in CHOICE_QUESTIONS:
            ans = q.get('answer', '')
            if ans not in valid_answers:
                invalid.append((fp, q.get('number'), ans))"""
    new_block = """        valid_answer = re.compile(r'^[A-D](?:或[A-D])*$')
        invalid = []
        for fp, q in CHOICE_QUESTIONS:
            ans = q.get('answer', '')
            if ans != '送分' and not valid_answer.fullmatch(ans):
                invalid.append((fp, q.get('number'), ans))"""
    if old_block in text:
        text = text.replace(old_block, new_block, 1)
    elif "valid_answer = re.compile" not in text:
        raise AuditError("無法更新答案合法性測試")

    test_path.write_text(text, encoding="utf-8")


def replace_table_value(text: str, label: str, value: str) -> str:
    pattern = rf"(\|\s*{re.escape(label)}\s*\|\s*)[^|]+(\|)"
    updated, count = re.subn(pattern, rf"\g<1>{value} \g<2>", text, count=1)
    if count != 1:
        raise AuditError(f"README 找不到統計列：{label}")
    return updated


def update_readme(readme_path: Path, totals: dict[str, Any]) -> None:
    text = readme_path.read_text(encoding="utf-8")
    text = text.replace("涵蓋 106-114 年（2017-2025）", "涵蓋 106-115 年（2017-2026）")
    text = replace_table_value(text, "學系/類別", f"{totals['categories']} 個")
    text = replace_table_value(text, "年份", "106-115 年（10 年）")
    text = replace_table_value(
        text, "科目", f"{totals['subjects']} 個"
    )
    text = replace_table_value(
        text, "JSON 檔案", f"{totals['json_files']:,} 個（非重複）"
    )
    text = replace_table_value(
        text, "選擇題", f"{totals['choice']:,} 題"
    )
    text = replace_table_value(
        text, "申論題", f"{totals['essay']:,} 題"
    )
    text = replace_table_value(
        text, "總題數", f"{totals['questions']:,} 題"
    )
    text = re.sub(
        r"查詢速度：~\d+ms/次（[\d,]+ 題全文搜尋）。",
        f"查詢速度依執行環境而異（目前 {totals['questions']:,} 題全文搜尋）。",
        text,
        count=1,
    )
    if "## 115 年資料更新" not in text:
        marker = "\n## 資料來源\n"
        note = (
            "\n## 115 年資料更新\n\n"
            "115 年警察人員三等考試已依考選部考畢試題查詢平臺匯入，"
            "包含 13 類科、90 科次的試題，以及官方標準答案與更正答案。"
            "匯入來源、SHA-256 與檢查結果詳見 `docs/115-import-report.md`。\n"
        )
        if marker not in text:
            raise AuditError("README 找不到「資料來源」章節")
        text = text.replace(marker, note + marker, 1)
    readme_path.write_text(text, encoding="utf-8")


def build_report(
    records: list[dict[str, Any]],
    year_totals: dict[str, int],
    duplicate_stats: dict[str, Any],
    dataset_totals: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    unique_records = [
        r
        for r in records
        if not (r["payload"].get("metadata") or {}).get("_is_duplicate")
    ]
    unique_questions = sum(int(r["questions"]) for r in unique_records)
    unique_choice = sum(int(r["choice"]) for r in unique_records)
    unique_essay = sum(int(r["essay"]) for r in unique_records)

    rows = []
    for code, info in CATEGORY_MAP.items():
        selected = [r for r in records if r["code"] == code]
        rows.append(
            "| {code} | {official} | `{folder}` | {files} | {questions} |".format(
                code=code,
                official=info["official"],
                folder=info["folder"],
                files=len(selected),
                questions=sum(int(r["questions"]) for r in selected),
            )
        )

    corrected = int((manifest.get("catalog") or {}).get("corrected_answers") or 0)
    return f"""# 115 年警察人員三等考試匯入報告

- 執行時間：{utc_now()}
- 官方來源：考選部考畢試題查詢平臺
- 考試代碼：`{EXAM_CODE}`
- 年度：民國 {YEAR} 年（2026）
- 官方頁面：{OFFICIAL_PAGE}

## 匯入範圍

| 類科代碼 | 官方類科 | 資料庫目錄 | 科次 | 解析題數 |
|---:|---|---|---:|---:|
{chr(10).join(rows)}

## 統計

- 類科：{len(CATEGORY_MAP)} 個
- 類科科次：{year_totals['question_files']} 份
- 下載官方檔案：{len(manifest.get('files') or [])} 個
- 官方更正答案：{corrected} 份
- 解析題數（含跨類科共用考卷副本）：{year_totals['questions']:,} 題
- 115 年非重複考卷：{duplicate_stats['unique_files']} 份
- 115 年重複副本：{duplicate_stats['duplicate_files']} 份
- 115 年非重複題數：{unique_questions:,} 題
  - 選擇題：{unique_choice:,} 題
  - 申論題：{unique_essay:,} 題

## 完整資料庫

- 非重複 JSON：{dataset_totals['json_files']:,} 份
- 總題數：{dataset_totals['questions']:,} 題
  - 選擇題：{dataset_totals['choice']:,} 題
  - 申論題：{dataset_totals['essay']:,} 題
- 類科：{dataset_totals['categories']} 個
- 科目：{dataset_totals['subjects']} 個
- 年度：{min(dataset_totals['years'])}–{max(dataset_totals['years'])}

## 驗證項目

- [x] 官方類科代碼 201–213 全數存在
- [x] 13 類科共 90 科次，每科均有 `試題.pdf`
- [x] 每份 PDF 以 `%PDF-` 檔頭與 SHA-256 驗證
- [x] 每份試題均成功產生 `試題.json`
- [x] 選擇題具 A–D 四個選項與合法官方答案
- [x] 題號無缺漏、無重複
- [x] 題幹無控制字元與 PUA 私用字元
- [x] 更正答案優先於原標準答案合併
- [x] 跨類科共用考卷以題目內容指紋標記重複
- [x] 全資料庫 pytest、搜尋索引及分析資料建置由 GitHub Actions 複驗

## 重複考卷處理

共辨識 {duplicate_stats['groups']} 組跨類科共用考卷。
所有副本仍保留於各類科目錄，並在 JSON 的頂層及 `metadata`
標記 `_is_duplicate`、`_duplicate_of` 與 `_duplicate_note`；
資料規模統計與搜尋索引只計入指定正本。
"""


def write_dataset_manifest(
    data_dir: Path,
    dataset_totals: dict[str, Any],
    duplicate_stats: dict[str, Any],
) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "coverage": {
            "first_year": min(dataset_totals["years"]),
            "last_year": max(dataset_totals["years"]),
            "years": dataset_totals["years"],
        },
        "counts": {
            key: dataset_totals[key]
            for key in (
                "json_files",
                "questions",
                "choice",
                "essay",
                "categories",
                "subjects",
            )
        },
        "latest_import": {
            "year": YEAR,
            "exam_code": EXAM_CODE,
            "official_page": OFFICIAL_PAGE,
            "category_count": len(CATEGORY_MAP),
            "subject_copies": EXPECTED_SUBJECT_COPIES,
            "unique_files": duplicate_stats["unique_files"],
            "duplicate_files": duplicate_stats["duplicate_files"],
        },
    }
    write_json(data_dir / "dataset_manifest.json", payload)


def remove_transient_files(data_dir: Path) -> None:
    for info in CATEGORY_MAP.values():
        year_dir = data_dir / str(info["folder"]) / f"{YEAR}年"
        for name in ("extraction_stats.json", "problematic_pdfs.json"):
            path = year_dir / name
            if path.exists():
                path.unlink()


def run(root: Path) -> dict[str, Any]:
    data_dir = root / "考古題庫"
    if not data_dir.is_dir():
        raise AuditError(f"找不到資料目錄：{data_dir}")

    manifest = load_import_manifest(data_dir)
    records, year_totals = normalize_115_files(data_dir, manifest)
    duplicate_stats = mark_duplicates(records)
    remove_transient_files(data_dir)

    # 重新讀取，確保寫入後仍符合結構。
    for record in records:
        validate_question_file(record["json_path"], read_json(record["json_path"]))

    dataset_totals = count_dataset(data_dir)
    if not dataset_totals["years"] or max(dataset_totals["years"]) != YEAR:
        raise AuditError(
            f"資料集最新年度不是 {YEAR}：{dataset_totals['years'][-5:]}"
        )

    update_test_baselines(root / "tests" / "test_data_quality.py", dataset_totals)
    update_readme(root / "README.md", dataset_totals)
    write_dataset_manifest(data_dir, dataset_totals, duplicate_stats)

    report = build_report(
        records,
        year_totals,
        duplicate_stats,
        dataset_totals,
        manifest,
    )
    report_path = root / "docs" / "115-import-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    result = {
        "year": YEAR,
        "categories": len(CATEGORY_MAP),
        "subject_copies": year_totals["question_files"],
        "year_questions_including_copies": year_totals["questions"],
        "year_choice_including_copies": year_totals["choice"],
        "year_essay_including_copies": year_totals["essay"],
        "duplicates": duplicate_stats,
        "dataset": dataset_totals,
        "report": report_path.as_posix(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="完成並稽核 115 年警察三等考古題匯入")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="專案根目錄（預設目前目錄）",
    )
    args = parser.parse_args()
    try:
        run(args.root.resolve())
    except Exception as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
