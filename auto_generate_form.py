#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CSV → Google Form 自動化工具

流程：
1. 讀取本地 questions.csv
2. 根據資料產生 Google Apps Script（Code.gs）
3. 透過 CLASP 將 Code.gs 推送至雲端
4. （可選）以 clasp run 觸發 createFormFromCSV()
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


DEFAULT_FORM_TITLE = "警察特考情境實務考古題"
DEFAULT_FORM_DESCRIPTION = "此表單用於練習警察特考情境實務考古題，請選擇最適合的選項。"

COLUMN_ALIASES: Dict[str, Sequence[str]] = {
    "year": ("year", "年份", "年度", "year別"),
    "number": ("number", "題號", "試題編號", "題目編號"),
    "title": ("title", "題目", "題幹", "試題內容", "question"),
    "option_a": ("option_a", "選項a", "選項A", "optiona", "A"),
    "option_b": ("option_b", "選項b", "選項B", "optionb", "B"),
    "option_c": ("option_c", "選項c", "選項C", "optionc", "C"),
    "option_d": ("option_d", "選項d", "選項D", "optiond", "D"),
    "answer": ("answer", "標準答案", "正確答案", "答案"),
}

TEMPLATE = """/**
 * ⚠️ 此檔案由 auto_generate_form.py 自動生成
 * ⚠️ 若需修改題目請更新 CSV 後重新執行腳本
 *
 * 生成時間：{timestamp}
 * 題目數量：{count}
 */

const QUESTIONS = {questions_json};

function createFormFromCSV() {{
  const total = QUESTIONS.length;
  console.log(`開始建立考古題表單，共 ${{
    total
  }} 題`);

  const form = FormApp.create('{form_title}');
  form.setTitle('{form_title}');
  form.setDescription('{form_description}');
  form.setShowLinkToRespondAgain(true);
  form.setIsQuiz(true);

  QUESTIONS.forEach((question, idx) => {{
    if (idx > 0 && idx % {questions_per_page} === 0) {{
      const page = Math.floor(idx / {questions_per_page}) + 1;
      form.addPageBreakItem().setTitle(`第 ${{
        page
      }} 頁`);
    }}

    const item = form.addMultipleChoiceItem();
    const trimmed = question.title.length > 500
      ? `${{question.title.substring(0, 497)}}...`
      : question.title;

    item
      .setTitle(`【${{question.year}}】${{question.number}}`)
      .setHelpText(trimmed);

    const optionMap = [
      {{ key: 'A', text: question.optionA }},
      {{ key: 'B', text: question.optionB }},
      {{ key: 'C', text: question.optionC }},
      {{ key: 'D', text: question.optionD }},
    ];

    const choices = optionMap
      .filter(opt => opt.text && opt.text.trim().length > 0)
      .map(opt => item.createChoice(opt.text, opt.key === question.answer));

    if (choices.length === 0) {{
      choices.push(item.createChoice('A', question.answer === 'A'));
      choices.push(item.createChoice('B', question.answer === 'B'));
      choices.push(item.createChoice('C', question.answer === 'C'));
      choices.push(item.createChoice('D', question.answer === 'D'));
    }}

    item.setChoices(choices);
    item.setRequired(true);
    item.setPoints(1);

    const feedback = FormApp.createFeedback().setText('請再確認題目敘述與參考答案。').build();
    item.setGeneralFeedback(feedback);
  }});

  console.log(`✅ 表單建立完成：${{ form.getEditUrl() }}`);
}}
"""


@dataclass(slots=True)
class Question:
    year: str
    number: str
    title: str
    answer: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str

    def to_payload(self) -> Dict[str, str]:
        return {
            "year": self.year,
            "number": self.number,
            "title": self.title,
            "answer": self.answer.upper(),
            "optionA": self.option_a,
            "optionB": self.option_b,
            "optionC": self.option_c,
            "optionD": self.option_d,
        }


@dataclass
class ImportReport:
    total_rows: int = 0
    imported: int = 0
    skipped: int = 0
    warnings: List[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV 轉 Google Form 自動化工具")
    parser.add_argument(
        "--csv",
        nargs="+",
        type=Path,
        metavar="CSV",
        default=[Path("questions.csv")],
        help="題目來源 CSV，可傳入多個檔案（預設：questions.csv）",
    )
    parser.add_argument(
        "--output",
        default=Path("src/Code.gs"),
        type=Path,
        help="輸出的 Google Apps Script 檔案（預設：src/Code.gs）",
    )
    parser.add_argument(
        "--form-title",
        default=DEFAULT_FORM_TITLE,
        help="建立的 Google Form 名稱（多檔時套用相同標題）",
    )
    parser.add_argument(
        "--form-description",
        default=DEFAULT_FORM_DESCRIPTION,
        help="表單描述文字，空白則使用預設說明",
    )
    parser.add_argument(
        "--questions-per-page",
        type=int,
        default=5,
        help="每頁題目的數量（預設：5）",
    )
    parser.add_argument(
        "--skip-push",
        action="store_true",
        help="僅生成 Code.gs，不執行 clasp push",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="完成 push 後執行 clasp run createFormFromCSV",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("form_generation_summary.json"),
        help="輸出匯總報告（JSON）的路徑，多檔時會依 CSV 另存檔名",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="處理多個 CSV 時即使其中一個失敗仍嘗試下一個",
    )
    return parser.parse_args()


def detect_columns(headers: Iterable[str]) -> Dict[str, str | None]:
    mapping: Dict[str, str | None] = {}
    normalized: Dict[str, str] = {}
    for header in headers or []:
        clean = (header or "").strip()
        if not clean:
            continue
        normalized.setdefault(clean.lower(), clean)

    def _resolve(aliases: Sequence[str]) -> str | None:
        for alias in aliases:
            key = alias.strip().lower()
            if key in normalized:
                return normalized[key]
        return None

    hard_required = ("title", "answer")
    soft_required = ("year", "number")
    optional_keys = ("option_a", "option_b", "option_c", "option_d")

    for key in hard_required:
        column = _resolve(COLUMN_ALIASES[key])
        if not column:
            raise ValueError(f"缺少必要欄位：{COLUMN_ALIASES[key]}")
        mapping[key] = column

    for key in soft_required:
        mapping[key] = _resolve(COLUMN_ALIASES[key])

    for key in optional_keys:
        mapping[key] = _resolve(COLUMN_ALIASES[key])

    return mapping


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def load_questions(csv_path: Path) -> tuple[List[Question], ImportReport]:
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到 CSV 檔案：{csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if not reader.fieldnames:
            raise ValueError("CSV 沒有找到標題列")
        column_map = detect_columns(reader.fieldnames)
        inferred_year = _infer_year_from_filename(csv_path)

        report = ImportReport()
        questions: List[Question] = []
        option_columns = {
            "A": column_map.get("option_a"),
            "B": column_map.get("option_b"),
            "C": column_map.get("option_c"),
            "D": column_map.get("option_d"),
        }
        missing_year_column = column_map.get("year") is None
        missing_number_column = column_map.get("number") is None
        year_notice_logged = False
        number_notice_logged = False

        for idx, row in enumerate(reader, start=2):
            report.total_rows += 1
            raw_title = row.get(column_map["title"], "") or ""
            title_clean = raw_title.strip()

            if not title_clean:
                report.skipped += 1
                report.warn(f"第 {idx} 行缺少題目內容")
                continue

            options: Dict[str, str] = {}
            missing_option = False
            for letter, column in option_columns.items():
                value = normalize_text(row.get(column, "")) if column else ""
                options[letter] = value
                if not value:
                    missing_option = True

            parsed_question = title_clean
            parsed_options: Dict[str, str] = {}
            if missing_option or not any(option_columns.values()):
                parsed_question, parsed_options = _split_question_and_options(raw_title)
                if parsed_question:
                    parsed_question = parsed_question.strip()
                if parsed_options:
                    for letter in ("A", "B", "C", "D"):
                        if not options[letter]:
                            options[letter] = normalize_text(parsed_options.get(letter, ""))

            if not parsed_question:
                report.skipped += 1
                report.warn(f"第 {idx} 行題幹無法解析")
                continue

            if any(not options[letter] for letter in ("A", "B", "C", "D")):
                report.skipped += 1
                report.warn(f"第 {idx} 行缺少 A-D 選項")
                continue

            year_value = (
                (row.get(column_map["year"], "") or "").strip()
                if column_map.get("year")
                else ""
            )
            if not year_value:
                year_value = inferred_year or ""
            if not year_value:
                year_value = "N/A"
            elif missing_year_column and not year_notice_logged:
                report.warn(f"缺少年份欄位，已改用檔名推斷值：{year_value}")
                year_notice_logged = True

            number_value = (
                (row.get(column_map["number"], "") or "").strip()
                if column_map.get("number")
                else ""
            )
            if not number_value:
                number_value = str(idx - 1)
                if missing_number_column and not number_notice_logged:
                    report.warn("缺少題號欄位，已改用列序號")
                    number_notice_logged = True

            answer = (
                (row.get(column_map["answer"], "") or "").strip().upper()
                if column_map.get("answer")
                else ""
            )
            if answer not in {"A", "B", "C", "D"}:
                report.warn(f"第 {idx} 行答案格式不正確（{answer or '空白'}），已預設為 A")
                answer = "A"

            questions.append(
                Question(
                    year=year_value,
                    number=number_value,
                    title=parsed_question,
                    answer=answer,
                    option_a=options["A"],
                    option_b=options["B"],
                    option_c=options["C"],
                    option_d=options["D"],
                )
            )
            report.imported += 1

    if not questions:
        raise ValueError("CSV 內沒有有效題目")
    return questions, report


OPTION_SYMBOL_MAP = {
    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
    "a": "A",
    "b": "B",
    "c": "C",
    "d": "D",
    "": "A",
    "": "B",
    "": "C",
    "": "D",
}

OPTION_PATTERN = re.compile(rf"^([{''.join(OPTION_SYMBOL_MAP.keys())}])[\)\.、．\s]*")


def _infer_year_from_filename(csv_path: Path) -> str:
    match = re.search(r"(\d{3,4})年", csv_path.stem)
    if match:
        return match.group(1)
    return ""


def _split_question_and_options(raw_text: str) -> tuple[str, Dict[str, str]]:
    lines = [line.strip() for line in raw_text.replace("\r", "\n").split("\n") if line.strip()]
    if not lines:
        return "", {}

    option_start = next(
        (idx for idx, line in enumerate(lines) if OPTION_PATTERN.match(line)),
        None,
    )
    if option_start is None:
        return "", {}

    question_text = " ".join(lines[:option_start]).strip()
    question_text = re.sub(r"^\d+[\.、]?\s*", "", question_text).strip()

    options: Dict[str, List[str]] = {"A": [], "B": [], "C": [], "D": []}
    current_key: str | None = None

    for line in lines[option_start:]:
        match = OPTION_PATTERN.match(line)
        if match:
            symbol = match.group(1)
            letter = OPTION_SYMBOL_MAP.get(symbol, symbol.upper())
            current_key = letter if letter in options else None
            content = OPTION_PATTERN.sub("", line, count=1).strip()
            if current_key:
                options[current_key] = [content] if content else []
        elif current_key:
            options[current_key].append(line)

    normalized_options = {
        key: " ".join(parts).strip() for key, parts in options.items() if parts
    }

    return question_text, normalized_options


def render_gas(
    questions: Sequence[Question],
    *,
    form_title: str,
    form_description: str,
    questions_per_page: int,
) -> str:
    payload = [q.to_payload() for q in questions]
    questions_json = json.dumps(payload, ensure_ascii=False, indent=2)

    from datetime import datetime

    return TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        count=len(payload),
        questions_json=questions_json,
        form_title=form_title,
        form_description=form_description.replace("\n", "\\n"),
        questions_per_page=max(1, questions_per_page),
    )


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_command(command: Sequence[str], description: str, timeout: int = 60) -> bool:
    binary = command[0]
    resolved = shutil.which(binary)
    if not resolved:
        print(f"   ❌ 找不到指令：{binary}")
        return False

    try:
        print(f"➡️  {description}: {' '.join(command)}")
        completed = subprocess.run(
            [resolved, *command[1:]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        if completed.returncode == 0:
            print(f"   ✅ {description} 完成")
            if completed.stdout.strip():
                print(completed.stdout.strip())
            return True
        print(f"   ❌ {description} 失敗：{completed.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print(f"   ❌ {description} 超時")
        return False


def _print_import_report(report: ImportReport) -> None:
    print("\n📊 匯入統計")
    print(f"  • 原始列數：{report.total_rows}")
    print(f"  • 成功匯入：{report.imported}")
    print(f"  • 已跳過：{report.skipped}")
    if report.warnings:
        print("⚠️ 注意事項：")
        for warning in report.warnings[:10]:
            print(f"   - {warning}")
        if len(report.warnings) > 10:
            print(f"   ... 尚有 {len(report.warnings) - 10} 則警告")


def _write_summary_report(
    report_path: Path,
    csv_path: Path,
    output_path: Path,
    total_questions: int,
    report: ImportReport,
) -> None:
    payload = {
        "csv_source": str(csv_path),
        "output_script": str(output_path),
        "total_questions": total_questions,
        "stats": {
            "total_rows": report.total_rows,
            "imported": report.imported,
            "skipped": report.skipped,
        },
        "warnings": report.warnings,
    }
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📝 匯總報告：{report_path}")
    except Exception as exc:  # pragma: no cover - best effort
        print(f"⚠️ 無法寫入報告：{exc}")


def _derive_report_path(base_path: Path, csv_path: Path, multi_csv: bool) -> Path:
    if not multi_csv:
        return base_path
    if base_path.suffix:
        return base_path.with_name(f"{base_path.stem}_{csv_path.stem}{base_path.suffix}")
    suffix = base_path.suffix or ".json"
    return base_path / f"{csv_path.stem}{suffix}"


def _process_single_csv(
    csv_path: Path,
    args: argparse.Namespace,
    *,
    multi_csv: bool,
    clasp_available: bool,
) -> bool:
    try:
        questions, import_report = load_questions(csv_path)
    except Exception as exc:
        print(f"❌ 讀取 CSV 失敗（{csv_path}）：{exc}")
        return False

    gas_content = render_gas(
        questions,
        form_title=args.form_title,
        form_description=args.form_description,
        questions_per_page=args.questions_per_page,
    )

    write_file(args.output, gas_content)
    print(f"💾 已生成 Apps Script：{args.output}")
    _print_import_report(import_report)

    summary_path = _derive_report_path(args.report, csv_path, multi_csv)
    _write_summary_report(summary_path, csv_path, args.output, len(questions), import_report)

    should_push = clasp_available and not args.skip_push
    if not should_push:
        return True

    if not run_command(["clasp", "push", "--force"], f"CLASP Push（{csv_path.stem}）"):
        return False

    if args.run and not run_command(
        ["clasp", "run", "createFormFromCSV"],
        f"clasp run createFormFromCSV（{csv_path.stem}）",
    ):
        return False

    return True


def main() -> None:
    args = parse_args()

    csv_files = [Path(path) for path in args.csv]
    multi_csv = len(csv_files) > 1

    clasp_project = Path(".clasp.json")
    clasp_available = clasp_project.exists()
    if not clasp_available and not args.skip_push:
        print("⚠️ 找不到 .clasp.json，將僅生成 Apps Script 與報告，略過 push/run")
    elif args.skip_push and args.run:
        print("⚠️ 已設定 --skip-push，將同時略過 clasp run")

    overall_success = True
    total_files = len(csv_files)
    for idx, csv_path in enumerate(csv_files, start=1):
        print(f"\n=== [{idx}/{total_files}] 處理 {csv_path} ===")
        ok = _process_single_csv(
            csv_path,
            args,
            multi_csv=multi_csv,
            clasp_available=clasp_available,
        )
        if not ok:
            overall_success = False
            if not args.continue_on_error:
                break

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
