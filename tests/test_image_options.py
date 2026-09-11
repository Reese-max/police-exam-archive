#!/usr/bin/env python3
"""圖片選項題的誠實降級合約（issue #58）

任何題目若 options 含 [圖片選項] 佔位，必須帶 image_options 來源標註，
且 search-index 產生器要把它標成 img=1 讓前端渲染誠實降級提示，
不得讓佔位文字被當成可讀選項呈現。
"""

import json
import glob
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
