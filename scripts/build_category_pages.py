#!/usr/bin/env python3
"""從題庫 JSON 重建類科總覽頁，不覆蓋首頁與現有共用 CSS/JS。"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "archive" / "misc" / "generate_html.py"
CATEGORIES = [
    "行政警察學系",
    "外事警察學系",
    "刑事警察學系",
    "公共安全學系社安組",
    "犯罪防治學系預防組",
    "消防學系",
    "交通學系交通組",
    "資訊管理學系",
    "鑑識科學學系",
    "國境警察學系境管組",
    "水上警察學系",
    "法律學系",
    "行政管理學系"
]


def load_generator():
    spec = importlib.util.spec_from_file_location("exam_generate_html", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入生成器：{GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "考古題庫")
    parser.add_argument("--output", type=Path, default=ROOT / "考古題網站")
    args = parser.parse_args()
    generator = load_generator()
    all_data = generator.collect_json_data(args.data_dir)
    missing = [category for category in CATEGORIES if category not in all_data]
    if missing:
        raise RuntimeError("缺少類科資料：" + ", ".join(missing))
    for category in CATEGORIES:
        path = generator.generate_category_page(category, all_data[category], args.output)
        if not path:
            raise RuntimeError(f"類科頁生成失敗：{category}")
        content = Path(path).read_text(encoding="utf-8")
        if "115年" not in content:
            raise RuntimeError(f"類科頁未包含 115 年：{path}")
        print(path)


if __name__ == "__main__":
    main()
