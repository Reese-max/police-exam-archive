#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正規化 115 年考卷中的考選部自訂字型 PUA 碼位。

考選部部分 PDF 以 Private Use Area 字元表示題內編號、圈號與選項標記。
本工具只處理已由歷年資料與原卷畫面確認的碼位；遇到未知 PUA 時立即失敗，
避免把可能具有語意的符號直接刪除。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PUA_MAP = {
    # 題內阿拉伯編號：原卷顯示 1. 至 10.
    "\ue0c6": "1.",
    "\ue0c7": "2.",
    "\ue0c8": "3.",
    "\ue0c9": "4.",
    "\ue0ca": "5.",
    "\ue0cb": "6.",
    "\ue0cc": "7.",
    "\ue0cd": "8.",
    "\ue0ce": "9.",
    "\ue0cf": "10.",
    # 圈號 ① 至 ⑫。
    "\ue129": "①",
    "\ue12a": "②",
    "\ue12b": "③",
    "\ue12c": "④",
    "\ue12d": "⑤",
    "\ue12e": "⑥",
    "\ue12f": "⑦",
    "\ue130": "⑧",
    "\ue131": "⑨",
    "\ue132": "⑩",
    "\ue133": "⑪",
    "\ue134": "⑫",
    # 中文分項序號。
    "\ue1c0": "㈠",
    "\ue1c1": "㈡",
    "\ue1c2": "㈢",
    "\ue1c3": "㈣",
    # 選項標記。
    "\ue18c": "(A)",
    "\ue18d": "(B)",
    "\ue18e": "(C)",
    "\ue18f": "(D)",
    # 注意事項前的裝飾符號；不屬於題目內容。
    "\ue129": "①",
    "\ue049": "",
    "\ue04a": "",
    "\ue04b": "",
    "\ue04c": "",
}


def is_pua(char: str) -> bool:
    codepoint = ord(char)
    return (
        0xE000 <= codepoint <= 0xF8FF
        or 0xF0000 <= codepoint <= 0xFFFFD
        or 0x100000 <= codepoint <= 0x10FFFD
    )


def sanitize_string(value: str) -> tuple[str, int]:
    replacements = 0
    output: list[str] = []
    for char in value:
        replacement = PUA_MAP.get(char)
        if replacement is not None:
            output.append(replacement)
            replacements += 1
        else:
            output.append(char)
    return "".join(output), replacements


def sanitize_node(node: Any, location: str) -> tuple[Any, int, list[dict[str, str]]]:
    if isinstance(node, str):
        cleaned, count = sanitize_string(node)
        unknown = [
            {
                "location": location,
                "character": char,
                "codepoint": f"U+{ord(char):04X}",
            }
            for char in cleaned
            if is_pua(char)
        ]
        return cleaned, count, unknown

    if isinstance(node, list):
        total = 0
        unknown: list[dict[str, str]] = []
        result = []
        for index, item in enumerate(node):
            cleaned, count, found = sanitize_node(item, f"{location}[{index}]")
            result.append(cleaned)
            total += count
            unknown.extend(found)
        return result, total, unknown

    if isinstance(node, dict):
        total = 0
        unknown: list[dict[str, str]] = []
        result = {}
        for key, value in node.items():
            cleaned, count, found = sanitize_node(value, f"{location}.{key}")
            result[key] = cleaned
            total += count
            unknown.extend(found)
        return result, total, unknown

    return node, 0, []


def run(root: Path) -> dict[str, Any]:
    files = sorted(root.glob("*/115年/*/試題.json"))
    if not files:
        raise RuntimeError(f"找不到 115 年試題 JSON：{root}")

    total_replacements = 0
    modified_files = 0
    all_unknown: list[dict[str, str]] = []

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cleaned, count, unknown = sanitize_node(payload, path.as_posix())
        all_unknown.extend(unknown)
        if count:
            path.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            modified_files += 1
            total_replacements += count
            print(f"正規化 {path}：{count} 個 PUA 碼位")

    if all_unknown:
        unique = []
        seen = set()
        for item in all_unknown:
            key = (item["location"], item["codepoint"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        preview = "\n".join(
            f"- {item['location']}：{item['codepoint']} {item['character']!r}"
            for item in unique[:30]
        )
        raise RuntimeError(
            f"仍有 {len(unique)} 個未知 PUA 位置，禁止靜默移除：\n{preview}"
        )

    summary = {
        "files_scanned": len(files),
        "modified_files": modified_files,
        "replacements": total_replacements,
        "unknown": 0,
    }
    print(
        f"PUA 正規化完成：掃描 {len(files)} 份 JSON，"
        f"修改 {modified_files} 份，共替換 {total_replacements} 個碼位"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="正規化 115 年考選部 PDF 私用字元")
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
