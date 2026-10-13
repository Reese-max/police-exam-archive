# -*- coding: utf-8 -*-
"""apply_layout_refinements.py 類科頁覆蓋率測試"""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT_PATH = ROOT / "scripts" / "apply_layout_refinements.py"
SITE_ROOT = ROOT / "考古題網站"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "apply_layout_refinements", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _site_category_names() -> set[str]:
    return {
        child.name
        for child in SITE_ROOT.iterdir()
        if child.is_dir()
        and (child / f"{child.name}考古題總覽.html").is_file()
    }


class TestLayoutRefinementsCoverage:
    def test_every_listed_category_page_exists(self):
        module = _load_module()
        missing = [
            category
            for category in module.CATEGORIES
            if not module.category_page(SITE_ROOT, category).is_file()
        ]
        assert not missing, f"CATEGORIES 含不存在的類科頁：{missing}"

    def test_every_site_category_page_is_covered(self):
        module = _load_module()
        uncovered = sorted(_site_category_names() - set(module.CATEGORIES))
        assert not uncovered, f"類科頁未載入版面精修樣式：{uncovered}"

    def test_apply_and_check_cover_every_category(self, tmp_path):
        module = _load_module()
        site = tmp_path / "site"
        css_dir = site / "css"
        css_dir.mkdir(parents=True)
        shutil.copy2(
            SITE_ROOT / "css" / "layout-refinements.css",
            css_dir / "layout-refinements.css",
        )
        page = "<html><head><title>t</title></head><body></body></html>"
        (site / "index.html").write_text(page, encoding="utf-8")
        for name in _site_category_names():
            category_dir = site / name
            category_dir.mkdir()
            (category_dir / f"{name}考古題總覽.html").write_text(
                page, encoding="utf-8"
            )

        module.apply(site)
        module.check(site)

        for name in _site_category_names():
            text = (site / name / f"{name}考古題總覽.html").read_text(
                encoding="utf-8"
            )
            assert "../css/layout-refinements.css" in text
