"""Build an offline, evidence-only MOEX PDF source map.

Run: python scripts/rag/build_source_map.py [--root REPOSITORY]
Keys retain the actual archive directory names. Normalization is only used to
join recorded paths; neither metadata.code nor display IDs are URL parameters.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

PDF_ENDPOINT = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx"
CODE_FIELDS = ("exam_code", "category_code", "subject_code")


def normalize_name(value: str) -> str:
    return " ".join(value.replace("（", "(").replace("）", ")").split())


def normalize_category_exam(value: str) -> str:
    # Exact historical headings observed in the official cached catalogs.
    return {
        "特種警察三等考試": "警察人員考試三等考試",
        "警察三等考試": "警察人員考試三等考試",
        "特種警察四等考試": "警察人員考試四等考試",
        "警察四等考試": "警察人員考試四等考試",
        "一般警察三等考試": "一般警察人員考試三等考試",
        "一般警察四等考試": "一般警察人員考試四等考試",
        "國家安全情報人員三等考試": "國家安全情報人員考試三等考試",
    }.get(normalize_name(value), normalize_name(value))


def normalize_key(path: str, aliases: dict[str, str] | None = None) -> str:
    """Accept Windows/Posix archive paths or category/year/subject keys."""
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
    if "考古題庫" in parts:
        parts = parts[parts.index("考古題庫") + 1:]
    if parts and parts[-1] in {"試題.pdf", "答案.pdf", "更正答案.pdf", "參考答案.pdf", "試題.json"}:
        parts.pop()
    if len(parts) != 3 or ".." in parts or not re.fullmatch(r"[0-9]{3}年", parts[1]):
        raise ValueError(f"Not an archive paper key: {path}")
    parts[0] = (aliases or {}).get(parts[0], parts[0])
    return "/".join(normalize_name(p) for p in parts)


def parse_pdf_url(url: str) -> dict[str, str]:
    """Validate observed official URLs and serialize their query deterministically."""
    parsed = urlsplit(html.unescape(url))
    endpoint = urlsplit(PDF_ENDPOINT)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.scheme, parsed.netloc, parsed.path) != (endpoint.scheme, endpoint.netloc, endpoint.path):
        raise ValueError(f"Not an official PDF URL: {url}")
    if parsed.fragment or set(params) != {"t", "code", "c", "s", "q"} or any(len(v) != 1 for v in params.values()):
        raise ValueError(f"Ambiguous PDF query: {url}")
    values = {k: v[0] for k, v in params.items()}
    if values["t"] not in {"Q", "S", "M", "R"} or any(not re.fullmatch(r"[0-9]+", values[k]) for k in ("code", "c", "s", "q")):
        raise ValueError(f"Invalid PDF query: {url}")
    return {
        "exam_code": values["code"], "category_code": values["c"],
        "subject_code": values["s"], "file_type": values["t"],
        "url": PDF_ENDPOINT + "?" + urlencode([(k, values[k]) for k in ("t", "code", "c", "s", "q")]),
    }


def parse_cache_key(value: str, aliases: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    # Split at the URL/path boundary, never at the scheme or Windows drive colon.
    match = re.fullmatch(r"(https://[^\s]+?):((?:[A-Za-z]:[\\/]|/|考古題庫[\\/]).+)", value)
    if not match:
        raise ValueError(f"Invalid download cache key: {value}")
    return normalize_key(match[2], aliases), parse_pdf_url(match[1])


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def literal_mapping(path: Path, name: str) -> dict:
    """Read existing naming evidence without importing executable scripts."""
    for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"Missing {name} in {path}")


def police_context(records: dict, categories: dict) -> tuple[dict, dict]:
    # Only the single-category internal-police block (501..513) is usable.
    # 505b/507b are display IDs; immigration 801 merges language categories.
    codes = {name: str(item["code"]) for name, item in categories.items()
             if isinstance(item.get("code"), int) and 501 <= item["code"] <= 513}
    by_year = defaultdict(list)
    for key, items in records.items():
        category, year, subject = key.split("/")
        for item in items:
            if codes.get(category) == item["category_code"]:
                by_year[year].append((subject, item))
    return codes, by_year


def infer_police_entry(key: str, codes: dict, by_year: dict) -> tuple[list, dict]:
    """Combine only a same-exam/year subject URL with an evidenced category ID."""
    category, year, subject = key.split("/")
    # The downloader's static table explicitly covers 105..114, not 115.
    if category not in codes or not 105 <= int(year[:-1]) <= 114:
        return [], {}
    known = by_year.get(year, [])
    exams = {item["exam_code"] for _, item in known}
    partial = {"category_code": codes[category]}
    if len(exams) != 1:
        return [], partial
    partial["exam_code"] = next(iter(exams))
    evidence = []
    for known_subject, item in known:
        if known_subject == subject:
            # Preserve observed type and q; a Q URL alone never implies S exists.
            params = {k: v[0] for k, v in parse_qs(urlsplit(item["url"]).query).items()}
            params["c"] = codes[category]
            record = parse_pdf_url(PDF_ENDPOINT + "?" + urlencode(params))
            evidence.append({**record, "source": item["source"], "derived": True})
    return evidence, partial


def load_evidence(root: Path) -> tuple[dict, dict, set[str]]:
    records = defaultdict(list)
    aliases = {}
    sources = set()
    for filename, name, reverse in (
        ("scripts/add_pdf_links.py", "MANUAL_OVERRIDES", True),
        ("scripts/build_category_pages.py", "LEGACY_NAME_FIXES", False),
        ("scripts/parse/extract_figures.py", "PDF_CAT_MAP", True),
    ):
        path = root / filename
        if path.exists():
            mapping = literal_mapping(path, name)
            aliases.update({v: k for k, v in mapping.items()} if reverse else mapping)
            sources.add(filename)

    def add(key, record, source):
        if record["file_type"] in {"Q", "S"}:
            records[key].append({**record, "source": source})

    for path in sorted(root.glob("**/.download_cache*.json")):
        source = path.relative_to(root).as_posix()
        cache = read_json(path)
        for raw in sorted(cache):
            key, record = parse_cache_key(raw, aliases)
            add(key, record, source)
        if cache:
            sources.add(source)

    manifest_path = root / "考古題庫/115_import_manifest.json"
    if manifest_path.exists():
        source = manifest_path.relative_to(root).as_posix()
        manifest = read_json(manifest_path)
        for item in manifest["files"]:
            key = normalize_key(item["relative_path"], aliases)
            record = parse_pdf_url(item["url"])
            if (record["exam_code"] != str(manifest["exam_code"])
                    or record["category_code"] != str(item["category_code"])
                    or record["file_type"] != item["file_type"]
                    or key != normalize_key(f"{item['category_folder']}/{manifest['year']}年/{item['subject']}", aliases)):
                raise ValueError(f"Inconsistent import manifest: {item['relative_path']}")
            add(key, record, source)
        sources.add(source)

    report_path = root / "reports/download_fix_report.txt"
    if report_path.exists():
        source = report_path.relative_to(root).as_posix()
        text = report_path.read_text(encoding="utf-8-sig")
        year = re.search(r"年份: 全部為 ([0-9]{3}) 年", text)
        subjects = re.findall(r"^  [0-9]+\. ([^/\r\n]+)/([^\r\n]+)", text, re.MULTILINE)
        for repair in re.finditer(r"重新下載 (.+?) 試題\.pdf\s+- 來源 URL: (\S+)", text):
            matches = [(cat, subject) for cat, subject in subjects
                       if subject == repair[1] or subject.startswith((repair[1] + "（", repair[1] + "("))]
            if not year or len(matches) != 1:
                raise ValueError("Ambiguous repair-report paper")
            category, subject = matches[0]
            url = repair[2]
            if url.startswith("wHandExamQandA_File.ashx?"):
                url = PDF_ENDPOINT + "?" + url.split("?", 1)[1]
            add(normalize_key(f"{category}/{year[1]}年/{subject}", aliases), parse_pdf_url(url), source)
            sources.add(source)
    return records, aliases, sources


def load_catalog(root: Path, records: dict, aliases: dict, sources: set,
                 catalog_path: Path | None = None) -> tuple[dict, dict]:
    """Join exact official labels using repo naming evidence, never fuzzy subjects."""
    source = "rag/moex_catalog.json"
    path = Path(catalog_path) if catalog_path is not None else root / source
    if not path.exists():
        return {}, {}
    catalog = read_json(path)
    if catalog["schema_version"] != 1:
        raise ValueError("Unsupported MOEX catalog schema")
    sources.add(source)
    names, observed = defaultdict(set), defaultdict(set)

    def category_key(category):
        return normalize_key(f"{category}/115年/_", aliases).split("/")[0]

    def add_name(exam, official, folder):
        names[(normalize_category_exam(exam), normalize_name(official))].add(category_key(folder))

    manifest = root / "考古題庫/115_import_manifest.json"
    if manifest.exists():
        for item in read_json(manifest)["files"]:
            if item.get("official_category"):
                add_name("警察人員考試三等考試", item["official_category"], item["category_folder"])
    table_source = "scripts/download/download_all_categories.py"
    table = root / table_source
    if table.exists():
        for folder, item in literal_mapping(table, "CATEGORIES").items():
            if "_" in item.get("full", ""):
                exam, official = item["full"].split("_", 1)
                add_name(exam, official, folder)
        sources.add(table_source)

    # Direct historical URLs can prove an official category/folder correspondence.
    # Derived cross-category links are deliberately excluded from this evidence.
    explicit_names = set(names)
    for key, items in records.items():
        category, year, _ = key.split("/")
        for item in items:
            observed[(int(year[:-1]), item["exam_code"], item["category_code"])].add(category)
    for item in catalog["entries"]:
        identity = (item["year"], item["exam_code"], item["category_code"])
        name = (normalize_category_exam(item["category_exam"]), normalize_name(item["category_name"]))
        if name in explicit_names:
            continue  # Stale URL codes cannot override an explicit naming table.
        for folder in observed.get(identity, []):
            add_name(item["category_exam"], item["category_name"], folder)

    matched, categories = defaultdict(list), defaultdict(set)
    for item in catalog["entries"]:
        year = item["year"]
        if not isinstance(year, int) or not 106 <= year <= 999:
            raise ValueError("Invalid catalog year")
        # A 107-year re-exam listed in the 109 directory is not a 109 paper.
        named_year = re.match(r"([0-9]{3})年", item.get("exam_name", ""))
        if named_year and int(named_year[1]) != year:
            continue
        targets = names.get((normalize_category_exam(item["category_exam"]), normalize_name(item["category_name"])), set())
        # A literal category name is also valid evidence; no suffix stripping.
        targets = targets | {category_key(item["category_name"])}
        for category in sorted(targets):
            categories[(category, year)].add(normalize_name(item["subject_name"]))
            key = normalize_key(f"{category}/{year}年/{item['subject_name']}", aliases)
            for kind, field in (("Q", "question_pdf_url"), ("S", "answer_pdf_url")):
                if item[field] is None:
                    continue
                record = parse_pdf_url(item[field])
                if (any(record[f] != item[f] for f in CODE_FIELDS)
                        or record["file_type"] != kind
                        or not record["exam_code"].startswith(str(year))):
                    raise ValueError("Inconsistent MOEX catalog URL")
                matched[key].append({**record, "source": source})
    return matched, categories


def build_source_map(root: Path, catalog_path: Path | None = None) -> tuple[dict, dict]:
    records, aliases, sources = load_evidence(root)
    catalog, catalog_categories = load_catalog(root, records, aliases, sources, catalog_path)
    table_source = "scripts/download/download_all_categories.py"
    table = root / table_source
    codes, by_year = police_context(records, literal_mapping(table, "CATEGORIES") if table.exists() else {})
    entries, unresolved, answer_unresolved, conflicts = {}, {}, {}, {}
    for paper in sorted((root / "考古題庫").glob("*/*/*/試題.json")):
        key = paper.parent.relative_to(root / "考古題庫").as_posix()
        normalized = normalize_key(key, aliases)
        evidence = records.get(normalized, [])
        entry = {field: None for field in CODE_FIELDS}
        entry.update(question_pdf_url=None, answer_pdf_url=None, resolved_by=None)
        if not evidence:
            evidence, partial = infer_police_entry(normalized, codes, by_year)
            entry.update(partial)
            if partial:
                sources.add(table_source)
        if normalized in catalog:
            preferred = catalog[normalized]
            differences = {}
            for field in (*CODE_FIELDS, "question_pdf_url", "answer_pdf_url"):
                def values(items):
                    if field in CODE_FIELDS:
                        return sorted({r[field] for r in items})
                    kind = "Q" if field == "question_pdf_url" else "S"
                    return sorted({r["url"] for r in items if r["file_type"] == kind})
                old, new = values(evidence), values(preferred)
                if old and old != new:
                    differences[field] = {"previous": old, "moex_catalog": new}
            if differences:
                conflicts[key] = {"preferred_source": "moex_catalog", "fields": differences,
                                  "previous_sources": sorted({r["source"] for r in evidence})}
            # Catalog absence of S must also win over a stale historical answer.
            entry = {field: None for field in CODE_FIELDS}
            entry.update(question_pdf_url=None, answer_pdf_url=None, resolved_by=None)
            evidence = preferred
        reasons = []
        for field in CODE_FIELDS:
            values = {r[field] for r in evidence}
            if len(values) == 1:
                entry[field] = next(iter(values))
            elif len(values) > 1:
                reasons.append(f"conflicting_{field}")
        for kind, field in (("Q", "question_pdf_url"), ("S", "answer_pdf_url")):
            urls = {r["url"] for r in evidence if r["file_type"] == kind}
            if len(urls) == 1 and all(entry[f] is not None for f in CODE_FIELDS):
                entry[field] = next(iter(urls))
            elif len(urls) > 1:
                reasons.append(f"conflicting_{field}")
        if entry["question_pdf_url"]:
            used = {r["source"] for r in evidence}
            if len(used) == 1:
                source = next(iter(used))
                entry["resolved_by"] = ("moex_catalog" if source == "rag/moex_catalog.json"
                                        else "download_cache" if Path(source).name.startswith(".download_cache")
                                        else "import_manifest" if source.endswith("115_import_manifest.json") else source)
            else:
                entry["resolved_by"] = "+".join(sorted(used))
            if any(r.get("derived") for r in evidence):
                entry["resolved_by"] = "derived_same_exam_year_subject:" + "+".join(sorted(used | {table_source}))
            if not entry["answer_pdf_url"]:
                answer_unresolved[key] = {"reasons": sorted(set(reasons + ["no_unambiguous_recorded_answer_pdf_url"]))}
        else:
            if "rag/moex_catalog.json" in sources and normalized not in catalog:
                category, year, _ = normalized.split("/")
                reasons.append("catalog_subject_name_not_matched" if (category, int(year[:-1])) in catalog_categories
                               else "catalog_category_year_not_matched")
            if not evidence:
                reasons.append("no_recorded_pdf_url_for_category_year_subject")
            reasons.extend(f"missing_{f}" for f in CODE_FIELDS if entry[f] is None)
            if not any(r["file_type"] == "Q" for r in evidence):
                reasons.append("no_recorded_question_pdf_url")
            unresolved[key] = {"reasons": sorted(set(reasons))}
        entries[key] = entry
    return (
        {"schema_version": 1, "generated_from": sorted(sources), "entries": entries},
        {"schema_version": 1, "entries": unresolved, "answer_unresolved": answer_unresolved,
         "conflicts": conflicts},
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    source_map, unresolved = build_source_map(args.root)
    write_json(args.root / "rag/source_map.json", source_map)
    write_json(args.root / "rag/source_map_unresolved.json", unresolved)
    total = len(source_map["entries"])
    missing = len(unresolved["entries"])
    print(f"total={total} resolved={total - missing} unresolved={missing} answer_unresolved={len(unresolved['answer_unresolved'])}")
    print(json.dumps(Counter(reason for item in unresolved["entries"].values() for reason in item["reasons"]), sort_keys=True))


if __name__ == "__main__":
    main()
