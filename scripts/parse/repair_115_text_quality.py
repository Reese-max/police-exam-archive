#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修復 115 年 JSON 的可確定文字瑕疵，並阻擋未核對的語意瑕疵。

自動修復只包含可由原卷或固定版面規則確認的內容：
- PDF 抽取造成的英文 camelCase 黏字
- 題幹殘留的「代號：12345」頁首頁尾 metadata
- 國文作文題尾誤吃入下一區「乙、測驗部分」標頭
- 消防警察情境實務第 20 題：依 115 年考選部原卷恢復四個排序選項

任何其他重複選項或區段 metadata 仍會讓流程失敗，禁止猜測。
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
# 115 年國文共同卷作文題後面，PDF 抽取會把分隔線與下一區標頭併入第二題。
_CHINESE_SECTION_TAIL_RE = re.compile(
    r"(?:\n\s*-\s*){1,6}\n?\s*乙、測驗(?:題)?部分[:：]?\s*[（(]?\s*20\s*分\s*[）)]?\s*$"
)

_FIRE_SCENARIO_SUBJECT_PREFIX = "消防警察情境實務("
_FIRE_Q20_OPTIONS = {
    "A": "②④③⑤①",
    "B": "②③④⑤①",
    "C": "③②④⑤①",
    "D": "④③②①⑤",
}
_FIRE_Q20_STEM_MARKER = "木材類之燃燒現象"


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
            value, n_tail = _CHINESE_SECTION_TAIL_RE.subn("", value)
            metadata += n_tail
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


def restore_verified_fire_q20(path: Path, question: dict[str, Any]) -> bool:
    """依考選部 115 年消防警察情境實務原卷恢復第 20 題排序選項。"""
    if not path.parent.name.startswith(_FIRE_SCENARIO_SUBJECT_PREFIX):
        return False
    if question.get("number") != 20 or question.get("type") != "choice":
        return False
    stem = str(question.get("stem") or "")
    if _FIRE_Q20_STEM_MARKER not in stem:
        return False
    options = question.get("options")
    if not isinstance(options, dict):
        return False
    # 只修復「四個選項皆空」這個已確認的 PDF 抽取失敗型態；有任何非空值就不覆蓋。
    if any(str(options.get(key, "")).strip() for key in "ABCD"):
        return False
    question["options"] = dict(_FIRE_Q20_OPTIONS)
    return True


def run(root: Path) -> dict[str, Any]:
    files = sorted(root.glob("*/115年/*/試題.json"))
    if not files:
        raise RuntimeError(f"找不到 115 年試題 JSON：{root}")

    total_camel = 0
    total_metadata = 0
    restored_options = 0
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
            if restore_verified_fire_q20(path, question):
                restored_options += 1

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
        f"camelCase 修復 {total_camel} 處，metadata 移除 {total_metadata} 處，"
        f"官方核對選項恢復 {restored_options} 題"
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
        "verified_options_restored": restored_options,
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
