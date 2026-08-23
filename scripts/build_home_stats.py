#!/usr/bin/env python3
"""生成首頁使用的精簡統計檔，避免首頁硬編碼題數與試卷數。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站" / "data" / "home-stats.json"

GROUPS = {
    "A": [
        "刑事警察學系",
        "鑑識科學學系",
        "交通學系交通組",
        "交通學系電訊組",
        "消防學系",
        "水上警察學系",
        "資訊管理學系",
    ],
    "B": [
        "行政警察學系",
        "外事警察學系",
        "公共安全學系社安組",
        "公共安全學系情報組",
        "犯罪防治學系預防組",
        "犯罪防治學系矯治組",
        "國境警察學系境管組",
        "國境警察學系移民組",
        "行政管理學系",
        "法律學系",
    ],
}

CATEGORIES = [c for group in GROUPS.values() for c in group]


def build_stats(data_dir: Path) -> dict:
    categories: dict[str, dict[str, int]] = {}
    total_papers = 0
    total_questions = 0
    searchable_questions = 0

    for category in CATEGORIES:
        category_dir = data_dir / category
        papers = 0
        questions = 0
        searchable = 0

        for path in sorted(category_dir.glob("**/試題.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            q_count = len(payload.get("questions", []))
            papers += 1
            questions += q_count

            is_duplicate = bool(
                payload.get("_is_duplicate")
                or payload.get("metadata", {}).get("_is_duplicate")
            )
            if not is_duplicate:
                searchable += q_count

        categories[category] = {
            "papers": papers,
            "questions": questions,
            "searchable_questions": searchable,
        }
        total_papers += papers
        total_questions += questions
        searchable_questions += searchable

    group_stats = {}
    for key, members in GROUPS.items():
        group_stats[key] = {
            "category_count": len(members),
            "papers": sum(categories[c]["papers"] for c in members),
            "questions": sum(categories[c]["questions"] for c in members),
            "searchable_questions": sum(
                categories[c]["searchable_questions"] for c in members
            ),
        }

    return {
        "schema_version": 1,
        "scope": "三等警察特考內軌 17 類科",
        "category_count": len(CATEGORIES),
        "paper_count": total_papers,
        "question_count": total_questions,
        "searchable_question_count": searchable_questions,
        "groups": group_stats,
        "categories": categories,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成首頁統計 JSON")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="驗證既有輸出是否與目前題庫一致，不寫檔",
    )
    args = parser.parse_args()

    stats = build_stats(args.data_dir)
    rendered = json.dumps(stats, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not args.output.exists():
            raise SystemExit(f"首頁統計檔不存在：{args.output}")
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            raise SystemExit(
                "首頁統計已過期；請執行 python scripts/build_home_stats.py 後提交變更"
            )
        print("首頁統計與題庫一致")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        f"首頁統計已寫入 {args.output}："
        f"{stats['category_count']} 類科、{stats['paper_count']} 份試卷、"
        f"{stats['question_count']} 題"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
