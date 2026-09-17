#!/usr/bin/env python3
"""圖片選項題的保存與渲染回歸測試（issue #58）

合約：
- 任何 options 含 [圖片選項] 佔位的題目，必須帶 source_locator（原始 PDF
  定位與 sha256）與 option_images（每個佔位選項對應一張可解析的圖片資產，
  含 alt、source_page、sha256）。
- 圖片資產必須存在且內容 sha256 與記錄一致（防止引用失效或圖床漂移）。
- build_search_index 必須把圖片選項與來源放進 optionImages 稀疏表，
  讓 search / quiz / 匯出能在不打開 PDF 的情況下渲染原卷圖片。
- 類科總覽頁與產生器輸出不得把 [圖片選項] 當成可讀文字選項呈現。
"""

import hashlib
import json
import glob
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "考古題庫"
SITE_DIR = PROJECT_ROOT / "考古題網站"

PLACEHOLDER = "[圖片選項]"

import sys
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def iter_questions():
    for fp in sorted(glob.glob(str(DATA_DIR / "**" / "試題.json"), recursive=True)):
        with open(fp, "r", encoding="utf-8") as f:
            d = json.load(f)
        for q in d.get("questions", []):
            yield fp, d, q


def image_option_questions():
    out = []
    for fp, d, q in iter_questions():
        opts = q.get("options") or {}
        if any(PLACEHOLDER in str(v) for v in opts.values()):
            out.append((fp, d, q))
    return out


def _dept_of(fp):
    return Path(fp).relative_to(DATA_DIR).parts[0]


# ── 資料合約 ──

def test_known_affected_question_count():
    """目前確認的圖片選項題為 4 筆資料集記錄（109 水上 Q2、113 消防 Q20，
    各存於學系與非學系兩個類科）。新增圖片題必須連同資產一起進。"""
    affected = image_option_questions()
    assert len(affected) == 4
    keys = {(d.get("year"), q.get("number")) for _, d, q in affected}
    assert keys == {(109, 2), (113, 20)}


def test_placeholder_questions_carry_source_locator():
    """每題圖片選項題都要有穩定來源定位：pdf 路徑、頁碼、pdf sha256。"""
    for fp, d, q in image_option_questions():
        loc = q.get("source_locator")
        assert loc is not None, f"{fp} 題 {q.get('number')} 缺 source_locator"
        assert loc.get("pdf"), f"{fp} source_locator.pdf 為空"
        assert loc.get("page"), f"{fp} source_locator.page 為空"
        sha = loc.get("pdf_sha256", "")
        assert re.fullmatch(r"[0-9a-f]{64}", sha), f"{fp} pdf_sha256 格式異常"
        # 來源定位與檔案級 source_pdf 一致，避免雙重真相
        assert loc["pdf"] == d.get("source_pdf")


def test_every_placeholder_option_has_resolvable_asset():
    """[圖片選項] 佔位不得裸放：每個標籤都要對應存在的圖片且內容雜湊正確。"""
    for fp, d, q in image_option_questions():
        opts = q.get("options") or {}
        images = q.get("option_images") or {}
        placeholder_labels = [L for L, v in opts.items() if PLACEHOLDER in str(v)]
        dept = _dept_of(fp)
        for label in placeholder_labels:
            img = images.get(label)
            assert img is not None, f"{fp} 題 {q.get('number')} 選項 {label} 無 option_images"
            src = img.get("src", "")
            public_src = img.get("public_src", "")
            assert src, f"{fp} 選項 {label} 缺 src"
            assert public_src, f"{fp} 選項 {label} 缺 public_src"
            assert img.get("alt"), f"{fp} 選項 {label} 缺 alt 文字"
            # src 相對於類科頁目錄、public_src 相對於網站根目錄，兩者都要可解析
            dept_asset = SITE_DIR / dept / src
            root_asset = SITE_DIR / public_src
            assert dept_asset.is_file(), f"資產不存在：{dept_asset}"
            assert root_asset.is_file(), f"資產不存在：{root_asset}"
            digest = hashlib.sha256(root_asset.read_bytes()).hexdigest()
            assert digest == img.get("sha256"), (
                f"{root_asset} 內容雜湊與記錄不符"
            )


# ── 搜尋索引合約 ──

def test_search_index_preserves_option_images():
    """build_search_index 需輸出 optionImages 稀疏表：src 可解析、含來源頁。"""
    from build_search_index import build_index

    index = build_index(DATA_DIR)
    option_images = index.get("optionImages")
    assert option_images is not None, "搜尋索引缺 optionImages 表"
    assert len(option_images) >= 4, f"索引只標出 {len(option_images)} 題圖片題"

    for row_key, entry in option_images.items():
        opts = entry.get("options") or {}
        assert set(opts) >= {"A", "B", "C", "D"}, f"列 {row_key} 選項不完整"
        source = entry.get("source") or {}
        assert source.get("page"), f"列 {row_key} 缺來源頁碼"
        assert re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", ""))
        for label, meta in opts.items():
            assert meta.get("src"), f"列 {row_key} 選項 {label} 缺 src"
            assert meta.get("alt"), f"列 {row_key} 選項 {label} 缺 alt"
            assert (SITE_DIR / meta["src"]).is_file(), (
                f"索引中的圖片路徑無法解析：{meta['src']}"
            )


# ── 產生器與已生成頁面合約 ──

def test_generator_renders_image_options_not_placeholder_text():
    """generate_html 不得把 [圖片選項] 當文字選項輸出；須輸出圖片與來源標記。"""
    from build_category_pages import _load_generator

    generator = _load_generator()
    for fp, d, q in image_option_questions():
        html = generator.render_question_html(q)
        assert f'opt-text">{PLACEHOLDER}' not in html, f"{fp} 仍輸出佔位文字"
        assert html.count('class="opt-image"') >= 1
        for label, meta in q["option_images"].items():
            assert meta["src"] in html, f"{fp} 選項 {label} 圖片未渲染"
        assert 'data-source-page=' in html


def test_rendered_category_pages_embed_option_images():
    """四個類科總覽頁必須真的嵌上圖片（src 可解析），而非僅資料層完備。"""
    seen = {}
    for fp, d, q in image_option_questions():
        dept = _dept_of(fp)
        page = SITE_DIR / dept / f"{dept}考古題總覽.html"
        text = page.read_text(encoding="utf-8")
        for label, meta in q["option_images"].items():
            # 頁面內引用可以是 dept 相對（src）或根相對（public_src）
            assert meta["src"] in text or meta["public_src"] in text, (
                f"{page.name} 未引用 {meta['src']}"
            )
        seen[dept] = True
    assert set(seen) == {"水上警察學系", "水上警察", "消防學系", "消防警察"}


# ── 前端管線合約（JS 端以契約字串驗證，實際渲染由上方頁面測試涵蓋）──

def test_frontend_surfaces_wire_option_images():
    """search / quiz / pdf-export 三個介面都要讀取並渲染 option_images。"""
    search_engine = (SITE_DIR / "js" / "search-engine.js").read_text(encoding="utf-8")
    search_html = (SITE_DIR / "search.html").read_text(encoding="utf-8")
    quiz_html = (SITE_DIR / "quiz.html").read_text(encoding="utf-8")
    pdf_js = (SITE_DIR / "js" / "pdf-export.js").read_text(encoding="utf-8")

    assert "optionImages" in search_engine
    assert "optImages" in search_engine
    assert "optImages" in search_html
    assert "optImages" in quiz_html
    assert "opt-image" in pdf_js
    assert "drawOptionImage" in pdf_js
