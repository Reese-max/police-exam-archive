import json
from pathlib import Path
from urllib.error import URLError

import pytest

from scripts.rag.build_source_map import (
    PDF_ENDPOINT,
    build_source_map,
    infer_police_entry,
    normalize_key,
    normalize_category_exam,
    parse_cache_key,
    parse_pdf_url,
    police_context,
    write_json,
)
from scripts.rag import build_source_map as source_module
from scripts.rag import fetch_moex_catalog as fetch_module
from scripts.rag.fetch_moex_catalog import (
    CatalogFetcher,
    NoRedirect,
    PAGE,
    parse_catalog,
    parse_exam_list,
    validate_page_url,
)


MOEX_HTML = (Path(__file__).parent / "fixtures/moex_catalog.html").read_text(encoding="utf-8")


def catalog_rows():
    exam = parse_exam_list(MOEX_HTML, 114)[0]
    return parse_catalog(MOEX_HTML, exam, PAGE + "?e=114060&y=2025")


def url(kind="Q", code="114060", category="508", subject="0102"):
    return f"{PDF_ENDPOINT}?t={kind}&code={code}&c={category}&s={subject}&q=1"


def paper(root, key):
    path = root / "考古題庫" / key / "試題.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # PDF header codes are deliberately present: they must never become URL IDs.
    path.write_text(json.dumps({"metadata": {"code": "50810"}}), encoding="utf-8")


def cache(root, items):
    write_json(root / ".download_cache_all.json", {
        f"{link}:C:\\old\\考古題庫\\{key.replace('/', chr(92))}\\試題.pdf": {}
        for key, link in items
    })


def test_cache_windows_drive_and_q_suffix():
    key, record = parse_cache_key(url() + r":C:\Users\User\Desktop\考古題庫\資訊管理\114年\國文（作文與測驗）\試題.pdf")
    assert key == "資訊管理/114年/國文(作文與測驗)"
    assert record == {
        "exam_code": "114060", "category_code": "508", "subject_code": "0102",
        "file_type": "Q", "url": url(),
    }


@pytest.mark.parametrize("path", [
    "考古題庫/資訊管理/114年/國文（作文與測驗）/試題.json",
    "./資訊管理/114年/國文(作文與測驗)/",
    r"C:\archive\考古題庫\資訊管理\114年\國文(作文與測驗)\答案.pdf",
])
def test_key_normalization(path):
    assert normalize_key(path, {"資訊管理": "資訊管理學系"}) == "資訊管理學系/114年/國文(作文與測驗)"


@pytest.mark.parametrize("path", ["../114年/國文", "類別/114年/../國文", "類別/114/國文"])
def test_invalid_key_rejected(path):
    with pytest.raises(ValueError):
        normalize_key(path)


@pytest.mark.parametrize("value", [
    url().replace("wwwq.moex.gov.tw", "example.com"),
    url() + "&s=9999",
    url().replace("&s=0102", ""),
    url().replace("c=508", "c=505b"),
])
def test_invalid_or_ambiguous_url_rejected(value):
    with pytest.raises(ValueError):
        parse_pdf_url(value)


def test_inferred_same_exam_year_subject_uses_table_category_and_observed_types():
    record = {**parse_pdf_url(url()), "source": ".download_cache_all.json"}
    codes, by_year = police_context({"資訊管理學系/114年/國文": [record]}, {
        "資訊管理學系": {"code": 508}, "行政警察學系": {"code": 501},
        "交通學系電訊組": {"code": "507b"}, "國境警察學系移民組": {"code": 801},
    })
    inferred, partial = infer_police_entry("行政警察學系/114年/國文", codes, by_year)
    assert len(inferred) == 1
    assert inferred[0]["url"] == url(category="501")
    assert inferred[0]["file_type"] == "Q"
    assert inferred[0]["derived"] is True
    assert partial == {"exam_code": "114060", "category_code": "501"}
    assert "交通學系電訊組" not in codes
    assert "國境警察學系移民組" not in codes


@pytest.mark.parametrize("key,partial", [
    ("行政警察學系/113年/國文", {"category_code": "501"}),
    ("行政警察學系/114年/別的科目", {"category_code": "501", "exam_code": "114060"}),
    ("行政警察學系/115年/國文", {}),
    ("未知類科/114年/國文", {}),
])
def test_inference_does_not_guess_missing_year_subject_or_category(key, partial):
    record = {**parse_pdf_url(url()), "source": ".download_cache_all.json"}
    codes, by_year = police_context({"資訊管理學系/114年/國文": [record]}, {
        "資訊管理學系": {"code": 508}, "行政警察學系": {"code": 501},
    })
    assert infer_police_entry(key, codes, by_year) == ([], partial)


def test_inference_rejects_ambiguous_exam_and_unmatched_display_id():
    records = {"資訊管理學系/114年/國文": [
        {**parse_pdf_url(url(code=code)), "source": "cache"}
        for code in ("114060", "114070")
    ]}
    codes, by_year = police_context(records, {"資訊管理學系": {"code": 508}})
    assert infer_police_entry("資訊管理學系/114年/國文", codes, by_year) == ([], {"category_code": "508"})
    _, by_year = police_context(records, {"資訊管理學系": {"code": 509}})
    assert not by_year


def test_unknown_paper_stays_null(tmp_path):
    key = "未知類科/113年/國文"
    paper(tmp_path, key)
    source_map, unresolved = build_source_map(tmp_path)
    assert set(source_map["entries"][key].values()) == {None}
    assert key in unresolved["entries"]
    assert "missing_subject_code" in unresolved["entries"][key]["reasons"]


def test_aliases_retain_original_keys_and_do_not_invent_answers(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "add_pdf_links.py").write_text(
        "MANUAL_OVERRIDES = {'資訊管理學系': '資訊管理'}", encoding="utf-8")
    keys = ["資訊管理/114年/國文(作文與測驗)", "資訊管理學系/114年/國文（作文與測驗）"]
    for key in keys:
        paper(tmp_path, key)
    cache(tmp_path, [(keys[0], url())])
    source_map, unresolved = build_source_map(tmp_path)
    assert set(source_map["entries"]) == set(keys)
    for key in keys:
        entry = source_map["entries"][key]
        assert entry["question_pdf_url"] == url()
        assert entry["answer_pdf_url"] is None
        assert entry["resolved_by"] == "download_cache"
        assert key in unresolved["answer_unresolved"]
    assert not unresolved["entries"]
    assert "scripts/add_pdf_links.py" in source_map["generated_from"]


def test_manifest_pairs_answer_without_reusing_previous_year_codes(tmp_path):
    key = "資訊管理學系/115年/國文(作文與測驗)"
    paper(tmp_path, key)
    old_key = key.replace("115年", "114年")
    paper(tmp_path, old_key)
    write_json(tmp_path / "考古題庫/115_import_manifest.json", {
        "year": 115, "exam_code": "115060", "files": [{
            "category_folder": "資訊管理學系", "category_code": "208",
            "subject": "國文(作文與測驗)", "file_type": kind,
            "relative_path": f"考古題庫/{key}/{'試題' if kind == 'Q' else '答案'}.pdf",
            "url": url(kind, code="115060", category="208"),
        } for kind in ("Q", "S")],
    })
    source_map, unresolved = build_source_map(tmp_path)
    entry = source_map["entries"][key]
    assert entry["question_pdf_url"] == url(code="115060", category="208")
    assert entry["answer_pdf_url"] == url("S", code="115060", category="208")
    assert entry["resolved_by"] == "import_manifest"
    assert source_map["entries"][old_key]["exam_code"] is None
    assert old_key in unresolved["entries"]


def test_conflicts_fail_closed(tmp_path):
    key = "資訊管理/114年/國文"
    paper(tmp_path, key)
    cache(tmp_path, [(key, url()), (key, url(subject="9999"))])
    source_map, unresolved = build_source_map(tmp_path)
    entry = source_map["entries"][key]
    assert entry["exam_code"] == "114060"
    assert entry["subject_code"] is None
    assert entry["question_pdf_url"] is None
    assert "conflicting_subject_code" in unresolved["entries"][key]["reasons"]


def test_repair_report_uses_explicit_year_category_subject_and_url(tmp_path):
    key = "資訊管理/106年/警察情境實務（包括警察法規）"
    paper(tmp_path, key)
    report = tmp_path / "reports/download_fix_report.txt"
    report.parent.mkdir()
    report.write_text(
        "年份: 全部為 106 年\n  1. 資訊管理/警察情境實務（包括警察法規）\n"
        "1. 重新下載 警察情境實務 試題.pdf\n   - 來源 URL: "
        + url(code="106070", subject="1103").split("/exam/", 1)[1], encoding="utf-8")
    source_map, unresolved = build_source_map(tmp_path)
    entry = source_map["entries"][key]
    assert entry["question_pdf_url"] == url(code="106070", subject="1103")
    assert entry["answer_pdf_url"] is None
    assert entry["resolved_by"] == "reports/download_fix_report.txt"
    assert not unresolved["entries"]


def test_output_bytes_stable_across_input_order_and_repeated_runs(tmp_path):
    keys = ["資訊管理/114年/乙科", "資訊管理/114年/甲科"]
    for key in keys:
        paper(tmp_path, key)
    items = [(keys[0], url(subject="0002")), (keys[1], url(subject="0001"))]
    snapshots = []
    for ordered in (items, list(reversed(items)), items):
        cache(tmp_path, ordered)
        outputs = build_source_map(tmp_path)
        for i, output in enumerate(outputs):
            write_json(tmp_path / f"out{i}.json", output)
        snapshots.append(tuple((tmp_path / f"out{i}.json").read_bytes() for i in range(2)))
    assert snapshots[0] == snapshots[1] == snapshots[2]
    assert list(json.loads(snapshots[0][0])["entries"]) == sorted(keys)


def test_moex_html_parser_keeps_grades_deduplicates_and_does_not_invent_answers():
    rows = catalog_rows()
    assert len(rows) == 3
    assert rows[0]["category_name"] == "資訊管理"
    assert rows[0]["subject_name"] == "國文（作文與測驗）"
    assert rows[0]["question_pdf_url"] == url()
    assert rows[0]["answer_pdf_url"] == url("S")
    assert rows[1]["answer_pdf_url"] is None  # R is not S.
    assert rows[2]["category_exam"] == "警察人員考試四等考試"
    assert len(parse_exam_list(MOEX_HTML, 114)) == 1  # No promotion exams.


@pytest.mark.parametrize("text", [
    MOEX_HTML.replace("code=114060", "code=113060"),
    MOEX_HTML.replace('class="level2"', 'class="unknown"'),
    "<html>maintenance</html>",
])
def test_moex_html_parser_rejects_missing_or_inconsistent_context(text):
    with pytest.raises(ValueError):
        parse_catalog(text, {"exam_code": "114060", "year": 114}, PAGE)


@pytest.mark.parametrize("value", [
    "https://example.com/exam/wFrmExamQandASearch.aspx?y=2025",
    url(), PAGE + "?y=2025&y=2024", PAGE + "?y=2025&token=secret",
    PAGE.replace("https:", "http:") + "?y=2025",
])
def test_fetcher_restricts_network_to_official_html(value):
    with pytest.raises(ValueError):
        validate_page_url(value)


def test_fetcher_refuses_redirect_before_following_it():
    with pytest.raises(ValueError, match="redirect refused"):
        NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.com/")


def memory_archive(monkeypatch, rows, old=None):
    """Small in-memory archive: exercises real matching without temp-file privileges."""
    root = Path("fake-repository")
    keys = ["資訊管理/114年/國文(作文與測驗)", "資訊管理/114年/申論科",
            "資訊管理/114年/國文(作文與測驗) extra", "未知/114年/國文"]
    monkeypatch.setattr(source_module, "load_evidence", lambda _: (old or {}, {}, set()))
    monkeypatch.setattr(Path, "exists", lambda p: p == root / "rag/moex_catalog.json")
    monkeypatch.setattr(Path, "glob", lambda p, pattern: [root / "考古題庫" / k / "試題.json" for k in keys])
    monkeypatch.setattr(source_module, "read_json", lambda _: {"schema_version": 1, "entries": rows})
    return root, keys


def test_catalog_exact_normalization_and_unmatched_names_remain_null(monkeypatch):
    root, keys = memory_archive(monkeypatch, catalog_rows())
    result, missing = build_source_map(root)
    assert result["entries"][keys[0]]["resolved_by"] == "moex_catalog"
    assert result["entries"][keys[0]]["question_pdf_url"] == url()
    assert result["entries"][keys[1]]["answer_pdf_url"] is None
    assert keys[1] in missing["answer_unresolved"]
    assert set(result["entries"][keys[2]].values()) == {None}
    assert "catalog_subject_name_not_matched" in missing["entries"][keys[2]]["reasons"]
    assert "catalog_category_year_not_matched" in missing["entries"][keys[3]]["reasons"]
    assert result["generated_from"] == ["rag/moex_catalog.json"]


def test_catalog_wins_conflicts_and_missing_catalog_answer_clears_stale_answer(monkeypatch):
    rows = catalog_rows()
    rows[0]["answer_pdf_url"] = None
    key = "資訊管理/114年/國文(作文與測驗)"
    old = {key: [{**parse_pdf_url(url(kind, subject="9999")), "source": "old_cache"}
                 for kind in ("Q", "S")]}
    root, keys = memory_archive(monkeypatch, rows, old)
    result, missing = build_source_map(root)
    entry = result["entries"][keys[0]]
    assert entry["subject_code"] == "0102"
    assert entry["question_pdf_url"] == url()
    assert entry["answer_pdf_url"] is None
    conflict = missing["conflicts"][key]
    assert conflict["preferred_source"] == "moex_catalog"
    assert conflict["fields"]["subject_code"] == {"previous": ["9999"], "moex_catalog": ["0102"]}
    assert conflict["fields"]["answer_pdf_url"]["moex_catalog"] == []


def test_catalog_internal_ambiguity_fails_closed(monkeypatch):
    rows = catalog_rows()
    rows.append({**rows[0], "subject_code": "9999", "question_pdf_url": url(subject="9999"),
                 "answer_pdf_url": None})
    root, keys = memory_archive(monkeypatch, rows)
    result, missing = build_source_map(root)
    assert result["entries"][keys[0]]["subject_code"] is None
    assert result["entries"][keys[0]]["question_pdf_url"] is None
    assert "conflicting_subject_code" in missing["entries"][keys[0]]["reasons"]


def test_catalog_offline_rebuild_stable_across_order(monkeypatch):
    snapshots = []
    for rows in (catalog_rows(), list(reversed(catalog_rows())), catalog_rows()):
        root, _ = memory_archive(monkeypatch, rows)
        snapshots.append(json.dumps(build_source_map(root), ensure_ascii=False, sort_keys=True).encode())
    assert snapshots[0] == snapshots[1] == snapshots[2]


def test_offline_fetcher_reads_cache_and_never_requests_network(monkeypatch):
    fetcher = CatalogFetcher(Path("unused"), offline=True)
    monkeypatch.setattr(Path, "read_bytes", lambda _: MOEX_HTML.encode())
    monkeypatch.setattr(fetcher.opener, "open", lambda *a, **k: pytest.fail("network used"))
    text, receipt = fetcher.get(PAGE + "?e=114060&y=2025")
    assert text == MOEX_HTML
    assert receipt["cache_file"] == "rag/moex_cache/2025_114060.html"
    assert fetcher.requests == 0


def test_catalog_category_code_conflict_cannot_poison_explicit_name_mapping(monkeypatch):
    rows = catalog_rows()
    rows.append({**rows[0], "category_code": "509", "category_name": "鑑識",
                 "category_label": "警察人員考試三等考試_鑑識",
                 "question_pdf_url": url(category="509"), "answer_pdf_url": None})
    key = "資訊管理/114年/國文(作文與測驗)"
    old = {key: [{**parse_pdf_url(url(category="509")), "source": "old_cache"}]}
    root, _ = memory_archive(monkeypatch, rows, old)
    monkeypatch.setattr(Path, "exists", lambda p: p.name in {"moex_catalog.json", "download_all_categories.py"})
    monkeypatch.setattr(source_module, "literal_mapping", lambda *a: {
        "資訊管理": {"full": "警察人員考試三等考試_資訊管理", "code": 508},
        "鑑識": {"full": "警察人員考試三等考試_鑑識", "code": 509},
    })
    result, missing = build_source_map(root)
    assert result["entries"][key]["category_code"] == "508"
    assert result["entries"][key]["question_pdf_url"] == url()
    assert missing["conflicts"][key]["fields"]["category_code"] == {
        "previous": ["509"], "moex_catalog": ["508"],
    }


def test_historical_exam_headings_use_exact_aliases_and_preserve_grade():
    assert normalize_category_exam("特種警察三等考試") == "警察人員考試三等考試"
    assert normalize_category_exam("警察四等考試") == "警察人員考試四等考試"
    assert normalize_category_exam("一般警察三等考試") == "一般警察人員考試三等考試"
    assert normalize_category_exam("other 三等") == "other 三等"


def test_reexam_published_in_later_year_is_not_assigned_to_later_year(monkeypatch):
    rows = [{**item, "exam_name": "107年消防警察特考重新考試"} for item in catalog_rows()]
    root, keys = memory_archive(monkeypatch, rows)
    result, missing = build_source_map(root)
    assert result["entries"][keys[0]]["question_pdf_url"] is None
    assert keys[0] in missing["entries"]


def test_catalog_rejects_inconsistent_url_codes(monkeypatch):
    rows = catalog_rows()
    rows[0]["subject_code"] = "9999"
    root, _ = memory_archive(monkeypatch, rows)
    with pytest.raises(ValueError, match="Inconsistent MOEX"):
        build_source_map(root)


def test_fetcher_rate_limits_retries_and_stops_after_two_failures(monkeypatch):
    fetcher = CatalogFetcher(Path("unused"))
    clock, starts = [10.0], []
    monkeypatch.setattr(Path, "exists", lambda _: False)
    monkeypatch.setattr(fetch_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fetch_module.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))

    def fail(req, timeout):
        assert req.get_method() == "GET" and timeout == 30
        starts.append(clock[0])
        raise URLError("simulated timeout")

    monkeypatch.setattr(fetcher.opener, "open", fail)
    with pytest.raises(URLError, match="simulated timeout"):
        fetcher.get(PAGE + "?y=2025")
    assert fetcher.requests == 2
    assert starts == [10.0, 11.0]
