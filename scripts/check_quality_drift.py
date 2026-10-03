#!/usr/bin/env python3
"""品質摘要漂移檢查腳本。

驗證所有公開表面的語料庫計數與品質分母是否與 quality_summary.json 一致。
用於 CI 中防止手動修改導致數據不一致。

用法:
    python scripts/check_quality_drift.py
    python scripts/check_quality_drift.py --readme path/to/README.md --quiz path/to/quiz.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUALITY_SUMMARY = ROOT / "考古題庫" / "quality_summary.json"
DEFAULT_README = ROOT / "README.md"
DEFAULT_QUIZ = ROOT / "考古題網站" / "quiz.html"
DEFAULT_MANIFEST = ROOT / "考古題庫" / "dataset_manifest.json"


def load_quality_summary() -> dict:
    """載入品質摘要成品。"""
    if not QUALITY_SUMMARY.exists():
        raise SystemExit(f"品質摘要成品不存在：{QUALITY_SUMMARY}")
    return json.loads(QUALITY_SUMMARY.read_text(encoding="utf-8"))


def check_readme(summary: dict, readme_path: Path) -> list[str]:
    """檢查 README.md 品質區段是否與成品一致。"""
    errors = []
    readme_text = readme_path.read_text(encoding="utf-8")

    # 找到品質區段
    quality_section = re.search(r"## 資料品質\n(.*?)(?=\n## |\Z)", readme_text, re.DOTALL)
    if not quality_section:
        errors.append("README: 找不到 '## 資料品質' 區段")
        return errors

    section_text = quality_section.group(1)
    choice_count = summary["counts"]["choice"]

    # 檢查選項完整率
    opt_match = re.search(r"選項完整率.*?(\d[\d,]*)/(\d[\d,]*)", section_text)
    if not opt_match:
        errors.append("README: 找不到 '選項完整率'")
    else:
        opt_num = int(opt_match.group(1).replace(",", ""))
        opt_den = int(opt_match.group(2).replace(",", ""))
        if opt_den != choice_count:
            errors.append(f"README: 選項完整率分母 {opt_den} != 品質摘要 {choice_count}")
        if opt_num != choice_count:
            errors.append(f"README: 選項完整率分子 {opt_num} != 品質摘要 {choice_count}")

    # 檢查答案合法率
    ans_match = re.search(r"答案合法率.*?(\d[\d,]*)/(\d[\d,]*)", section_text)
    if not ans_match:
        errors.append("README: 找不到 '答案合法率'")
    else:
        ans_num = int(ans_match.group(1).replace(",", ""))
        ans_den = int(ans_match.group(2).replace(",", ""))
        if ans_den != choice_count:
            errors.append(f"README: 答案合法率分母 {ans_den} != 品質摘要 {choice_count}")
        if ans_num != choice_count:
            errors.append(f"README: 答案合法率分子 {ans_num} != 品質摘要 {choice_count}")

    return errors


def check_quiz_html(summary: dict, quiz_path: Path) -> list[str]:
    """檢查 quiz.html 註解是否與成品一致。"""
    errors = []
    quiz_text = quiz_path.read_text(encoding="utf-8")
    choice_count = summary["counts"]["choice"]

    # 找到選擇題計數註解
    comment_match = re.search(r"真實題庫.*?(\d[\d,]*)\s*道選擇題", quiz_text)
    if not comment_match:
        errors.append("quiz.html: 找不到選擇題計數註解")
    else:
        count = int(comment_match.group(1).replace(",", ""))
        if count != choice_count:
            errors.append(f"quiz.html: 註解計數 {count} != 品質摘要 {choice_count}")

    return errors


def check_manifest(summary: dict, manifest_path: Path) -> list[str]:
    """檢查 dataset_manifest.json 是否與成品一致。"""
    errors = []
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    expected_counts = summary["counts"]
    actual_counts = manifest_data.get("counts", {})

    for key in ("choice", "essay", "questions", "json_files", "categories", "subjects"):
        expected = expected_counts.get(key)
        actual = actual_counts.get(key)
        if expected != actual:
            errors.append(f"dataset_manifest.json: {key} {actual} != 品質摘要 {expected}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="品質摘要漂移檢查")
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    parser.add_argument("--quiz", type=Path, default=DEFAULT_QUIZ)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    summary = load_quality_summary()

    all_errors = []
    all_errors.extend(check_readme(summary, args.readme))
    all_errors.extend(check_quiz_html(summary, args.quiz))
    all_errors.extend(check_manifest(summary, args.manifest))

    if all_errors:
        print("❌ 品質摘要漂移檢查失敗：", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("✅ 所有公開表面與品質摘要一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())