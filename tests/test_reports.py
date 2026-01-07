import json
from pathlib import Path

from auto_generate_form import ImportReport, _derive_report_path, _write_summary_report


def test_derive_report_path_appends_csv_name_when_multi(tmp_path):
    base_file = tmp_path / "form_generation_summary.json"
    csv_path = Path("情境實務.csv")
    derived = _derive_report_path(base_file, csv_path, True)
    assert derived.name == "form_generation_summary_情境實務.json"

    base_dir = tmp_path / "reports"
    derived_dir = _derive_report_path(base_dir, csv_path, True)
    assert derived_dir == base_dir / "情境實務.json"


def test_derive_report_path_respects_base_when_single(tmp_path):
    base_file = tmp_path / "summary.json"
    csv_path = Path("foo.csv")
    derived = _derive_report_path(base_file, csv_path, False)
    assert derived == base_file


def test_write_summary_report_contains_stats(tmp_path):
    output = tmp_path / "summary.json"
    report = ImportReport(total_rows=2, imported=1, skipped=1, warnings=["測試警告"])

    _write_summary_report(output, Path("foo.csv"), Path("src/Code.gs"), 1, report)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["csv_source"].endswith("foo.csv")
    assert payload["stats"]["skipped"] == 1
    assert payload["warnings"] == ["測試警告"]
