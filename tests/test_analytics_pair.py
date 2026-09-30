from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "考古題網站" / "tests" / "analytics-pair.test.js"


def test_analytics_pair_regression() -> None:
    result = subprocess.run(
        ["node", "--test", str(TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_node_failure_keeps_utf8_diagnostics(monkeypatch, tmp_path) -> None:
    failing_test = tmp_path / "failing-pair.test.js"
    failing_test.write_text(
        "require('node:test')('pair', () => { throw new Error('配對檢查失敗'); });",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "TEST", failing_test)
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp950")

    with pytest.raises(AssertionError, match="配對檢查失敗"):
        test_analytics_pair_regression()
