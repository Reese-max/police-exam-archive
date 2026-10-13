#!/usr/bin/env python3
"""將版面精修樣式掛載到首頁與完整類科頁。

Pages 部署時，類科頁會重新由 JSON 產生；因此不能只人工修改既有 HTML。
本腳本以冪等方式注入 stylesheet，並提供 CI 檢查避免之後重建時遺失。
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = ROOT / "考古題網站"
CSS_PATH = SITE_ROOT / "css" / "layout-refinements.css"

CATEGORIES = [
    "刑事警察學系",
    "刑事警察",
    "鑑識科學學系",
    "鑑識科學",
    "交通學系交通組",
    "交通學系電訊組",
    "交通警察交通組",
    "交通警察電訊組",
    "消防學系",
    "消防警察",
    "水上警察學系",
    "水上警察",
    "資訊管理學系",
    "資訊管理",
    "行政警察學系",
    "行政警察",
    "外事警察學系",
    "外事警察",
    "公共安全學系社安組",
    "公共安全學系情報組",
    "公共安全",
    "犯罪防治學系預防組",
    "犯罪防治學系矯治組",
    "犯罪防治預防組",
    "犯罪防治矯治組",
    "國境警察學系境管組",
    "國境警察學系移民組",
    "國境警察",
    "行政管理學系",
    "行政管理",
    "法律學系",
    "警察法制",
]

HOME_LINK = '<link rel="stylesheet" href="css/layout-refinements.css">'
CATEGORY_LINK = '<link rel="stylesheet" href="../css/layout-refinements.css">'
REQUIRED_CSS_MARKERS = (
    "Layout refinements v2",
    "grid-template-columns: repeat(3, minmax(0, 1fr))",
    ".error-report-btn",
    "width: min(100%, 1120px)",
)


def category_page(site_root: Path, category: str) -> Path:
    return site_root / category / f"{category}考古題總覽.html"


def validate_css(css_path: Path) -> None:
    if not css_path.is_file():
        raise RuntimeError(f"找不到版面精修樣式：{css_path}")

    text = css_path.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_CSS_MARKERS if marker not in text]
    if missing:
        raise RuntimeError(f"版面精修 CSS 缺少必要規則：{missing}")
    if text.count("{") != text.count("}"):
        raise RuntimeError("版面精修 CSS 大括號數量不一致")


def inject_link(path: Path, link: str) -> bool:
    if not path.is_file():
        raise RuntimeError(f"找不到 HTML：{path}")

    text = path.read_text(encoding="utf-8")
    if link in text:
        return False
    if "</head>" not in text:
        raise RuntimeError(f"HTML 缺少 </head>：{path}")

    updated = text.replace("</head>", f"{link}\n</head>", 1)
    path.write_text(updated, encoding="utf-8")
    return True


def apply(site_root: Path) -> int:
    validate_css(site_root / "css" / "layout-refinements.css")

    changed = 0
    changed += int(inject_link(site_root / "index.html", HOME_LINK))
    for category in CATEGORIES:
        changed += int(inject_link(category_page(site_root, category), CATEGORY_LINK))

    print(f"版面精修樣式已掛載：{len(CATEGORIES) + 1} 個頁面，實際更新 {changed} 個")
    return changed


def check(site_root: Path) -> None:
    validate_css(site_root / "css" / "layout-refinements.css")

    targets = [(site_root / "index.html", HOME_LINK)]
    targets.extend((category_page(site_root, category), CATEGORY_LINK) for category in CATEGORIES)

    failures: list[str] = []
    for path, link in targets:
        if not path.is_file():
            failures.append(f"缺少檔案：{path}")
            continue
        text = path.read_text(encoding="utf-8")
        if link not in text:
            failures.append(f"未載入版面精修 CSS：{path}")

    if failures:
        raise RuntimeError("\n".join(failures))
    print(f"首頁與 {len(CATEGORIES)} 個類科頁均已載入版面精修樣式")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", type=Path, default=SITE_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    site_root = args.site_root.resolve()
    if args.check:
        check(site_root)
    else:
        apply(site_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
