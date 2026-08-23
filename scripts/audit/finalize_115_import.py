#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""完成並稽核民國 115 年三等警察特考資料匯入。

此工具只在下載與 PDF 解析完成後執行。它會：
1. 驗證 13 類科、90 份科目副本及官方 PDF/JSON。
2. 核對一般答案與更正答案，確認所有選擇題都有合法答案。
3. 標記 115 年跨類科共用考卷，避免搜尋索引重複計數。
4. 凍結資料規模到測試、README、dataset manifest 與匯入報告。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "考古題庫"
YEAR = 115
YEAR_DIR_NAME = "115年"
OFFICIAL_URL = (
    "https://wwwq.moex.gov.tw/exam/"
    "wFrmExamQandASearch.aspx?e=115060&y=2026"
)

EXPECTED_CATEGORIES = [
    "行政警察學系",
    "外事警察學系",
    "刑事警察學系",
    "公共安全學系社安組",
    "犯罪防治學系預防組",
    "消防學系",
    "交通學系交通組",
    "資訊管理學系",
    "鑑識科學學系",
    "國境警察學系境管組",
    "水上警察學系",
    "法律學系",
    "行政管理學系",
]
EXPECTED_SUBJECT_COPIES = 90
EXPECTED_CORRECTED_PDFS = 4
EXPECTED_CORRECTION_VALUES = Counter({
    "A或C": 1,
    "A或C或D": 1,
    "B": 1,
    "送分": 2,
})
ANSWER_RE = re.compile(r"(?:[A-D](?:或[A-D]){0,3}|送分)\Z")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
PUA_RE = re.compile(r"[\ue000-\uf8ff]")


class AuditFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise AuditFailure(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"JSON 無法讀取：{path.relative_to(ROOT)}：{exc}")
    if not isinstance(value, dict):
        fail(f"JSON 根節點不是物件：{path.relative_to(ROOT)}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def valid_pdf(path: Path) -> bool:
    try:
        return path.stat().st_size > 1024 and path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def all_text_fields(question: Dict[str, Any]) -> Iterable[str]:
    for key in ("stem", "passage"):
        value = question.get(key)
        if isinstance(value, str):
            yield value
    options = question.get("options")
    if isinstance(options, dict):
        for value in options.values():
            yield str(value)


def normalize_document(
    path: Path,
    document: Dict[str, Any],
    category: str,
    subject: str,
) -> Dict[str, Any]:
    document["year"] = YEAR
    document["category"] = category
    document["subject"] = subject

    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        document["metadata"] = metadata
    metadata["year"] = YEAR
    metadata["category"] = category
    metadata["subject"] = subject
    metadata["source_page"] = OFFICIAL_URL

    question_pdf = path.parent / "試題.pdf"
    metadata["source_pdf_sha256"] = sha256(question_pdf)
    document["source_pdf"] = question_pdf.relative_to(ROOT).as_posix()
    document["source_page"] = OFFICIAL_URL
    return document


def validate_questions(path: Path, document: Dict[str, Any]) -> Dict[str, int]:
    questions = document.get("questions")
    if not isinstance(questions, list) or not questions:
        fail(f"沒有題目：{path.relative_to(ROOT)}")

    choice_numbers: List[int] = []
    choice = 0
    essay = 0
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            fail(f"第 {index} 筆題目不是物件：{path.relative_to(ROOT)}")
        qtype = question.get("type")
        if qtype == "choice":
            choice += 1
            number = question.get("number")
            if not isinstance(number, int):
                fail(f"選擇題題號不是整數：{path.relative_to(ROOT)} #{number}")
            choice_numbers.append(number)
            options = question.get("options")
            if not isinstance(options, dict) or set(options) != set("ABCD"):
                fail(f"選項不完整：{path.relative_to(ROOT)} #{number}")
            answer = question.get("answer")
            if not isinstance(answer, str) or not ANSWER_RE.fullmatch(answer):
                fail(
                    f"答案缺漏或格式不合法：{path.relative_to(ROOT)} "
                    f"#{number}={answer!r}"
                )
            stem = str(question.get("stem") or "").strip()
            passage = str(question.get("passage") or "").strip()
            if not stem and not passage:
                fail(f"空題幹且無段落：{path.relative_to(ROOT)} #{number}")
        elif qtype == "essay":
            essay += 1
            if not str(question.get("stem") or "").strip():
                fail(f"申論題題幹為空：{path.relative_to(ROOT)} #{index}")
        else:
            fail(f"未知題型：{path.relative_to(ROOT)} #{index}={qtype!r}")

        for text in all_text_fields(question):
            if CONTROL_RE.search(text):
                fail(f"含控制字元：{path.relative_to(ROOT)} #{index}")
            if PUA_RE.search(text):
                fail(f"含 PUA 私用字元：{path.relative_to(ROOT)} #{index}")

    if choice_numbers:
        if len(choice_numbers) != len(set(choice_numbers)):
            fail(f"選擇題號重複：{path.relative_to(ROOT)}")
        expected = list(range(min(choice_numbers), max(choice_numbers) + 1))
        if sorted(choice_numbers) != expected:
            fail(f"選擇題號不連續：{path.relative_to(ROOT)}")

    return {"questions": len(questions), "choice": choice, "essay": essay}


def correction_entries(corrected_pdf: Path) -> Dict[int, str]:
    try:
        import pdfplumber
        from scripts.parse.answer_extractor import _parse_correction_notes
    except ImportError as exc:
        fail(f"缺少答案稽核依賴：{exc}")

    text_parts: List[str] = []
    try:
        with pdfplumber.open(str(corrected_pdf)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
    except Exception as exc:
        fail(f"更正答案 PDF 無法讀取：{corrected_pdf.relative_to(ROOT)}：{exc}")
    return _parse_correction_notes("\n".join(text_parts))


def audit_year() -> Tuple[List[Path], Dict[str, Any]]:
    category_dirs = [
        DATA_DIR / category / YEAR_DIR_NAME for category in EXPECTED_CATEGORIES
    ]
    missing = [path for path in category_dirs if not path.is_dir()]
    if missing:
        fail("缺少 115 年類科目錄：" + ", ".join(p.parent.name for p in missing))

    unexpected = sorted(
        path.parent.name
        for path in DATA_DIR.glob(f"*/{YEAR_DIR_NAME}")
        if path.parent.name not in EXPECTED_CATEGORIES
    )
    if unexpected:
        fail("出現未預期的 115 年類科：" + ", ".join(unexpected))

    subject_dirs = sorted(
        path
        for category_dir in category_dirs
        for path in category_dir.iterdir()
        if path.is_dir()
    )
    if len(subject_dirs) != EXPECTED_SUBJECT_COPIES:
        fail(
            f"115 年科目副本應為 {EXPECTED_SUBJECT_COPIES}，"
            f"實際 {len(subject_dirs)}"
        )

    pdf_count = 0
    corrected_pdfs: List[Path] = []
    json_paths: List[Path] = []
    year_counts = Counter()
    quality_warnings: List[Dict[str, Any]] = []

    for subject_dir in subject_dirs:
        category = subject_dir.parent.parent.name
        subject = subject_dir.name
        question_pdf = subject_dir / "試題.pdf"
        json_path = subject_dir / "試題.json"
        if not valid_pdf(question_pdf):
            fail(f"試題 PDF 缺漏或損壞：{question_pdf.relative_to(ROOT)}")
        if not json_path.is_file():
            fail(f"試題 JSON 缺漏：{json_path.relative_to(ROOT)}")

        for pdf_path in subject_dir.glob("*.pdf"):
            if not valid_pdf(pdf_path):
                fail(f"PDF 缺漏或損壞：{pdf_path.relative_to(ROOT)}")
            pdf_count += 1
        corrected = subject_dir / "更正答案.pdf"
        if corrected.exists():
            corrected_pdfs.append(corrected)

        document = normalize_document(
            json_path,
            load_json(json_path),
            category,
            subject,
        )
        counts = validate_questions(json_path, document)
        year_counts.update(counts)

        quality = document.get("_quality")
        if isinstance(quality, dict):
            try:
                score = float(quality.get("score", 1.0))
            except (TypeError, ValueError):
                score = 0.0
            if score < 0.7:
                quality_warnings.append({
                    "path": json_path.relative_to(ROOT).as_posix(),
                    "score": score,
                    "issues": quality.get("issues", []),
                })

        write_json(json_path, document)
        json_paths.append(json_path)

    if len(corrected_pdfs) != EXPECTED_CORRECTED_PDFS:
        fail(
            f"更正答案 PDF 應為 {EXPECTED_CORRECTED_PDFS}，"
            f"實際 {len(corrected_pdfs)}"
        )

    correction_values = Counter()
    correction_rows: List[Dict[str, Any]] = []
    for corrected_pdf in corrected_pdfs:
        entries = correction_entries(corrected_pdf)
        if not entries:
            fail(f"無法解析更正內容：{corrected_pdf.relative_to(ROOT)}")
        document = load_json(corrected_pdf.parent / "試題.json")
        by_number = {
            q.get("number"): q
            for q in document.get("questions", [])
            if isinstance(q, dict) and q.get("type") == "choice"
        }
        for number, answer in sorted(entries.items()):
            actual = (by_number.get(number) or {}).get("answer")
            if actual != answer:
                fail(
                    f"更正答案未套用：{corrected_pdf.relative_to(ROOT)} "
                    f"#{number} 應為 {answer}，實際 {actual!r}"
                )
            correction_values[answer] += 1
            correction_rows.append({
                "path": corrected_pdf.relative_to(ROOT).as_posix(),
                "question": number,
                "answer": answer,
            })

    if correction_values != EXPECTED_CORRECTION_VALUES:
        fail(
            "更正答案內容與官方預期不符："
            f"應為 {dict(EXPECTED_CORRECTION_VALUES)}，"
            f"實際 {dict(correction_values)}"
        )

    return json_paths, {
        "categories": len(category_dirs),
        "subject_copies": len(subject_dirs),
        "pdf_files": pdf_count,
        "json_files": len(json_paths),
        "questions": year_counts["questions"],
        "choice": year_counts["choice"],
        "essay": year_counts["essay"],
        "corrected_answer_pdfs": len(corrected_pdfs),
        "corrections": correction_rows,
        "quality_warnings": quality_warnings,
    }


def question_fingerprint(document: Dict[str, Any]) -> str:
    payload = json.dumps(
        document.get("questions", []),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mark_115_duplicates(json_paths: List[Path]) -> Dict[str, Any]:
    groups: Dict[Tuple[str, str], List[Tuple[Path, Dict[str, Any]]]] = defaultdict(list)
    category_order = {name: index for index, name in enumerate(EXPECTED_CATEGORIES)}

    for path in json_paths:
        document = load_json(path)
        metadata = document.setdefault("metadata", {})
        for key in ("_is_duplicate", "_duplicate_of", "_duplicate_note"):
            document.pop(key, None)
            metadata.pop(key, None)
        key = (path.parent.name, question_fingerprint(document))
        groups[key].append((path, document))

    duplicate_files = 0
    duplicate_groups = 0
    canonical_rows: List[Dict[str, Any]] = []
    for (_, fingerprint), items in groups.items():
        items.sort(
            key=lambda item: (
                category_order.get(item[0].parent.parent.parent.name, 999),
                item[0].as_posix(),
            )
        )
        canonical_path, canonical_doc = items[0]
        write_json(canonical_path, canonical_doc)
        if len(items) == 1:
            continue

        duplicate_groups += 1
        canonical_subject_dir = canonical_path.parent.relative_to(DATA_DIR).as_posix()
        duplicates: List[str] = []
        for path, document in items[1:]:
            metadata = document.setdefault("metadata", {})
            note = "與另一類科共用同一份 115 年官方考卷"
            document["_is_duplicate"] = True
            document["_duplicate_of"] = canonical_subject_dir
            document["_duplicate_note"] = note
            metadata["_is_duplicate"] = True
            metadata["_duplicate_of"] = canonical_subject_dir
            metadata["_duplicate_note"] = note
            write_json(path, document)
            duplicates.append(path.parent.relative_to(DATA_DIR).as_posix())
            duplicate_files += 1
        canonical_rows.append({
            "subject": canonical_path.parent.name,
            "fingerprint": fingerprint,
            "canonical": canonical_subject_dir,
            "duplicates": duplicates,
        })

    return {
        "groups": duplicate_groups,
        "duplicate_files": duplicate_files,
        "details": canonical_rows,
    }


def dataset_counts() -> Dict[str, Any]:
    files = 0
    questions = 0
    choice = 0
    essay = 0
    categories = set()
    subjects = set()
    years = set()

    for path in sorted(DATA_DIR.glob("**/試題.json")):
        document = load_json(path)
        metadata = document.get("metadata") or {}
        if document.get("_is_duplicate") or metadata.get("_is_duplicate"):
            continue
        files += 1
        category = document.get("category") or path.relative_to(DATA_DIR).parts[0]
        subject = document.get("subject") or path.parent.name
        year = document.get("year")
        if not isinstance(year, int):
            match = re.fullmatch(r"(\d{3})年", path.parent.parent.name)
            year = int(match.group(1)) if match else None
        categories.add(category)
        subjects.add(subject)
        if year:
            years.add(year)
        for question in document.get("questions", []):
            questions += 1
            if question.get("type") == "choice":
                choice += 1
            elif question.get("type") == "essay":
                essay += 1

    if not years or max(years) != YEAR:
        fail(f"資料年份未延伸至 {YEAR} 年")
    return {
        "files": files,
        "questions": questions,
        "choice": choice,
        "essay": essay,
        "categories": len(categories),
        "subjects": len(subjects),
        "years": sorted(years),
    }


def update_quality_tests(counts: Dict[str, Any]) -> None:
    path = ROOT / "tests" / "test_data_quality.py"
    text = path.read_text(encoding="utf-8")
    replacements = {
        r"assert len\(ALL_FILES\) == \d+": f"assert len(ALL_FILES) == {counts['files']}",
        r"assert len\(ALL_QUESTIONS\) == \d+": (
            f"assert len(ALL_QUESTIONS) == {counts['questions']}"
        ),
        r"assert len\(CHOICE_QUESTIONS\) == \d+": (
            f"assert len(CHOICE_QUESTIONS) == {counts['choice']}"
        ),
        r"assert len\(ESSAY_QUESTIONS\) == \d+": (
            f"assert len(ESSAY_QUESTIONS) == {counts['essay']}"
        ),
    }
    for pattern, replacement in replacements.items():
        text, changed = re.subn(pattern, replacement, text, count=1)
        if changed != 1:
            fail(f"無法更新資料規模測試：{pattern}")

    text = re.sub(
        r"預期 \d+ 個非重複檔案",
        f"預期 {counts['files']} 個非重複檔案",
        text,
        count=1,
    )
    text = re.sub(
        r"預期 \d+ 題",
        f"預期 {counts['questions']} 題",
        text,
        count=1,
    )
    text = re.sub(
        r"預期 \d+ 選擇題",
        f"預期 {counts['choice']} 選擇題",
        text,
        count=1,
    )
    text = re.sub(
        r"預期 \d+ 申論題",
        f"預期 {counts['essay']} 申論題",
        text,
        count=1,
    )

    old = """        valid_answers = {'A', 'B', 'C', 'D', '送分', 'C或D'}
        invalid = []
        for fp, q in CHOICE_QUESTIONS:
            ans = q.get('answer', '')
            if ans not in valid_answers:
                invalid.append((fp, q.get('number'), ans))"""
    new = """        valid_answer = re.compile(r'(?:[A-D](?:或[A-D]){0,3}|送分)\\Z')
        invalid = []
        for fp, q in CHOICE_QUESTIONS:
            ans = q.get('answer', '')
            if not isinstance(ans, str) or not valid_answer.fullmatch(ans):
                invalid.append((fp, q.get('number'), ans))"""
    if old in text:
        text = text.replace(old, new, 1)
    elif "valid_answer = re.compile" not in text:
        fail("無法更新合法答案測試")
    path.write_text(text, encoding="utf-8")


def write_115_regression_test() -> None:
    path = ROOT / "tests" / "test_115_import.py"
    categories_literal = json.dumps(EXPECTED_CATEGORIES, ensure_ascii=False, indent=4)
    content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""民國 115 年三等警察特考匯入回歸測試。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "考古題庫"
EXPECTED_CATEGORIES = {categories_literal}


def test_115_category_and_subject_coverage():
    dirs = [DATA / category / "115年" for category in EXPECTED_CATEGORIES]
    assert all(path.is_dir() for path in dirs)
    subjects = [child for path in dirs for child in path.iterdir() if child.is_dir()]
    assert len(subjects) == 90
    assert all((path / "試題.pdf").is_file() for path in subjects)
    assert all((path / "試題.json").is_file() for path in subjects)


def test_115_json_nonempty_and_answers_present():
    for path in DATA.glob("*/115年/*/試題.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document.get("year") == 115
        questions = document.get("questions", [])
        assert questions
        for question in questions:
            if question.get("type") == "choice":
                assert question.get("answer")
                assert set(question.get("options", {{}})) == set("ABCD")


def test_115_official_corrections_are_preserved():
    values = []
    for path in DATA.glob("*/115年/*/試題.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if (path.parent / "更正答案.pdf").exists():
            values.extend(
                question.get("answer")
                for question in document.get("questions", [])
                if question.get("type") == "choice"
                and question.get("answer") not in {{"A", "B", "C", "D"}}
            )
    assert "A或C" in values
    assert "A或C或D" in values
    assert values.count("送分") >= 2


def test_115_corrected_pdf_count():
    assert len(list(DATA.glob("*/115年/*/更正答案.pdf"))) == 4
'''
    path.write_text(content, encoding="utf-8")


def update_readme(counts: Dict[str, Any]) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("106-114 年（2017-2025）", "106-115 年（2017-2026）")
    text = text.replace("106-114 年（9 年）", "106-115 年（10 年）")
    text = re.sub(
        r"\| 學系/類別 \| [^|]+ \|",
        f"| 學系/類別 | {counts['categories']} 個 |",
        text,
        count=1,
    )
    text = re.sub(
        r"\| 科目 \| [^|]+ \|",
        f"| 科目 | {counts['subjects']} 個 |",
        text,
        count=1,
    )
    text = re.sub(
        r"\| JSON 檔案 \| [^|]+ \|",
        f"| JSON 檔案 | {counts['files']:,} 個（非重複） |",
        text,
        count=1,
    )
    text = re.sub(
        r"\| 選擇題 \| [^|]+ \|",
        f"| 選擇題 | {counts['choice']:,} 題 |",
        text,
        count=1,
    )
    text = re.sub(
        r"\| 申論題 \| [^|]+ \|",
        f"| 申論題 | {counts['essay']:,} 題 |",
        text,
        count=1,
    )
    text = re.sub(
        r"\| 總題數 \| [^|]+ \|",
        f"| 總題數 | {counts['questions']:,} 題 |",
        text,
        count=1,
    )
    text = re.sub(
        r"選項完整率\*\*: [\d,]+/[\d,]+",
        f"選項完整率**: {counts['choice']:,}/{counts['choice']:,}",
        text,
        count=1,
    )
    text = re.sub(
        r"答案合法率\*\*: [\d,]+/[\d,]+",
        f"答案合法率**: {counts['choice']:,}/{counts['choice']:,}",
        text,
        count=1,
    )
    text = re.sub(
        r"\([\d,]+ 題全文搜尋\)",
        f"({counts['questions']:,} 題全文搜尋)",
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")


def write_outputs(
    year_stats: Dict[str, Any],
    duplicate_stats: Dict[str, Any],
    counts: Dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "schema_version": 1,
        "generated_at": now,
        "source": OFFICIAL_URL,
        "coverage": {
            "min_year": min(counts["years"]),
            "max_year": max(counts["years"]),
            "years": counts["years"],
        },
        "counts": {key: counts[key] for key in (
            "files", "questions", "choice", "essay", "categories", "subjects"
        )},
        "year_115": year_stats,
        "year_115_duplicates": duplicate_stats,
    }
    write_json(DATA_DIR / "dataset_manifest.json", manifest)

    corrections = "\n".join(
        f"- `{row['path']}`：第 {row['question']} 題 → `{row['answer']}`"
        for row in year_stats["corrections"]
    )
    warnings = year_stats["quality_warnings"]
    warning_text = (
        "無。"
        if not warnings
        else "\n".join(
            f"- `{row['path']}`：quality={row['score']}，issues={row['issues']}"
            for row in warnings
        )
    )
    report = f"""# 115 年三等警察特考匯入稽核報告

- 產生時間：{now}
- 官方來源：考選部 115 年警察人員考試頁面
- 匯入類科：{year_stats['categories']} 個
- 科目副本：{year_stats['subject_copies']} 份
- 官方 PDF：{year_stats['pdf_files']} 份
- 試題 JSON：{year_stats['json_files']} 份
- 題目副本總數：{year_stats['questions']:,} 題
  - 選擇題：{year_stats['choice']:,} 題
  - 申論題：{year_stats['essay']:,} 題
- 更正答案 PDF：{year_stats['corrected_answer_pdfs']} 份
- 共用考卷群組：{duplicate_stats['groups']} 組
- 排除重複副本：{duplicate_stats['duplicate_files']} 份

## 官方更正答案核對

{corrections}

## 全資料庫（排除重複）

- 年度：{min(counts['years'])}–{max(counts['years'])}
- JSON 考卷：{counts['files']:,} 份
- 總題數：{counts['questions']:,} 題
- 選擇題：{counts['choice']:,} 題
- 申論題：{counts['essay']:,} 題
- 類科：{counts['categories']} 個
- 科目：{counts['subjects']} 個

## 低於 0.7 的解析品質提示

{warning_text}

## 驗證結論

通過目錄覆蓋、PDF 完整性、JSON 結構、題號連續性、四選項完整性、答案合法性、官方更正答案一致性與跨類科重複標記檢查。完整 pytest 與前端索引建置由 GitHub Actions 接續執行。
"""
    report_path = ROOT / "docs" / "115-import-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def main() -> int:
    try:
        json_paths, year_stats = audit_year()
        duplicate_stats = mark_115_duplicates(json_paths)
        counts = dataset_counts()
        update_quality_tests(counts)
        write_115_regression_test()
        update_readme(counts)
        write_outputs(year_stats, duplicate_stats, counts)
    except AuditFailure as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return 1

    print("115 年匯入稽核完成")
    print(json.dumps({
        "year_115": year_stats,
        "duplicates": {
            "groups": duplicate_stats["groups"],
            "duplicate_files": duplicate_stats["duplicate_files"],
        },
        "dataset": counts,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
