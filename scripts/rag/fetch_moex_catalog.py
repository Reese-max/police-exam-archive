"""Fetch public MOEX HTML catalogs only; never request PDF links.

Run: python scripts/rag/fetch_moex_catalog.py [--offline]
Cached HTML is reused unless --refresh is supplied. No timestamps enter output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup, SoupStrainer

try:
    from .build_source_map import parse_pdf_url, write_json
except ImportError:  # Direct script invocation.
    from build_source_map import parse_pdf_url, write_json

PAGE = "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx"


def validate_page_url(url: str) -> None:
    parsed = urlsplit(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.scheme != "https" or parsed.netloc != "wwwq.moex.gov.tw"
            or parsed.path != "/exam/wFrmExamQandASearch.aspx" or parsed.fragment
            or set(params) not in ({"y"}, {"e", "y"})
            or any(len(v) != 1 or not re.fullmatch(r"[0-9]+", v[0]) for v in params.values())):
        raise ValueError(f"Only official HTML catalog GETs are allowed: {url}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"Catalog redirect refused: {newurl}")


class CatalogFetcher:
    def __init__(self, cache_dir: Path, offline=False, refresh=False):
        self.cache_dir = cache_dir
        self.offline = offline
        self.refresh = refresh
        self.requests = 0
        self.last_request = 0.0
        self.opener = build_opener(NoRedirect())

    def get(self, url: str) -> tuple[str, dict]:
        validate_page_url(url)
        params = parse_qs(urlsplit(url).query)
        name = f"{params['y'][0]}_{params.get('e', ['index'])[0]}.html"
        path = self.cache_dir / name
        if self.offline or (path.exists() and not self.refresh):
            data = path.read_bytes()
        else:
            for attempt in range(2):
                time.sleep(max(0, 1.0 - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                self.requests += 1
                try:
                    req = Request(url, headers={"User-Agent": "CatalogReader/1.0"}, method="GET")
                    with self.opener.open(req, timeout=30) as response:
                        if response.headers.get_content_type() != "text/html":
                            raise ValueError("Catalog response is not HTML")
                        data = response.read()
                    break
                except (URLError, TimeoutError):
                    if attempt == 1:
                        raise
            # Decode before caching so broken responses do not poison reruns.
            data.decode("utf-8-sig")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        return data.decode("utf-8-sig"), {
            "url": url, "cache_file": f"rag/moex_cache/{name}",
            "sha256": hashlib.sha256(data).hexdigest(),
        }


def parse_exam_list(text: str, year: int) -> list[dict]:
    soup = BeautifulSoup(text, "html.parser", parse_only=SoupStrainer("select", id=re.compile(r"ddlExamCode$")))
    select = soup.find("select", id=re.compile(r"ddlExamCode$"))
    if select is None:
        raise ValueError("Missing exam-code selector")
    exams = []
    for option in select.find_all("option", value=True):
        code, name = option["value"], option.get_text(" ", strip=True)
        # Select the combined police exam, including all its companion categories.
        if "警察" in name and ("特種考試" in name or "特考" in name):
            if not re.fullmatch(r"[0-9]{6}", code) or not code.startswith(str(year)):
                raise ValueError(f"Unexpected exam year/code: {year}/{code}")
            exams.append({"exam_code": code, "exam_name": name, "year": year})
    if not exams:
        raise ValueError(f"No police exam listed for {year}")
    return sorted(exams, key=lambda item: item["exam_code"])


def parse_catalog(text: str, exam: dict, page_url: str) -> list[dict]:
    """Read category headers and subject rows in document order, dedup mobile links."""
    soup = BeautifulSoup(text, "html.parser")
    category_label = None
    rows = {}
    for element in soup.select("td.level2, label.exam-title"):
        if element.name == "td":
            category_label = element.get_text(" ", strip=True)
            continue
        row = element.find_parent("tr")
        if row is None:
            raise ValueError("Subject label has no row")
        subject_name = element.get_text(" ", strip=True)
        for link in row.find_all("a", href=True):
            absolute = urljoin(PAGE, link["href"])
            if urlsplit(absolute).path != "/exam/wHandExamQandA_File.ashx":
                continue
            record = parse_pdf_url(absolute)
            if record["file_type"] not in {"Q", "S"}:
                continue
            if (record["exam_code"] != exam["exam_code"] or not category_label
                    or "_" not in category_label or not subject_name):
                raise ValueError("Missing or inconsistent catalog row context")
            category_exam, category_name = category_label.split("_", 1)
            category_name = category_name.replace("類別", "")
            q = parse_qs(urlsplit(record["url"]).query)["q"][0]
            identity = (record["category_code"], record["subject_code"], q)
            item = rows.setdefault(identity, {
                **exam, "category_code": record["category_code"],
                "category_name": category_name, "category_exam": category_exam,
                "category_label": category_label, "subject_code": record["subject_code"],
                "subject_name": subject_name, "question_pdf_url": None,
                "answer_pdf_url": None, "official_page": page_url,
            })
            if (item["category_label"], item["subject_name"]) != (category_label, subject_name):
                raise ValueError(f"Conflicting catalog labels: {identity}")
            field = "question_pdf_url" if record["file_type"] == "Q" else "answer_pdf_url"
            if item[field] not in (None, record["url"]):
                raise ValueError(f"Conflicting catalog URLs: {identity}")
            item[field] = record["url"]
    if not rows:
        raise ValueError(f"No subject rows for {exam['exam_code']}")
    return [rows[key] for key in sorted(rows)]


def fetch_catalog(root: Path, offline=False, refresh=False, years=range(106, 116)) -> tuple[dict, int]:
    fetcher = CatalogFetcher(root / "rag/moex_cache", offline, refresh)
    pages, entries = {}, []
    for year in sorted(set(years)):
        index_url = PAGE + "?" + urlencode({"y": year + 1911})
        text, receipt = fetcher.get(index_url)
        pages[index_url] = receipt
        for exam in parse_exam_list(text, year):
            url = PAGE + "?" + urlencode({"e": exam["exam_code"], "y": year + 1911})
            text, receipt = fetcher.get(url)
            pages[url] = receipt
            entries.extend(parse_catalog(text, exam, url))
        print(f"year={year} pages={len(pages)} entries={len(entries)}", flush=True)
    entries.sort(key=lambda item: (item["exam_code"], item["category_code"],
                                   item["subject_code"], item["question_pdf_url"] or "",
                                   item["answer_pdf_url"] or ""))
    return {"schema_version": 1, "pages": [pages[url] for url in sorted(pages)],
            "entries": entries}, fetcher.requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    start = time.monotonic()
    catalog, requests = fetch_catalog(args.root, args.offline, args.refresh)
    write_json(args.root / "rag/moex_catalog.json", catalog)
    print(json.dumps({"pages": len(catalog["pages"]), "requests": requests,
                      "entries": len(catalog["entries"]),
                      "elapsed_seconds": round(time.monotonic() - start, 2)}, sort_keys=True))


if __name__ == "__main__":
    main()
