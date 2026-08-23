#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依 115 年考選部原卷宣告的測驗題數校正解析結果。

PDF 文字抽取偶爾會把題幹中的數字誤認為新題號（例如「40 倍」→ 第 40 題）。
本工具從同目錄的官方「試題.pdf」讀取「共 N 題」宣告，只允許 1..N 的
choice 題號；超出宣告範圍者視為解析假題移除，而宣告範圍內若仍缺題則
立即失敗，避免靜默遺失真正考題。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


_DECLARED_COUNT_RE = re.compile(r"共\s*(\d{1,3})\s*題")


def read_declared_count(pdf_path: Path) -> int | None:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - CI installs pdfplumber
        raise RuntimeError("需要 pdfplumber 才能核對官方題數") from exc

    with pdfplumber.open(str(pdf_path)) as pdf:
        # 題數宣告通常在第一頁；讀前兩頁提高容錯。
        text = "\n".join((page.extract_text() or "") for page in pdf.pages[:2])
    matches = [int(value) for value in _DECLARED_COUNT_RE.findall(text)]
    if not matches:
        return None

    # 若同頁另有非本科目的說明，選擇合理的最大宣告值；實際警察考卷
    # 測驗題通常為 20~60 題，且題號自 1 起算。
    candidates = [value for value in matches if 1 <= value <= 100]
    return max(candidates) if candidates else None


def normalize_one(json_path: Path) -> dict[str, Any] | None:
    pdf_path = json_path.with_name("試題.pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"缺少官方試題 PDF：{pdf_path}")

    declared = read_declared_count(pdf_path)
    if declared is None:
        # 純申論科目沒有「共 N 題」宣告，不處理。
        return None

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        raise RuntimeError(f"questions 格式錯誤：{json_path}")

    kept = []
    removed: list[int] = []
    for question in questions:
        if question.get("type") != "choice":
            kept.append(question)
            continue
        number = question.get("number")
        if isinstance(number, int) and not (1 <= number <= declared):
            removed.append(number)
            continue
        kept.append(question)

    actual = sorted(
        {
            q.get("number")
            for q in kept
            if q.get("type") == "choice" and isinstance(q.get("number"), int)
        }
    )
    expected = list(range(1, declared + 1))
    missing = sorted(set(expected) - set(actual))
    duplicates: list[int] = []
    seen: set[int] = set()
    for q in kept:
        if q.get("type") != "choice" or not isinstance(q.get("number"), int):
            continue
        number = q["number"]
        if number in seen:
            duplicates.append(number)
        seen.add(number)

    if missing or duplicates:
        raise RuntimeError(
            f"官方宣告 {declared} 題但解析仍不完整：{json_path}；"
            f"缺題={missing}，重複={sorted(set(duplicates))}"
        )

    if removed:
        payload["questions"] = kept
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "file": json_path.as_posix(),
        "declared": declared,
        "choice_questions": len(actual),
        "removed_out_of_range": sorted(removed),
    }


def run(root: Path) -> dict[str, Any]:
    files = sorted(root.glob("*/115年/*/試題.json"))
    if not files:
        raise RuntimeError(f"找不到 115 年試題 JSON：{root}")

    checked = 0
    removed_total = 0
    changed: list[dict[str, Any]] = []
    for path in files:
        result = normalize_one(path)
        if result is None:
            continue
        checked += 1
        removed = result["removed_out_of_range"]
        if removed:
            removed_total += len(removed)
            changed.append(result)
            print(
                f"校正 {path}：官方 {result['declared']} 題，"
                f"移除越界假題 {removed}"
            )

    print(
        f"官方題數核對完成：掃描 {len(files)} 份 JSON，"
        f"核對 {checked} 份測驗卷，移除 {removed_total} 個越界假題"
    )
    return {
        "files_scanned": len(files),
        "choice_papers_checked": checked,
        "removed_out_of_range": removed_total,
        "changed": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="核對 115 年官方測驗題數")
    parser.add_argument("--root", type=Path, default=Path("考古題庫"))
    args = parser.parse_args()
    try:
        run(args.root)
    except Exception as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
