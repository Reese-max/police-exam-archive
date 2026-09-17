#!/usr/bin/env python3
"""生成 `考古題庫/quality_summary.json` —— 語料庫統計與品質的單一事實來源。

所有公開表面（README、dataset_manifest.json、quiz/search 文案、首頁
home-stats、analytics）的題數與品質分母都應可追溯到這份 artifact；
漂移檢查由 scripts/check_corpus_claims.py 執行。

用法:
    python scripts/build_quality_summary.py            # 重建 artifact
    python scripts/build_quality_summary.py --check    # 驗證 artifact 未過期
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_home_stats import build_stats  # noqa: E402

DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = DEFAULT_DATA_DIR / "quality_summary.json"

# 生成時才確定的欄位；--check 比對時排除
VOLATILE_KEYS = ("generated_at", "source_commit")

VALID_ANSWER = re.compile(r"^[A-D](?:或[A-D])*$")
IMAGE_OPTION_MARKER = "圖片選項"


def _iter_exam_files(data_dir: Path) -> list[str]:
    return sorted(glob.glob(str(data_dir / "**" / "試題.json"), recursive=True))


def _is_duplicate(payload: dict) -> bool:
    return bool((payload.get("metadata") or {}).get("_is_duplicate"))


def _is_top_level_flagged_only(payload: dict) -> bool:
    """頂層有 _is_duplicate 但 metadata 未標記的檔案。

    正典納入規則為 metadata._is_duplicate（與 test_data_quality /
    dataset_manifest 一致）；此類檔案仍計入唯一題數，但於
    dataset.known_inconsistencies 揭露。
    """
    return bool(payload.get("_is_duplicate")) and not _is_duplicate(payload)


def _meta(fp: str, data_dir: Path, payload: dict):
    """類科/年度/科目；頂層欄位缺漏時以目錄結構推斷（與 build_search_index 一致）。"""
    category = payload.get("category", "")
    year = payload.get("year")
    subject = payload.get("subject", "")
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
    if isinstance(year, str) and year.isdigit():
        year = int(year)
    return category, year, subject


def _fingerprint(files: list[str], data_dir: Path) -> str:
    """對整個語料庫目錄（含重複副本）做內容指紋，作為資料版本識別。"""
    h = hashlib.sha256()
    for fp in files:
        rel = os.path.relpath(fp, str(data_dir)).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(Path(fp).read_bytes()).digest())
    return "sha256:" + h.hexdigest()


def _source_commit(data_dir: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(data_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


def build_summary(data_dir: Path) -> dict:
    """從語料庫重建品質摘要（純計算，不寫檔）。"""
    data_dir = Path(data_dir)
    files = _iter_exam_files(data_dir)

    counts = {
        "total_files": 0,
        "json_files": 0,
        "duplicate_files": 0,
        "questions": 0,
        "choice": 0,
        "essay": 0,
        "duplicate_questions": 0,
        "duplicate_choice": 0,
        "duplicate_essay": 0,
        "categories": set(),
        "subjects": set(),
        "years": set(),
    }
    by_year: dict[str, dict[str, int]] = {}
    option_complete = 0
    answer_valid = 0
    image_placeholder = 0
    free_score = 0
    multi_answer = 0
    top_level_only_flags = 0
    files_without_year = 0

    for fp in files:
        with open(fp, encoding="utf-8") as f:
            payload = json.load(f)
        counts["total_files"] += 1
        questions = payload.get("questions") or []

        if _is_top_level_flagged_only(payload):
            top_level_only_flags += 1

        if _is_duplicate(payload):
            counts["duplicate_files"] += 1
            for q in questions:
                counts["duplicate_questions"] += 1
                if q.get("type") == "choice":
                    counts["duplicate_choice"] += 1
                elif q.get("type") == "essay":
                    counts["duplicate_essay"] += 1
            continue

        counts["json_files"] += 1
        category, year, subject = _meta(fp, data_dir, payload)
        if category:
            counts["categories"].add(str(category))
        if subject:
            counts["subjects"].add(str(subject))
        if isinstance(year, int):
            counts["years"].add(year)
        else:
            files_without_year += 1

        for q in questions:
            counts["questions"] += 1
            qtype = q.get("type")
            if qtype == "choice":
                counts["choice"] += 1
                opts = q.get("options") or {}
                if len(opts) == 4 and all(k in opts for k in "ABCD"):
                    option_complete += 1
                ans = q.get("answer", "")
                if ans == "送分" or VALID_ANSWER.fullmatch(str(ans)):
                    answer_valid += 1
                if ans == "送分":
                    free_score += 1
                elif "或" in str(ans):
                    multi_answer += 1
                if any(
                    IMAGE_OPTION_MARKER in str(v) for v in opts.values()
                ):
                    image_placeholder += 1
            elif qtype == "essay":
                counts["essay"] += 1

            if isinstance(year, int):
                slot = by_year.setdefault(
                    str(year), {"choice": 0, "essay": 0, "total": 0}
                )
                slot["total"] += 1
                if qtype == "choice":
                    slot["choice"] += 1
                elif qtype == "essay":
                    slot["essay"] += 1

    years = sorted(counts["years"])
    choice = counts["choice"]

    known_inconsistencies = []
    if top_level_only_flags:
        known_inconsistencies.append(
            f"{top_level_only_flags} 份檔案僅在頂層標記 _is_duplicate"
            "（metadata 未標記）；依正典規則仍計入唯一題數"
        )
    if files_without_year:
        known_inconsistencies.append(
            f"{files_without_year} 份檔案缺少年度資訊，未列入 by_year 統計"
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(data_dir),
        "dataset_fingerprint": _fingerprint(files, data_dir),
        "dataset": {
            "root": data_dir.name,
            "file_pattern": "**/試題.json",
            "inclusion_rule": (
                "僅計入 metadata._is_duplicate 不為 true 的 試題.json"
            ),
            "exclusion_rule": (
                "metadata._is_duplicate == true 的跨類科共用考卷副本"
                "僅列入 duplicate_* 計數，不混入唯一題數"
            ),
            "known_inconsistencies": known_inconsistencies,
        },
        "counts": {
            "total_files": counts["total_files"],
            "json_files": counts["json_files"],
            "duplicate_files": counts["duplicate_files"],
            "questions": counts["questions"],
            "choice": counts["choice"],
            "essay": counts["essay"],
            "duplicate_questions": counts["duplicate_questions"],
            "duplicate_choice": counts["duplicate_choice"],
            "duplicate_essay": counts["duplicate_essay"],
            "categories": len(counts["categories"]),
            "subjects": len(counts["subjects"]),
            "top_level_only_duplicate_flags": top_level_only_flags,
            "files_without_year": files_without_year,
        },
        "coverage": {
            "first_year": years[0] if years else None,
            "last_year": years[-1] if years else None,
            "years": years,
        },
        "by_year": {y: by_year[y] for y in sorted(by_year)},
        "quality": {
            "option_completeness": {
                "numerator": option_complete,
                "denominator": choice,
                "rate": (option_complete / choice) if choice else None,
                "scope": "counts.choice（所有非重複選擇題）",
                "rule": "options 恰好含 A/B/C/D 四個鍵",
            },
            "answer_validity": {
                "numerator": answer_valid,
                "denominator": choice,
                "rate": (answer_valid / choice) if choice else None,
                "scope": "counts.choice（所有非重複選擇題）",
                "rule": "answer 為 '送分' 或符合 ^[A-D](或[A-D])*$",
            },
        },
        "special_values": {
            "free_score_questions": free_score,
            "multi_answer_questions": multi_answer,
        },
        "image_placeholders": {
            "choice_questions": image_placeholder,
            "marker": f"[{IMAGE_OPTION_MARKER}]",
            "note": (
                "僅驗證選項鍵存在；圖片內容本身的可用性尚未驗證"
                "（追蹤於 issue #58），不對外宣稱可用"
            ),
        },
        "projections": {
            "site": build_stats(data_dir),
        },
    }


def render_summary(summary: dict) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2) + "\n"


def semantic_diff(expected, actual, _path: str = "") -> list[tuple]:
    """遞迴比對兩個 dict/值，回傳 (path, expected, actual) tuple 清單。

    頂層 VOLATILE_KEYS（generated_at、source_commit）不參與比對。
    """
    if isinstance(expected, dict) and isinstance(actual, dict):
        diffs: list[tuple] = []
        for key in sorted(set(expected) | set(actual)):
            if not _path and key in VOLATILE_KEYS:
                continue
            sub = f"{_path}.{key}" if _path else key
            if key not in expected:
                diffs.append((sub, "<absent>", repr(actual[key])))
            elif key not in actual:
                diffs.append((sub, repr(expected[key]), "<absent>"))
            else:
                diffs.extend(semantic_diff(expected[key], actual[key], sub))
        return diffs
    if expected != actual:
        return [(_path, repr(expected), repr(actual))]
    return []


def format_diffs(diffs: list[tuple]) -> list[str]:
    return [f"{p}: expected {e}, found {a}" for p, e, a in diffs]


def write_summary(summary: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_summary(summary), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成語料庫品質摘要")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="驗證已提交的 artifact 與目前題庫一致，不寫檔",
    )
    args = parser.parse_args()

    summary = build_summary(args.data_dir)

    if args.check:
        if not args.output.exists():
            raise SystemExit(f"品質摘要不存在：{args.output}")
        committed = json.loads(args.output.read_text(encoding="utf-8"))
        diffs = semantic_diff(summary, committed)
        if diffs:
            for d in format_diffs(diffs):
                print(f"  {d}")
            raise SystemExit(
                "品質摘要已過期；請執行 "
                "python scripts/check_corpus_claims.py --write 後提交變更"
            )
        print("品質摘要與題庫一致")
        return 0

    write_summary(summary, args.output)
    c = summary["counts"]
    print(
        f"品質摘要已寫入 {args.output}：{c['json_files']:,} 份非重複試題、"
        f"{c['choice']:,} 選擇題 / {c['essay']:,} 申論題 / "
        f"{c['questions']:,} 總題數；重複副本 {c['duplicate_files']:,} 份另計"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
