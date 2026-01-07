import json
from pathlib import Path
from types import SimpleNamespace

import auto_generate_form as agf


def test_parse_args_supports_multiple_csvs(monkeypatch):
    monkeypatch.setattr(
        agf.sys,
        "argv",
        [
            "auto_generate_form.py",
            "--csv",
            "a.csv",
            "b.csv",
            "--questions-per-page",
            "3",
            "--continue-on-error",
        ],
    )
    args = agf.parse_args()
    assert args.csv == [Path("a.csv"), Path("b.csv")]
    assert args.questions_per_page == 3
    assert args.continue_on_error is True


def test_run_command_handles_missing_binary():
    assert agf.run_command(["tool_that_does_not_exist_xyz"], "missing") is False


def test_process_single_csv_generates_summary(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "題目,選項A,選項B,選項C,選項D,標準答案\n第一題,甲,乙,丙,丁,A\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        form_title="Demo",
        form_description="Desc",
        questions_per_page=5,
        output=tmp_path / "Code.gs",
        report=tmp_path / "summary.json",
        skip_push=True,
        run=False,
    )

    ok = agf._process_single_csv(csv_path, args, multi_csv=True, clasp_available=False)

    assert ok is True
    derived_report = tmp_path / "summary_sample.json"
    payload = json.loads(derived_report.read_text(encoding="utf-8"))
    assert payload["total_questions"] == 1
    assert Path(payload["csv_source"]).name == "sample.csv"


def test_process_single_csv_fails_when_push_fails(tmp_path, monkeypatch):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "題目,選項A,選項B,選項C,選項D,標準答案\n第一題,甲,乙,丙,丁,A\n",
        encoding="utf-8",
    )

    args = SimpleNamespace(
        form_title="Demo",
        form_description="Desc",
        questions_per_page=5,
        output=tmp_path / "Code.gs",
        report=tmp_path / "summary.json",
        skip_push=False,
        run=True,
    )

    calls = []

    def fake_run_command(command, description, timeout=60):
        calls.append(description)
        return False

    monkeypatch.setattr(agf, "run_command", fake_run_command)

    ok = agf._process_single_csv(csv_path, args, multi_csv=False, clasp_available=True)

    assert ok is False
    assert any("CLASP Push" in desc for desc in calls)
