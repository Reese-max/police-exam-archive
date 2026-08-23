#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修復 115 年 JSON 的可確定文字瑕疵，並輸出不可安全猜測的語意瑕疵。

可自動修復：
- PDF 抽取造成的英文 camelCase 黏字（例如 policeOfficer → police Officer）
- 題幹殘留的「代號：12345」頁首頁尾 metadata

不可自動猜測：
- 重複選項
- 仍殘留「乙、測驗」等區段標頭
遇到後兩者會列出完整路徑、題號與內容並失敗，供人工對照官方原卷。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_CAMEL_RE = re.compile(r"([a-z]{2,})([A-Z][a-z]{2,})")
_CODE_RE = re.compile(r"\s*代號[:：]\s*\d{4,5}\s*")
_META_RE = re.compile(r"乙、測驗")


def repair_camel(text: str) -> tuple[str, int]:
    count = 0
    while True:
        text2, n = _CAMEL_RE.subn(r"\1 \2", text)
        count += n
        if n == 0 or text2 == text:
            return text2, count
        text = text2


def repair_question(question: dict[str, Any]) -> tuple[int, int]:
    camel = 0
    metadata = 0
    for field in ("stem", "passage"):
        value = question.get(field)
        if not isinstance(value, str):
            continue
        value, n = repair_camel(value)
        camel += n
        if field == "stem":
            value, n_meta = _CODE_RE.subn(" ", value)
            metadata += n_meta
        question[field] = re.sub(r"[ \t]{2,}", " ", value).strip()

    options = question.get("options")
    if isinstance(options, dict):
        for key, value in list(options.items()):
            if not isinstance(value, str):
                continue
            value, n = repair_camel(value)
            camel += n
            options[key] = re.sub(r"[ \t]{2,}", " ", value).strip()
    return camel, metadata


def run(root: Path) -> dict[str, Any]:
    files = sorted(root.glob("*/115年/*/試題.json"))
    if not files:
        raise RuntimeError(f"找不到 115 年試題 JSON：{root}")

    total_camel = 0
    total_metadata = 0
    modified = 0
    duplicate_options: list[dict[str, Any]] = []
    remaining_metadata: list[dict[str, Any]] = []

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for question in payload.get("questions", []):
            if not isinstance(question, dict):
                continue
            camel, metadata = repair_question(question)
            total_camel += camel
            total_metadata += metadata

            stem = str(question.get("stem") or "")
            if _META_RE.search(stem):
                remaining_metadata.append({
                    "file": path.as_posix(),
                    "number": question.get("number"),
                    "stem": stem[:500],
                })

            if question.get("type") == "choice" and not question.get("_note"):
                options = question.get("options") or {}
                if isinstance(options, dict) and options:
                    normalized = [str(v).strip() for v in options.values()]
                    if len(set(normalized)) < len(normalized):
                        duplicate_options.append({
                            "file": path.as_posix(),
                            "number": question.get("number"),
                            "stem": stem[:500],
                            "options": options,
                        })

        after = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if after != before:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            modified += 1

    print(
        f"115 文字修復：掃描 {len(files)} 份，修改 {modified} 份，"
        f"camelCase 修復 {total_camel} 處，代號 metadata 移除 {total_metadata} 處"
    )

    problems = []
    if remaining_metadata:
        problems.append("仍有區段 metadata：\n" + json.dumps(
            remaining_metadata, ensure_ascii=False, indent=2
        ))
    if duplicate_options:
        problems.append("仍有未核對重複選項：\n" + json.dumps(
            duplicate_options, ensure_ascii=False, indent=2
        ))
    if problems:
        raise RuntimeError("\n\n".join(problems))

    return {
        "files_scanned": len(files),
        "modified_files": modified,
        "camelcase_repaired": total_camel,
        "metadata_removed": total_metadata,
        "duplicate_options": 0,
        "remaining_metadata": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="修復並診斷 115 年文字品質")
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
