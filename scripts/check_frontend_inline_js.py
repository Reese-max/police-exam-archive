#!/usr/bin/env python3
"""使用 Node.js 檢查指定 HTML 內嵌 JavaScript 語法。

會略過具有 ``src`` 的外部 script 與 JSON-LD 等非 JavaScript 資料區塊。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [
    ROOT / "考古題網站" / "practice.html",
    ROOT / "考古題網站" / "search.html",
    ROOT / "考古題網站" / "quiz.html",
]
SCRIPT_RE = re.compile(
    r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
TYPE_RE = re.compile(r"\btype\s*=\s*([\"'])(?P<value>.*?)\1", flags=re.IGNORECASE)
SRC_RE = re.compile(r"\bsrc\s*=", flags=re.IGNORECASE)
JS_TYPES = {
    "",
    "text/javascript",
    "application/javascript",
    "module",
}


def scripts_from_html(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    scripts: list[str] = []
    for match in SCRIPT_RE.finditer(text):
        attrs = match.group("attrs") or ""
        if SRC_RE.search(attrs):
            continue
        type_match = TYPE_RE.search(attrs)
        script_type = type_match.group("value").strip().lower() if type_match else ""
        if script_type not in JS_TYPES:
            continue
        body = match.group("body").strip()
        if body:
            scripts.append(body)
    return scripts


def check_file(path: Path) -> int:
    if not path.is_file():
        print(f"找不到 HTML：{path}", file=sys.stderr)
        return 1

    scripts = scripts_from_html(path)
    errors = 0
    for index, script in enumerate(scripts, start=1):
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".js",
            delete=False,
        ) as handle:
            handle.write(script)
            temp_path = Path(handle.name)
        try:
            completed = subprocess.run(
                ["node", "--check", str(temp_path)],
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            temp_path.unlink(missing_ok=True)

        if completed.returncode:
            errors += 1
            print(
                f"{path.relative_to(ROOT)} 第 {index} 個內嵌 script 語法錯誤：",
                file=sys.stderr,
            )
            print(completed.stderr.strip(), file=sys.stderr)

    print(f"{path.relative_to(ROOT)}：檢查 {len(scripts)} 個內嵌 script")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="要檢查的 HTML")
    args = parser.parse_args()
    files = [path if path.is_absolute() else ROOT / path for path in args.files]
    files = files or DEFAULT_FILES
    return 1 if sum(check_file(path) for path in files) else 0


if __name__ == "__main__":
    raise SystemExit(main())
