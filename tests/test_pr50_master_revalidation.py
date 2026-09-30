#!/usr/bin/env python3
"""PR #50 × 目前 master 合併結果的回歸契約測試（issue #70）。

衝突解決必須同時保留兩側仍有效的契約：
- PR #50：115 唯讀稽核工具、115 修補回歸測試、前端 JS 語法檢查、
  已移除的一次性自動合併工作流與隱藏 payload 不得被帶回。
- master：版面精修、完整類科頁建置（17 類科、--check）、app.js 語法檢查。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

REMOVED_WORKFLOWS = (
    "finalize-115-pipeline.yml",
    "ingest-115-police.yml",
    "merge-115-after-ci.yml",
    "merge-verified-115.yml",
    "rescue-115-pipeline.yml",
    "verify-115-and-open-pr.yml",
)

HIDDEN_PAYLOADS = (
    ROOT / "scripts/audit/.finalize_115_import.py.gz.b64",
    ROOT / "scripts/parse/.recover_115_missing_choices.py.gz.b64",
)

FRONTEND_SYNTAX_CHECKS = (
    "js/app.js",
    "js/answer-utils.js",
    "js/search-engine.js",
    "js/quiz-engine.js",
)


def test_one_time_automerge_workflows_and_payloads_stay_removed():
    remaining = [name for name in REMOVED_WORKFLOWS if (WORKFLOWS / name).exists()]
    assert not remaining, f"一次性自動合併工作流被重新帶回：{remaining}"
    for payload in HIDDEN_PAYLOADS:
        assert not payload.exists(), f"隱藏可執行 payload 被重新帶回：{payload.name}"


def test_pr50_integrity_auditor_present_and_passes():
    auditor = ROOT / "scripts" / "audit" / "verify_115_integrity.py"
    assert auditor.is_file(), "PR #50 的 115 唯讀稽核工具在合併後遺失"
    result = subprocess.run(
        [sys.executable, str(auditor)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pr50_regression_suite_and_membership_manifest_present():
    assert (ROOT / "tests" / "test_115_remediation.py").is_file()
    manifest = ROOT / "考古題庫" / "115_membership_manifest.json"
    assert manifest.is_file(), "跨類科 membership manifest 遺失"


def test_master_side_category_and_layout_contracts_survive():
    # master 後來加入的版面精修與完整類科頁建置不得被衝突解決覆蓋。
    assert (ROOT / "scripts" / "apply_layout_refinements.py").is_file()
    assert (ROOT / "考古題網站" / "css" / "layout-refinements.css").is_file()
    builder = (ROOT / "scripts" / "build_category_pages.py").read_text(encoding="utf-8")
    for marker in (
        '"交通學系電訊組"',
        '"公共安全學系情報組"',
        '"犯罪防治學系矯治組"',
        '"國境警察學系移民組"',
        "--check",
        'id="year-115"',
    ):
        assert marker in builder, f"build_category_pages.py 缺少 master 契約：{marker}"


def test_ci_and_pages_syntax_checks_cover_both_sides():
    for name in ("ci.yml", "pages.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        for script in FRONTEND_SYNTAX_CHECKS:
            needle = f"node --check 考古題網站/{script}"
            assert needle in text, f"{name} 缺少語法檢查：{script}"
