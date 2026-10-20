"""Committed category pages and the read-only freshness gate (issue #105)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.apply_layout_refinements import CATEGORY_LINK, inject_link
from scripts.build_category_pages import CATEGORIES, IMAGE_CHOICE_ALIASES, build_pages


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "考古題庫"
SITE_ROOT = ROOT / "考古題網站"
SCRIPT = ROOT / "scripts" / "build_category_pages.py"


def _page(root: Path, category: str) -> Path:
    return root / category / f"{category}考古題總覽.html"


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*.html")
    }


def _check(output: Path, input_root: Path = DATA_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-X", "utf8", str(SCRIPT), "--check",
            "--input", str(input_root), "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


@pytest.fixture(scope="module")
def generated_pages(tmp_path_factory) -> Path:
    output = tmp_path_factory.mktemp("category-pages")
    build_pages(DATA_ROOT, output)
    return output


@pytest.mark.parametrize("category", CATEGORIES)
def test_committed_category_stats_and_years_match_sources(category: str) -> None:
    stats = json.loads((SITE_ROOT / "data" / "home-stats.json").read_text(encoding="utf-8"))
    assert set(stats["categories"]) == set(CATEGORIES)
    category_stats = stats["categories"][category]
    years = {
        path.relative_to(DATA_ROOT / category).parts[0].removesuffix("年")
        for path in (DATA_ROOT / category).rglob("試題.json")
    }
    text = _page(SITE_ROOT, category).read_text(encoding="utf-8")
    values = [int(value) for value in re.findall(r'class="stat-value">(\d+)</div>', text)]
    assert values == [len(years), category_stats["papers"], category_stats["questions"]]
    for year in years:
        assert f'id="year-{year}"' in text
        assert f'data-year="{year}"' in text


@pytest.mark.parametrize(
    ("category", "old", "new"),
    [
        ("行政警察學系", 'class="stat-value">2042<', 'class="stat-value">2041<'),
        ("行政警察學系", 'id="year-115"', 'id="year-999"'),
        ("行政警察學系", 'data-year="115"', 'data-year="999"'),
        ("行政警察學系", 'class="q-block"', 'class="missing-question"'),
        ("水上警察", 'class="opt-image"', 'class="missing-option-image"'),
        ("消防警察", 'class="opt-image"', 'class="missing-option-image"'),
    ],
    ids=["stats", "year-block", "year-filter", "question", "water-alias", "fire-alias"],
)
def test_check_rejects_stale_page_without_writing(
    tmp_path: Path, generated_pages: Path, category: str, old: str, new: str
) -> None:
    output = tmp_path / "site"
    shutil.copytree(generated_pages, output)
    page = _page(output, category)
    text = page.read_text(encoding="utf-8")
    assert old in text
    page.write_text(text.replace(old, new, 1), encoding="utf-8")
    before = _snapshot(output)

    result = _check(output)

    assert result.returncode != 0, "--check accepted a stale category page"
    diagnostic = result.stdout + result.stderr
    assert str(page) in diagnostic
    assert "python scripts/build_category_pages.py" in diagnostic
    assert _snapshot(output) == before


@pytest.mark.parametrize("category", [*CATEGORIES, *IMAGE_CHOICE_ALIASES])
def test_generated_pages_keep_navigation_and_pwa(generated_pages: Path, category: str) -> None:
    page = _page(generated_pages, category)
    text = page.read_text(encoding="utf-8")
    markers = (
        '<link rel="canonical" href="' + page.name + '">',
        '<link rel="manifest" href="../manifest.json">',
        '<a class="sidebar-home" href="../search.html">全文搜尋</a>',
        '<a class="sidebar-home" href="../quiz.html">模擬考試</a>',
        "navigator.serviceWorker.register('../sw.js', {scope: '../'})",
        '<div class="export-actions">',
    )
    assert all(marker in text for marker in markers), [marker for marker in markers if marker not in text]


def test_rebuild_keeps_pdf_links_and_checks_question_content(tmp_path: Path) -> None:
    source = tmp_path / "input"
    output = tmp_path / "site"
    for index, category in enumerate([*CATEGORIES, *IMAGE_CHOICE_ALIASES]):
        year = 115 if index < 13 else 114
        path = source / category / f"{year}年" / "測試科目" / "試題.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "questions": [{
                "number": 1, "type": "choice", "stem": "測試題幹",
                "options": {"A": "甲", "B": "乙"}, "answer": "A",
            }],
        }, ensure_ascii=False), encoding="utf-8")
    build_pages(source, output)
    page = _page(output, "行政警察學系")
    links = '<div class="pdf-links"><a class="pdf-link" href="../pdfs/existing.pdf">試題</a></div>'
    text = page.read_text(encoding="utf-8")
    page.write_text(text.replace('<div class="subject-body">', links + '\n<div class="subject-body">', 1), encoding="utf-8")

    build_pages(source, output)

    text = page.read_text(encoding="utf-8")
    assert links in text, "Rebuilding removed an existing PDF download entry"
    result = _check(output, source)
    assert result.returncode == 0, result.stdout + result.stderr
    page.write_text(text.replace("測試題幹", "遭改寫的題幹", 1), encoding="utf-8")
    before = _snapshot(output)
    result = _check(output, source)
    assert result.returncode != 0, "Preserved PDF links must not mask stale questions"
    assert str(page) in result.stdout + result.stderr
    assert _snapshot(output) == before


def test_check_rejects_missing_legacy_page(tmp_path: Path, generated_pages: Path) -> None:
    output = tmp_path / "site"
    shutil.copytree(generated_pages, output)
    page = _page(output, "水上警察")
    page.unlink()
    before = _snapshot(output)

    result = _check(output)

    assert result.returncode != 0, "--check accepted a missing legacy category page"
    assert str(page) in result.stdout + result.stderr
    assert _snapshot(output) == before


def test_check_accepts_current_pages_with_old_date_and_layout_link(
    tmp_path: Path, generated_pages: Path
) -> None:
    output = tmp_path / "site"
    shutil.copytree(generated_pages, output)
    for page in output.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        text, count = re.subn(r"生成時間：\d{4}-\d{2}-\d{2}", "生成時間：2000-01-01", text)
        assert count == 1
        page.write_text(text, encoding="utf-8")
        inject_link(page, CATEGORY_LINK)
    before = _snapshot(output)

    result = _check(output)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _snapshot(output) == before
