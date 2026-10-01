# -*- coding: utf-8 -*-
"""Analytics 圖表程式／資料同版 pair 的回歸測試（issue #74）。"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SITE = ROOT / "考古題網站"
PAIR_TEST = SITE / "tests" / "analytics-pair.regression.js"
CHART_JS = SITE / "analytics-chart.js"
CHART_DATA = SITE / "analytics-chart-data.js"
CHART_BUNDLE = SITE / "analytics-chart-bundle.js"

node_required = pytest.mark.skipif(
    not shutil.which("node"),
    reason="node not installed",
)


@node_required
def test_service_worker_never_serves_a_mixed_chart_pair() -> None:
    """service worker 只能提供整組同版的圖表程式／資料。"""
    result = subprocess.run(
        ["node", "--test", str(PAIR_TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_chart_bundle_is_identical_for_crlf_and_lf_sources() -> None:
    """Windows 貢獻者的 CRLF 版本必須產生與 LF 相同的 bundle 與 digest。"""
    from scripts.sync_analytics_frontend import chart_bundle

    data = CHART_DATA.read_text(encoding="utf-8")
    chart = CHART_JS.read_text(encoding="utf-8")
    assert chart_bundle(data, chart) == chart_bundle(
        data.replace("\n", "\r\n"), chart.replace("\n", "\r\n")
    )


def test_generated_bundle_matches_its_sources() -> None:
    """產生的 pair bundle 必須等同目前的 chart code + data。"""
    from scripts.sync_analytics_frontend import chart_bundle

    expected = chart_bundle(
        CHART_DATA.read_text(encoding="utf-8"),
        CHART_JS.read_text(encoding="utf-8"),
    )
    actual = CHART_BUNDLE.read_text(encoding="utf-8")
    assert actual == expected, (
        "analytics-chart-bundle.js 與 analytics-chart.js／analytics-chart-data.js 不一致，"
        "請執行 scripts/sync_analytics_frontend.py 重新產生"
    )
