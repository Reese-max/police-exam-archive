# -*- coding: utf-8 -*-
"""Analytics 程式/資料同版 pair 的 service worker 回歸測試（issue #74）。"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "考古題網站" / "tests" / "analytics-pair.test.js"


def test_analytics_pair_regression() -> None:
    result = subprocess.run(
        ["node", "--test", str(TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
