#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清除 115 年 PDF 換段時誤併入題目文字的頁面 metadata。

僅處理題目的 stem、passage 與 options；不會修改 sections、題號、答案或正文。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "考古題庫"

# 115 年國文共同試題的第二題尾端會被 pdfplumber 併入：
#   乙、測驗部分:(20 分) 代號:1201
# 同時涵蓋全形／半形括號、冒號及不規則空格。
TEST_SECTION_RE = re.compile(
    r"(?:[-－]\s*)*"
    r"乙\s*、\s*測驗(?:題)?(?:部分)?\s*[:：]?\s*"
    r"[（(]?\s*\d+\s*分\s*[）)]?",
)
CODE_RE = re.compile(r"代號\s*[:：]\s*\d{4,6}")
PAGE_RE = re.compile(r"頁次\s*[:：]\s*\d+\s*[－-]\s*\d+")


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = TEST_SECTION_RE.sub(" ", text)
    text = CODE_RE.sub(" ", text)
    text = PAGE_RE.sub(" ", text)
    text = re.sub(r"(?:\s*[-－]\s*){2,}$", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip(" \n-－、")


def clean_question(question: dict[str, Any]) -> int:
    changes = 0
    for field in ("stem", "passage"):
        if field not in question:
            continue
        before = question.get(field)
        after = clean_text(before)
        if after != before:
            question[field] = after
            changes += 1

    options = question.get("options")
    if isinstance(options, dict):
        for label, before in list(options.items()):
            after = clean_text(before)
            if after != before:
                options[label] = after
                changes += 1
    return changes


def main() -> int:
    files = sorted(DATA_ROOT.glob("*/115年/*/試題.json"))
    changed_files = 0
    changed_fields = 0
    residual: list[dict[str, Any]] = []

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        file_changes = 0
        for question in payload.get("questions", []):
            if not isinstance(question, dict):
                continue
            file_changes += clean_question(question)
            stem = str(question.get("stem") or "")
            if re.search(r"乙\s*、\s*測驗|代號\s*[:：]\s*\d{4}", stem):
                residual.append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "number": question.get("number"),
                        "stem": stem[:240],
                    }
                )

        if file_changes:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed_files += 1
            changed_fields += file_changes

    print(
        json.dumps(
            {
                "files_scanned": len(files),
                "files_changed": changed_files,
                "fields_changed": changed_fields,
                "residual_metadata": len(residual),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    for item in residual:
        print("RESIDUAL " + json.dumps(item, ensure_ascii=False), file=sys.stderr)
    return 1 if residual else 0


if __name__ == "__main__":
    raise SystemExit(main())
