#!/usr/bin/env python3
"""從考古題庫 JSON 生成品質摘要成品。

產出 quality_summary.json，作為所有公開語料庫計數與品質分母的單一真實來源。

用法:
    python scripts/build_quality_summary.py
    python scripts/build_quality_summary.py --output 考古題庫/quality_summary.json
    python scripts/build_quality_summary.py --check
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題庫" / "quality_summary.json"


def get_git_commit_sha() -> str:
    """取得當前 Git commit SHA。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def load_all_questions(data_dir: Path) -> tuple[list[dict], int, int, int]:
    """載入所有非重複題目，回傳 (questions, total_files, duplicate_papers, duplicate_questions)。"""
    files = sorted(glob.glob(str(data_dir / "**" / "試題.json"), recursive=True))
    questions = []
    duplicate_papers = 0
    duplicate_questions = 0

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        is_duplicate = bool(d.get("metadata", {}).get("_is_duplicate"))
        if is_duplicate:
            duplicate_papers += 1
            duplicate_questions += len(d.get("questions", []))
            continue

        category = d.get("category", "")
        year = d.get("year")
        subject = d.get("subject", "")

        if not category or not year or not subject:
            rel = os.path.relpath(fp, str(data_dir))
            parts = rel.replace(os.sep, "/").split("/")
            if not category:
                category = parts[0] if len(parts) > 0 else ""
            if not year:
                year_str = parts[1].replace("年", "") if len(parts) > 1 else ""
                year = int(year_str) if year_str.isdigit() else None
            if not subject:
                subject = parts[2] if len(parts) > 2 else ""

        for q in d.get("questions", []):
            questions.append({
                "cat": category,
                "yr": year,
                "sub": subject,
                "type": q.get("type", ""),
                "stem": q.get("stem", ""),
                "options": q.get("options", {}) if q.get("type") == "choice" else {},
                "answer": q.get("answer", "") if q.get("type") == "choice" else "",
            })

    return questions, len(files), duplicate_papers, duplicate_questions


def compute_quality_metrics(questions: list[dict]) -> dict:
    """計算品質指標：選項完整率、答案合法率。"""
    choice_questions = [q for q in questions if q["type"] == "choice"]
    total_choice = len(choice_questions)

    # 選項完整率：擁有 A/B/C/D 四個非空選項的選擇題比例
    complete_options = 0
    for q in choice_questions:
        opts = q.get("options", {})
        if len(opts) == 4 and all(k in opts and opts[k] for k in "ABCD"):
            complete_options += 1

    # 答案合法率：擁有合法答案 (A-D, 送分, 或 C或D 等多重答案) 的選擇題比例
    import re
    valid_answer = re.compile(r'^[A-D](?:或[A-D])*$')
    valid_answers = 0
    for q in choice_questions:
        ans = q.get("answer", "")
        if ans == "送分" or valid_answer.fullmatch(ans):
            valid_answers += 1

    return {
        "option_completeness": {
            "numerator": complete_options,
            "denominator": total_choice,
            "rate": complete_options / total_choice if total_choice else 0.0,
        },
        "answer_legality": {
            "numerator": valid_answers,
            "denominator": total_choice,
            "rate": valid_answers / total_choice if total_choice else 0.0,
        },
    }


def build_quality_summary(data_dir: Path) -> dict:
    """建立品質摘要成品。"""
    questions, total_files, dup_papers, dup_questions = load_all_questions(data_dir)

    choice_questions = [q for q in questions if q["type"] == "choice"]
    essay_questions = [q for q in questions if q["type"] == "essay"]

    categories = sorted({q["cat"] for q in questions if q["cat"]})
    subjects = sorted({q["sub"] for q in questions if q["sub"]})
    years = sorted({q["yr"] for q in questions if q["yr"]})

    # 計算年份範圍
    if years:
        corpus_version = f"{years[0]}-{years[-1]}"
    else:
        corpus_version = "unknown"

    # 非重複檔案數
    non_duplicate_files = total_files - dup_papers

    quality = compute_quality_metrics(questions)

    return {
        "schema_version": 1,
        "snapshot": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "commit_sha": get_git_commit_sha(),
            "corpus_version": corpus_version,
            "inclusion_rules": [
                "所有非重複 JSON 檔案 (metadata._is_duplicate != true)",
                f"年份範圍: {corpus_version}",
                "跨類科共用考卷僅計入指定正本一次",
                "115 年非重複題目已納入 (550 選擇題、157 申論題)",
            ],
            "exclusion_rules": [
                "標記 metadata._is_duplicate=true 的重複考卷副本",
                "無法解析的損壞 JSON 檔案",
            ],
        },
        "counts": {
            "json_files": non_duplicate_files,
            "questions": len(questions),
            "choice": len(choice_questions),
            "essay": len(essay_questions),
            "categories": len(categories),
            "subjects": len(subjects),
        },
        "duplicate_exclusions": {
            "papers": dup_papers,
            "questions": dup_questions,
        },
        "quality": quality,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成品質摘要成品")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="驗證既有輸出是否與目前題庫一致，不寫檔",
    )
    args = parser.parse_args()

    summary = build_quality_summary(args.data_dir)
    rendered = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not args.output.exists():
            raise SystemExit(f"品質摘要成品不存在：{args.output}")
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            print("--- 應有品質摘要 ---")
            print(rendered)
            raise SystemExit(
                "品質摘要已過期；請執行 python scripts/build_quality_summary.py 後提交變更"
            )
        print("品質摘要與題庫一致")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        f"品質摘要已寫入 {args.output}："
        f"{summary['counts']['choice']:,} 選擇題、"
        f"{summary['counts']['essay']:,} 申論題、"
        f"{summary['counts']['questions']:,} 總題數"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())