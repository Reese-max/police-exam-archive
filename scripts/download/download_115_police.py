#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下載考選部 115 年警察人員三等考試的官方試題與答案。

本腳本刻意使用考選部頁面中的類科代碼（201–213）做精確對應，
避免既有下載器依科目名稱推測類科時，因年度命名變動而漏抓資料。
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


YEAR = 115
GREGORIAN_YEAR = 2026
EXAM_CODE = "115060"
BASE_URL = "https://wwwq.moex.gov.tw/exam/"
PAGE_URL = (
    "https://wwwq.moex.gov.tw/exam/"
    "wFrmExamQandASearch.aspx?e=115060&y=2026"
)

# 官方類科代碼 → 既有資料庫資料夾名稱。
CATEGORY_MAP: "OrderedDict[str, dict[str, str | int]]" = OrderedDict(
    [
        ("201", {"folder": "行政警察學系", "official": "行政警察人員", "subjects": 7}),
        ("202", {"folder": "外事警察學系", "official": "外事警察人員(選試英語)", "subjects": 6}),
        ("203", {"folder": "刑事警察學系", "official": "刑事警察人員", "subjects": 7}),
        ("204", {"folder": "公共安全學系社安組", "official": "公共安全人員", "subjects": 7}),
        ("205", {"folder": "犯罪防治學系預防組", "official": "犯罪防治人員預防組", "subjects": 7}),
        ("206", {"folder": "消防學系", "official": "消防警察人員", "subjects": 7}),
        ("207", {"folder": "交通學系交通組", "official": "交通警察人員交通組", "subjects": 7}),
        ("208", {"folder": "資訊管理學系", "official": "警察資訊管理人員", "subjects": 7}),
        ("209", {"folder": "鑑識科學學系", "official": "刑事鑑識人員", "subjects": 7}),
        ("210", {"folder": "國境警察學系境管組", "official": "國境警察人員", "subjects": 7}),
        ("211", {"folder": "水上警察學系", "official": "水上警察人員", "subjects": 7}),
        ("212", {"folder": "法律學系", "official": "警察法制人員", "subjects": 7}),
        ("213", {"folder": "行政管理學系", "official": "行政管理人員", "subjects": 7}),
    ]
)

FILE_NAMES = {
    "Q": "試題.pdf",
    "S": "答案.pdf",
    "M": "更正答案.pdf",
    "R": "參考答案.pdf",
}
EXPECTED_TOTAL_SUBJECTS = sum(int(v["subjects"]) for v in CATEGORY_MAP.values())
EXPECTED_CORRECTED_ANSWERS = 4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_subject(value: str) -> str:
    value = html.unescape(value).strip()
    value = re.sub(r'[\\/:*?"<>|]', "", value)
    value = re.sub(r"\s+", " ", value).rstrip(" .")
    if not value:
        raise ValueError("空白科目名稱")
    return value


def safe_component(value: str) -> str:
    """建立可追溯且不碰撞的安全路徑；完整名稱另存 official_subject。"""
    value = normalize_subject(value)
    if len(value.encode("utf-8")) <= 240:
        return value
    suffix = "__" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    prefix = value
    while prefix and len((prefix.rstrip(" .") + suffix).encode("utf-8")) > 240:
        prefix = prefix[:-1]
    prefix = prefix.rstrip(" .")
    if not prefix:
        raise ValueError("科目名稱無法建立安全路徑")
    return prefix + suffix


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_pdf_bytes(data: bytes, source: str, content_type: str = "") -> None:
    normalized_type = content_type.lower().split(";", 1)[0].strip()
    if normalized_type and normalized_type not in {
        "application/pdf", "application/octet-stream", "application/x-download"
    }:
        raise RuntimeError(f"下載 Content-Type 非 PDF：{source}：{content_type}")
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"內容缺少 PDF 檔頭：{source}")
    if len(data) <= 1024:
        raise RuntimeError(f"PDF 檔案過小（{len(data)} bytes）：{source}")
    if not data.rstrip().endswith(b"%%EOF"):
        raise RuntimeError(f"PDF 缺少 EOF 標記，可能截斷：{source}")
    try:
        import fitz
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.page_count < 1:
                raise RuntimeError("頁數為 0")
            document.load_page(0)
    except Exception as exc:
        raise RuntimeError(f"PDF 無法解析：{source}：{exc}") from exc


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_html(session: requests.Session) -> str:
    response = session.get(PAGE_URL, timeout=60, verify=True)
    response.raise_for_status()
    if response.apparent_encoding:
        response.encoding = response.apparent_encoding
    text = response.text
    if "115年公務人員特種考試警察人員考試" not in text:
        raise RuntimeError("考選部頁面內容不符預期，未找到 115 年警察人員考試")
    return text


def query_values(href: str) -> dict[str, str]:
    parsed = urlparse(html.unescape(href))
    values = {
        key: vals[-1]
        for key, vals in parse_qs(parsed.query, keep_blank_values=True).items()
        if vals
    }
    # 某些頁面可能把查詢字串再包在 url 參數中。
    nested = values.get("url")
    if nested:
        nested_values = parse_qs(urlparse(html.unescape(nested)).query)
        for key, vals in nested_values.items():
            if vals and key not in values:
                values[key] = vals[-1]
    return values


def subject_from_link(link: Tag) -> str:
    row = link.find_parent("tr")
    if not isinstance(row, Tag):
        raise ValueError("下載連結找不到所屬列")
    label = row.find("label", class_="exam-title") or row.find("label")
    if isinstance(label, Tag):
        subject = label.get_text(" ", strip=True)
    else:
        # 後備：移除連結文字後，以該列第一段純文字為科目。
        clone = BeautifulSoup(str(row), "html.parser")
        for anchor in clone.find_all("a"):
            anchor.decompose()
        subject = clone.get_text(" ", strip=True)
    subject = re.sub(r"^(試題|答案|更正答案|參考答案)\s*", "", subject)
    return normalize_subject(subject)


def scrape_entries(page_html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page_html, "lxml")
    collected: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for link in soup.find_all("a", href=True):
        if not isinstance(link, Tag):
            continue
        href = str(link.get("href", ""))
        if "wHandExamQandA_File.ashx" not in href:
            continue
        params = query_values(href)
        code = params.get("code") or params.get("e")
        category_code = params.get("c")
        file_type = params.get("t")
        if code != EXAM_CODE or category_code not in CATEGORY_MAP:
            continue
        if file_type not in FILE_NAMES:
            continue

        official_subject = subject_from_link(link)
        subject = safe_component(official_subject)
        absolute_url = urljoin(BASE_URL, html.unescape(href))
        key = (category_code, subject, file_type, absolute_url)
        collected[key] = {
            "category_code": category_code,
            "category_folder": CATEGORY_MAP[category_code]["folder"],
            "official_category": CATEGORY_MAP[category_code]["official"],
            "subject": subject,
            "official_subject": official_subject,
            "file_type": file_type,
            "file_name": FILE_NAMES[file_type],
            "url": absolute_url,
        }

    entries = sorted(
        collected.values(),
        key=lambda item: (
            list(CATEGORY_MAP).index(str(item["category_code"])),
            str(item["subject"]),
            str(item["file_type"]),
        ),
    )
    if not entries:
        raise RuntimeError("沒有從官方頁面解析出任何下載連結")
    return entries


def validate_catalog(entries: list[dict[str, Any]]) -> dict[str, Any]:
    subjects_by_category: dict[str, set[str]] = defaultdict(set)
    types_by_subject: dict[tuple[str, str], set[str]] = defaultdict(set)

    for item in entries:
        code = str(item["category_code"])
        subject = str(item["subject"])
        subjects_by_category[code].add(subject)
        types_by_subject[(code, subject)].add(str(item["file_type"]))

    errors: list[str] = []
    for code, info in CATEGORY_MAP.items():
        actual = len(subjects_by_category.get(code, set()))
        expected = int(info["subjects"])
        if actual != expected:
            errors.append(
                f"類科 {code} {info['official']}：預期 {expected} 科，實際 {actual} 科"
            )

    all_subjects = sum(len(value) for value in subjects_by_category.values())
    if all_subjects != EXPECTED_TOTAL_SUBJECTS:
        errors.append(
            f"總科目份數：預期 {EXPECTED_TOTAL_SUBJECTS}，實際 {all_subjects}"
        )

    no_question = [
        f"{code}/{subject}"
        for (code, subject), types in types_by_subject.items()
        if "Q" not in types
    ]
    if no_question:
        errors.append(f"{len(no_question)} 科缺試題連結：{no_question[:5]}")

    corrected = sum(1 for item in entries if item["file_type"] == "M")
    if corrected != EXPECTED_CORRECTED_ANSWERS:
        errors.append(
            f"更正答案份數：預期 {EXPECTED_CORRECTED_ANSWERS}，實際 {corrected}"
        )

    if errors:
        raise RuntimeError("官方目錄驗證失敗：\n- " + "\n- ".join(errors))

    return {
        "category_count": len(CATEGORY_MAP),
        "subject_copies": all_subjects,
        "download_links": len(entries),
        "corrected_answers": corrected,
        "subjects_by_category": {
            code: sorted(subjects_by_category[code]) for code in CATEGORY_MAP
        },
    }


def download_pdf(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    overwrite: bool,
) -> tuple[bytes, bool]:
    if destination.exists() and not overwrite:
        data = destination.read_bytes()
        validate_pdf_bytes(data, str(destination))
        return data, True

    response = session.get(url, timeout=120, verify=True)
    response.raise_for_status()
    data = response.content
    content_type = response.headers.get("Content-Type", "")
    validate_pdf_bytes(data, url, content_type)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    temp.write_bytes(data)
    os.replace(temp, destination)
    return data, False


def run(output: Path, overwrite: bool, pause: float) -> dict[str, Any]:
    session = make_session()
    page_html = fetch_html(session)
    entries = scrape_entries(page_html)
    catalog = validate_catalog(entries)

    files: list[dict[str, Any]] = []
    cached = 0
    downloaded = 0

    for index, item in enumerate(entries, start=1):
        folder = str(item["category_folder"])
        subject = str(item["subject"])
        destination = output / folder / f"{YEAR}年" / subject / str(item["file_name"])
        data, was_cached = download_pdf(
            session,
            str(item["url"]),
            destination,
            overwrite=overwrite,
        )
        cached += int(was_cached)
        downloaded += int(not was_cached)
        files.append(
            {
                **item,
                "relative_path": destination.as_posix(),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "cached": was_cached,
            }
        )
        status = "快取" if was_cached else "下載"
        print(
            f"[{index:03d}/{len(entries):03d}] {status} "
            f"{folder}/{YEAR}年/{subject}/{item['file_name']} "
            f"({len(data) / 1024:.0f} KiB)"
        )
        if pause and not was_cached:
            time.sleep(pause)

    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "year": YEAR,
        "gregorian_year": GREGORIAN_YEAR,
        "exam_code": EXAM_CODE,
        "exam_name": "公務人員特種考試警察人員考試（三等）",
        "official_page": PAGE_URL,
        "catalog": catalog,
        "downloaded": downloaded,
        "cached": cached,
        "files": files,
    }
    manifest_path = output / "115_import_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"\n完成：{catalog['category_count']} 類科、"
        f"{catalog['subject_copies']} 科次、{len(files)} 個官方檔案"
    )
    print(f"清單：{manifest_path}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="下載考選部 115 年警察人員三等考試試題與答案"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("考古題庫"),
        help="資料庫根目錄（預設：考古題庫）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="即使本地已有有效 PDF 仍重新下載",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.15,
        help="每次新下載後暫停秒數（預設 0.15）",
    )
    args = parser.parse_args()

    try:
        run(args.output, args.overwrite, max(0.0, args.pause))
    except Exception as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
