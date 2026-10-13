"""Regression for the 115-import workflow's no-op push guard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.audit.import_delta import metadata_only_staged_diff


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _write_json(root: Path, name: str, generated_at: str, count: int = 1) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"generated_at": generated_at, "count": count}, ensure_ascii=False),
        encoding="utf-8",
    )


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    report = root / "docs/115-import-report.md"
    report.parent.mkdir()
    report.write_text("# Report\n\n- 執行時間：old\n- 試題數：1\n", encoding="utf-8")
    _write_json(root, "考古題庫/115_import_manifest.json", "old")
    _write_json(root, "考古題庫/dataset_manifest.json", "old")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "baseline")
    return root


def test_timestamp_only_outputs_do_not_need_a_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "docs/115-import-report.md").write_text(
        "# Report\n\n- 執行時間：new\n- 試題數：1\n", encoding="utf-8"
    )
    _write_json(root, "考古題庫/115_import_manifest.json", "new")
    _write_json(root, "考古題庫/dataset_manifest.json", "new")
    _git(root, "add", "-A")
    assert metadata_only_staged_diff(root)


def test_changed_import_data_still_needs_a_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write_json(root, "考古題庫/dataset_manifest.json", "new", count=2)
    _git(root, "add", "-A")
    assert not metadata_only_staged_diff(root)


def test_changed_report_content_still_needs_a_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "docs/115-import-report.md").write_text(
        "# Report\n\n- 執行時間：new\n- 試題數：2\n", encoding="utf-8"
    )
    _git(root, "add", "-A")
    assert not metadata_only_staged_diff(root)


def test_unrelated_staged_file_still_needs_a_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "new.txt").write_text("new data", encoding="utf-8")
    _git(root, "add", "-A")
    assert not metadata_only_staged_diff(root)
