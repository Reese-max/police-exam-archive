"""Classify staged 115-import output changes before a workflow push."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


VOLATILE_OUTPUTS = {
    "docs/115-import-report.md",
    "考古題庫/115_import_manifest.json",
    "考古題庫/dataset_manifest.json",
}


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True
    ).stdout


def _without_run_timestamp(path: str, content: str) -> object:
    if path.endswith(".json"):
        data = json.loads(content)
        if not isinstance(data, dict):
            return data
        data.pop("generated_at", None)
        return data
    return re.sub(r"(?m)^- 執行時間：.*$", "- 執行時間：<run>", content)


def metadata_only_staged_diff(root: Path) -> bool:
    names = _git(root, "diff", "--cached", "--name-only", "-z").split(b"\0")
    paths = {name.decode("utf-8") for name in names if name}
    if not paths or not paths.issubset(VOLATILE_OUTPUTS):
        return False

    for path in paths:
        current_path = root / path
        if not current_path.is_file():
            return False
        try:
            previous = _git(root, "show", f"HEAD:{path}").decode("utf-8")
        except subprocess.CalledProcessError:
            return False
        current = current_path.read_text(encoding="utf-8")
        if _without_run_timestamp(path, previous) != _without_run_timestamp(path, current):
            return False
    return True


if __name__ == "__main__":
    try:
        metadata_only = metadata_only_staged_diff(Path.cwd())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Cannot classify import delta: {error}", file=sys.stderr)
        sys.exit(2)
    print("metadata-only" if metadata_only else "content-change")
    sys.exit(0 if metadata_only else 1)
