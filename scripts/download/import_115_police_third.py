#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下載考選部 115 年警察人員三等考試全部 13 個類別。

本腳本沿用既有 ``download_all_categories.py`` 的下載與目錄格式，僅：

1. 將來源鎖定為考選部考試代碼 ``115060``；
2. 限定警察人員三等考試的 13 個類別；
3. 補上 115 年官方科目名稱與舊版學系資料夾名稱的相容判斷。

下載後仍須執行 ``scripts/parse/pdf_to_questions.py``，將 PDF 轉成既有的
``考古題庫/<類別>/115年/<科目>/試題.json`` 格式。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.download import download_all_categories as downloader  # noqa: E402

YEAR = 115
EXAM_CODE = "115060"
SOURCE_PAGE = (
    "https://wwwq.moex.gov.tw/exam/"
    "wFrmExamQandASearch.aspx?e=115060&y=2026"
)

TARGET_CATEGORIES = (
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
    "行政管理學系",
)

_ORIGINAL_IDENTIFY = downloader.identify_category_from_subjects
_ORIGINAL_GET_EXAM_LIST = downloader.get_exam_list


def identify_category_from_subjects(subjects_text: str) -> str | None:
    """相容 115 年考選部現行科目名稱。

    舊腳本曾以「外事警察學系學」及「水上警察學系學」辨識；115 年官方
    名稱分別是「外事警察學」與「水上警察學」。其他類別沿用既有判斷。
    """
    if (
        "外事警察學" in subjects_text
        and "國際警察合作與跨國(境)犯罪防制" in subjects_text
    ):
        return "外事警察學系"

    if "水上警察學" in subjects_text and "海上犯罪偵查法學" in subjects_text:
        return "水上警察學系"

    return _ORIGINAL_IDENTIFY(subjects_text)


def get_exam_list(session, year: int) -> list[dict]:
    """115 年只讀取指定的官方聯合考試頁，避免混入其他年度或外軌考試。"""
    if year == YEAR:
        return [
            {
                "code": EXAM_CODE,
                "name": "115年公務人員特種考試警察人員考試",
                "year": YEAR,
                "source": SOURCE_PAGE,
            }
        ]
    return _ORIGINAL_GET_EXAM_LIST(session, year)


def main() -> None:
    downloader.identify_category_from_subjects = identify_category_from_subjects
    downloader.get_exam_list = get_exam_list

    output_dir = ROOT / "考古題庫"
    argv = [
        str(Path(__file__)),
        "--categories",
        *TARGET_CATEGORIES,
        "--years",
        str(YEAR),
        "--output",
        str(output_dir),
        "--workers",
        "3",
        "--no-cache",
    ]

    old_argv = sys.argv
    try:
        sys.argv = argv
        downloader.main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
