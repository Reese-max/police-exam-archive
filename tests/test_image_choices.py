"""圖片選項從題庫到前端輸出的回歸測試。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_category_pages import _load_generator
from scripts.build_search_index import FIELDS, build_index


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "考古題庫"
SITE_ROOT = ROOT / "考古題網站"


def _image_questions() -> list[tuple[Path, dict, dict]]:
    found = []
    for path in sorted(DATA_ROOT.rglob("試題.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for question in data.get("questions", []):
            if question.get("option_images"):
                found.append((path, data, question))
    return found


def test_all_source_image_choices_keep_four_verified_assets() -> None:
    questions = _image_questions()
    assert len(questions) == 4
    assert {(data.get("year"), question.get("number")) for _, data, question in questions} == {
        (109, 2),
        (113, 20),
    }

    for _, data, question in questions:
        locator = question["source_locator"]
        assert locator["pdf"] == data["source_pdf"]
        assert locator["page"] in (2, 4)
        assert len(locator["pdf_sha256"]) == 64
        assert set(question["option_images"]) == set("ABCD")

        for label in "ABCD":
            image = question["option_images"][label]
            assert image["src"].startswith("images/")
            assert image["public_src"].endswith(".png")
            asset = SITE_ROOT / image["public_src"]
            assert asset.is_file(), asset
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            assert digest == image["sha256"]


def test_search_index_and_generator_preserve_image_and_source_fields(tmp_path: Path) -> None:
    index = build_index(DATA_ROOT)
    assert index["v"] == 2
    assert index["fields"] == FIELDS
    columns = index["columns"]

    target_rows = [
        i for i, stem in enumerate(columns["stem"])
        if "進港嘴內航行時誤擊消波塊" in stem or "短路熔痕鑑定" in stem
    ]
    assert len(target_rows) == 4
    for row in target_rows:
        assert all(columns[f][row] for f in ("optImageA", "optImageB", "optImageC", "optImageD"))
        assert all(columns[f][row] for f in ("optAltA", "optAltB", "optAltC", "optAltD"))
        assert columns["sourcePage"][row] in ("2", "4")
        assert len(columns["sourceSha256"][row]) == 64
        assert "pdf_sha256" in columns["sourceLocator"][row]

    generator = _load_generator()
    rendered = []
    for _, _, question in _image_questions():
        html = generator.render_question_html(question)
        rendered.append(html)
        assert html.count('class="opt-image"') == 4
        assert 'class="opt-text">[圖片選項]' not in html
        assert 'data-source-page=' in html
        assert 'data-source-sha256=' in html
        for label in "ABCD":
            assert f"images/q{question['number']}-option-{label}.png" in html

    assert len(rendered) == 4

    # 以實際類科頁生成器寫入隔離目錄，確認 build output 仍攜帶同一契約。
    data = generator.collect_json_data(str(DATA_ROOT))
    water_page = Path(generator.generate_category_page("水上警察學系", data["水上警察學系"], str(tmp_path)))
    fire_page = Path(generator.generate_category_page("消防學系", data["消防學系"], str(tmp_path)))
    assert 'data-source-page="2"' in water_page.read_text(encoding="utf-8")
    assert water_page.read_text(encoding="utf-8").count('class="opt-image"') == 4
    assert 'data-source-page="4"' in fire_page.read_text(encoding="utf-8")
    assert fire_page.read_text(encoding="utf-8").count('class="opt-image"') == 4


def test_frontend_contract_has_image_paths_for_search_quiz_and_pdf() -> None:
    search_html = (SITE_ROOT / "search.html").read_text(encoding="utf-8")
    quiz_html = (SITE_ROOT / "quiz.html").read_text(encoding="utf-8")
    pdf_js = (SITE_ROOT / "js" / "pdf-export.js").read_text(encoding="utf-8")
    search_engine = (SITE_ROOT / "js" / "search-engine.js").read_text(encoding="utf-8")

    assert "optImage' + label" in search_html and "查看" in search_html
    assert "imageOpts" in quiz_html and "查看" in quiz_html
    assert "option.image" in pdf_js and "source" in pdf_js
    assert "sourceLocator" in search_engine
