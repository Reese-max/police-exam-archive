#!/usr/bin/env python3
"""重建完整類科頁面，保留原始 UI／功能並自動納入最新年度資料。

本腳本沿用專案既有的完整 HTML 產生器，但在載入時修復先前批次改名造成的
類科名稱重複。它只重建各類科頁，不覆蓋首頁、搜尋頁、Analytics、共用 CSS
或 JavaScript。
"""

from __future__ import annotations

import argparse
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站"
LEGACY_GENERATOR = ROOT / "archive" / "misc" / "generate_html.py"

CATEGORIES_GROUP_A = [
    "刑事警察學系",
    "鑑識科學學系",
    "交通學系交通組",
    "交通學系電訊組",
    "消防學系",
    "水上警察學系",
    "資訊管理學系",
]

CATEGORIES_GROUP_B = [
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
]

CATEGORIES = CATEGORIES_GROUP_A + CATEGORIES_GROUP_B

CATEGORIES_INFO = {
    "行政警察學系": {"code": 501, "icon": "&#128110;", "color": "#2563eb"},
    "外事警察學系": {"code": 502, "icon": "&#127760;", "color": "#0d9488"},
    "刑事警察學系": {"code": 503, "icon": "&#128269;", "color": "#d97706"},
    "公共安全學系社安組": {"code": 504, "icon": "&#128737;", "color": "#7c3aed"},
    "犯罪防治學系預防組": {"code": 505, "icon": "&#129309;", "color": "#e11d48"},
    "犯罪防治學系矯治組": {"code": "505b", "icon": "&#128274;", "color": "#ea580c"},
    "消防學系": {"code": 506, "icon": "&#128658;", "color": "#dc2626"},
    "交通學系交通組": {"code": 507, "icon": "&#128678;", "color": "#475569"},
    "交通學系電訊組": {"code": "507b", "icon": "&#128225;", "color": "#0284c7"},
    "資訊管理學系": {"code": 508, "icon": "&#128187;", "color": "#2563eb"},
    "鑑識科學學系": {"code": 509, "icon": "&#128300;", "color": "#059669"},
    "國境警察學系境管組": {"code": 510, "icon": "&#128706;", "color": "#7c3aed"},
    "水上警察學系": {"code": 511, "icon": "&#9875;", "color": "#0369a1"},
    "法律學系": {"code": 512, "icon": "&#9878;", "color": "#b45309"},
    "行政管理學系": {"code": 513, "icon": "&#128203;", "color": "#6366f1"},
    "國境警察學系移民組": {"code": 590, "icon": "&#9992;", "color": "#0891b2"},
    "公共安全學系情報組": {"code": "nsi", "icon": "&#128065;", "color": "#4f46e5"},
}

CATEGORIES_EMOJI = {
    "行政警察學系": "👮",
    "外事警察學系": "🌐",
    "刑事警察學系": "🔍",
    "公共安全學系社安組": "🛡",
    "公共安全學系情報組": "👁",
    "犯罪防治學系預防組": "🤝",
    "犯罪防治學系矯治組": "🔒",
    "消防學系": "🚒",
    "交通學系交通組": "🚦",
    "交通學系電訊組": "📡",
    "資訊管理學系": "💻",
    "鑑識科學學系": "🔬",
    "國境警察學系境管組": "🛂",
    "國境警察學系移民組": "✈",
    "水上警察學系": "⚓",
    "法律學系": "⚖",
    "行政管理學系": "📋",
}

# 既有產生器曾遭不完整的批次名稱替換。載入時修正所有殘留字串，避免再輸出
# 「學系學系」或「境管組學系境管組」等錯誤名稱。
LEGACY_NAME_FIXES = {
    "公共安全學系社安組學系情報組": "公共安全學系情報組",
    "公共安全學系社安組學系社安組": "公共安全學系社安組",
    "國境警察學系境管組學系移民組": "國境警察學系移民組",
    "國境警察學系境管組學系境管組": "國境警察學系境管組",
    "行政警察學系學系": "行政警察學系",
    "外事警察學系學系": "外事警察學系",
    "刑事警察學系學系": "刑事警察學系",
    "資訊管理學系學系": "資訊管理學系",
    "鑑識科學學系學系": "鑑識科學學系",
    "水上警察學系學系": "水上警察學系",
    "行政管理學系學系": "行政管理學系",
}

REQUIRED_UI_MARKERS = (
    'id="sidebar"',
    'id="searchInput"',
    'id="viewYear"',
    'id="viewSubject"',
    'id="practiceToggle"',
    'id="answerToggle"',
    'id="bookmarkFilter"',
    'id="exportPanel"',
    'id="darkToggle"',
    '<script src="../js/app.js" defer></script>',
)


def _load_generator() -> types.ModuleType:
    if not LEGACY_GENERATOR.is_file():
        raise FileNotFoundError(f"找不到既有 HTML 產生器：{LEGACY_GENERATOR}")

    source = LEGACY_GENERATOR.read_text(encoding="utf-8")
    for broken, correct in sorted(LEGACY_NAME_FIXES.items(), key=lambda item: -len(item[0])):
        source = source.replace(broken, correct)

    module = types.ModuleType("police_exam_full_page_generator")
    module.__file__ = str(LEGACY_GENERATOR)
    exec(compile(source, str(LEGACY_GENERATOR), "exec"), module.__dict__)

    # 明確覆寫類科設定，避免 archived generator 內的舊常數再影響資料收集。
    module.CATEGORIES_GROUP_A = list(CATEGORIES_GROUP_A)
    module.CATEGORIES_GROUP_B = list(CATEGORIES_GROUP_B)
    module.CATEGORIES_ORDER = list(CATEGORIES)
    module.CATEGORIES_INFO = dict(CATEGORIES_INFO)
    module.CATEGORIES_EMOJI = dict(CATEGORIES_EMOJI)
    return module


def _validate_page(path: Path, category: str, years: list[int]) -> None:
    if not path.is_file():
        raise RuntimeError(f"未產生類科頁：{path}")

    text = path.read_text(encoding="utf-8")
    missing_markers = [marker for marker in REQUIRED_UI_MARKERS if marker not in text]
    if missing_markers:
        raise RuntimeError(f"{category} 缺少原有 UI 功能標記：{missing_markers}")

    latest = max(years)
    if f'id="year-{latest}"' not in text:
        raise RuntimeError(f"{category} 缺少最新年度區塊：{latest}")
    if f'data-year="{latest}"' not in text:
        raise RuntimeError(f"{category} 缺少最新年度篩選：{latest}")

    if 115 in years:
        if 'id="year-115"' not in text or 'data-year="115"' not in text:
            raise RuntimeError(f"{category} 的 115 年資料未寫入完整類科頁")
        if "106年至115年" not in text:
            raise RuntimeError(f"{category} 的頁面年份摘要未更新至 115 年")

    # 防止再次部署成 PR #52 的簡化轉址頁。
    if "location.replace('../category.html?cat='" in text:
        raise RuntimeError(f"{category} 仍是簡化轉址頁，完整 UI 未恢復")


def build_pages(input_root: Path, output_root: Path) -> dict[str, dict[str, int]]:
    generator = _load_generator()
    all_data = generator.collect_json_data(str(input_root))

    missing_categories = [category for category in CATEGORIES if category not in all_data]
    if missing_categories:
        raise RuntimeError(f"題庫缺少類科資料：{missing_categories}")

    summary: dict[str, dict[str, int]] = {}
    for category in CATEGORIES:
        years_data = all_data[category]
        page = generator.generate_category_page(category, years_data, str(output_root))
        if not page:
            raise RuntimeError(f"{category} 類科頁產生失敗")

        years = sorted(int(year) for year in years_data)
        path = Path(page)
        _validate_page(path, category, years)

        paper_count = sum(len(subjects) for subjects in years_data.values())
        question_count = sum(
            len(subject_data.get("questions", []))
            for subjects in years_data.values()
            for subject_data in subjects.values()
        )
        summary[category] = {
            "first_year": min(years),
            "last_year": max(years),
            "papers": paper_count,
            "questions": question_count,
        }
        print(
            f"{category}：{min(years)}–{max(years)} 年，"
            f"{paper_count} 份試卷，{question_count} 題"
        )

    with_115 = [category for category, stats in summary.items() if stats["last_year"] == 115]
    if len(with_115) != 13:
        raise RuntimeError(f"預期 13 個類科含 115 年，實際為 {len(with_115)}：{with_115}")

    print(f"完整類科頁重建完成：17 個類科，其中 13 個已含 115 年")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="在暫存目錄完整產生並驗證，不修改正式網站目錄",
    )
    args = parser.parse_args()

    input_root = args.input.resolve()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="police-exam-category-pages-") as tmp:
            build_pages(input_root, Path(tmp))
        return 0

    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    build_pages(input_root, output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
