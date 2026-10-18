#!/usr/bin/env python3
"""圖片選項題的誠實降級合約（issue #58）

任何題目若 options 含 [圖片選項] 佔位，必須帶 image_options 來源標註，
且 search-index 產生器要把它標成 img=1 讓前端渲染誠實降級提示，
不得讓佔位文字被當成可讀選項呈現。
"""

import json
import glob
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
DATA_DIR = PROJECT_ROOT / "考古題庫"

PLACEHOLDER = "[圖片選項]"


def iter_questions():
    for fp in glob.glob(str(DATA_DIR / "**" / "試題.json"), recursive=True):
        with open(fp, "r", encoding="utf-8") as f:
            d = json.load(f)
        for q in d.get("questions", []):
            yield fp, q


def image_option_questions():
    out = []
    for fp, q in iter_questions():
        opts = q.get("options") or {}
        if any(PLACEHOLDER in str(v) for v in opts.values()):
            out.append((fp, q))
    return out


def test_placeholder_questions_carry_source_annotation():
    """含 [圖片選項] 的題目必須有 image_options 來源標註（不可無 metadata 裸放）"""
    for fp, q in image_option_questions():
        meta = q.get("image_options")
        assert meta is not None, f"{fp} 題 {q.get('number')} 缺 image_options 標註"
        assert meta.get("note"), f"{fp} 題 {q.get('number')} image_options.note 為空"
        assert meta.get("status"), f"{fp} 題 {q.get('number')} image_options.status 為空"


def test_search_index_flags_image_questions():
    """build_search_index 對圖片選項題必須輸出 img=1 欄位"""
    from build_search_index import load_exam_files, FIELDS

    img_idx = FIELDS.index("img")
    ans_idx = FIELDS.index("ans")
    rows = load_exam_files(DATA_DIR)
    flagged = [r for r in rows if r[img_idx] == 1]
    assert len(flagged) >= 4, f"搜尋索引只標出 {len(flagged)} 題圖片題，預期至少 4 題"
    for r in flagged:
        assert r[ans_idx] in ("A", "B", "C", "D"), "圖片題答案欄位異常"


def test_known_affected_question_count():
    """目前確認的圖片選項題為 4 題（README 記錄）；新增圖片題須連同標註一起進"""
    assert len(image_option_questions()) == 4


def test_search_engine_loads_legacy_and_current_indexes(tmp_path):
    """新版 JS 也必須能載入離線快取的舊索引，並保留新索引的圖片標記。"""
    from build_search_index import build_index

    image_question = image_option_questions()[0][1]
    paper = {
        "category": "水上警察", "year": 109, "subject": "情境實務",
        "questions": [image_question, {
            "number": 3, "type": "choice", "stem": "文字題", "answer": "A",
            "options": {label: label for label in "ABCD"},
        }],
    }
    (tmp_path / "試題.json").write_text(json.dumps(paper), encoding="utf-8")
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const original = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(process.argv[1], 'utf8');
(async () => {
  for (const current of [false, true]) {
    const data = JSON.parse(JSON.stringify(original));
    if (!current) {
      delete data.columns.img;
      data.fields = data.fields.filter(field => field !== 'img');
    }
    let documents;
    const context = vm.createContext({
      window: {},
      fetch: async () => ({ok: true, json: async () => data}),
      MiniSearch: class { addAll(docs) { documents = docs; } },
    });
    vm.runInContext(source, context);
    await context.window.SearchEngine.loadIndex();
    const results = context.window.SearchEngine.search('', {type: 'choice'});
    assert.equal(documents.length, 2);
    assert.equal(results.length, 2);
    assert.equal(results[0].optA, original.columns.optA[0]);
    assert.equal(results[0].ans, original.columns.ans[0]);
    assert.equal(results[0].img, current ? 1 : '');
    assert.equal(results[1].img, '');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script, str(PROJECT_ROOT / "考古題網站/js/search-engine.js")],
        input=json.dumps(build_index(tmp_path)), text=True, encoding="utf-8",
        capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_category_and_print_disclose_image_options():
    """類科頁及其桌面列印 DOM 必須說明圖片缺漏，保留選項與答案。"""
    from build_category_pages import _load_generator

    generator = _load_generator()
    for fp, question in image_option_questions():
        rendered = generator.render_question_html(question)
        assert PLACEHOLDER not in rendered, f"{fp} 仍輸出裸露的圖片佔位"
        assert rendered.count("原卷為圖") == 4
        for label in "ABCD":
            assert f'data-val="{label}"' in rendered
        assert f'data-answer="{question["answer"]}"' in rendered
