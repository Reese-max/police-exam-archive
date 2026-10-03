#!/usr/bin/env python3
"""Classify verified import changes without editing the worktree or Git index."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

JSON_REPORTS = {"考古題庫/115_import_manifest.json", "考古題庫/dataset_manifest.json"}
MARKDOWN_REPORT = "docs/115-import-report.md"
GENERATED_REPORTS = JSON_REPORTS | {MARKDOWN_REPORT}


class GuardError(Exception):
    """A classification failure must stop the workflow before committing."""


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise GuardError("cannot inspect the Git checkout")
    return result.stdout


def timestamp(value: object) -> None:
    if not isinstance(value, str) or "T" not in value:
        raise GuardError("generated timestamp has an invalid shape")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GuardError("generated timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GuardError("generated timestamp has no timezone")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GuardError("generated JSON contains duplicate keys")
        result[key] = value
    return result


def stable_json(content: bytes) -> str:
    try:
        data = json.loads(content.decode("utf-8"), object_pairs_hook=unique_object)
        if not isinstance(data, dict) or "generated_at" not in data:
            raise GuardError("generated JSON has no top-level timestamp")
        timestamp(data["generated_at"])
        del data["generated_at"]
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise GuardError("cannot read a generated JSON report") from error


def stable_markdown(content: bytes) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeError as error:
        raise GuardError("cannot read the generated Markdown report") from error
    matches = list(re.finditer(r"(?m)^- 執行時間：([^\r\n]+)", text))
    if len(matches) != 1:
        raise GuardError("generated Markdown must have exactly one execution time")
    match = matches[0]
    timestamp(match.group(1))
    return (text[:match.start(1)] + "<generated-time>" + text[match.end(1):]).encode("utf-8")


def has_substantive_changes(root: Path) -> bool:
    # NUL-separated paths preserve Unicode and spaces, including staged changes.
    paths = set(
        part.decode("utf-8")
        for part in (
            git(root, "diff", "--name-only", "-z", "HEAD").split(b"\0")
            + git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        )
        if part
    )
    if not paths:
        return False
    if paths - GENERATED_REPORTS:
        return True
    for path in sorted(paths):
        target = root / path
        if target.is_symlink() or not target.is_file():
            return True
        if not git(root, "ls-tree", "-z", "HEAD", "--", path):
            return True
        # Git summaries include mode/type changes, which content comparison misses.
        if git(root, "diff", "--summary", "HEAD", "--", path):
            return True
        before = git(root, "show", "HEAD:" + path)
        after = target.read_bytes()
        normalize = stable_json if path in JSON_REPORTS else stable_markdown
        if normalize(before) != normalize(after):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        substantive = has_substantive_changes(args.root)
    except (GuardError, OSError, UnicodeError) as error:
        print("Import commit guard failed: " + str(error), file=sys.stderr)
        return 2
    except Exception:
        # Exit 1 is reserved for a verified no-op, including for parser failures.
        print("Import commit guard failed: cannot safely classify import changes.", file=sys.stderr)
        return 2
    if substantive:
        print("Verified import contains substantive changes.")
        return 0
    print("Only generated timestamps changed, or no data changed; preserve the PR head.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
