"""Regression contract for the browser-local attempt ledger and review queue."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_review_queue_contract():
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "review_queue_contract.cjs")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
