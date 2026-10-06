"""Public ledger operations must preserve unreadable source bytes before replacement."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", [
    "quota_record", "quota_direct_save", "quota_import", "quota_export",
    "quarantine_throw", "quarantine_noop", "quarantine_readback", "unreadable_source",
    "blocked_read_is_usable", "quota_recovery_once", "already_quarantined",
    "successful_quarantine_import", "invalid_backup_has_no_side_effects",
])
def test_quarantine_preservation(case):
    result = subprocess.run(
        ["node", str(ROOT / "tests/review_queue_quarantine.cjs"), case],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
