"""Regression guards for the first-offline Analytics dependency contract."""

from pathlib import Path


SITE = Path(__file__).resolve().parents[1] / "考古題網站"
CHART_ASSET = "vendor/chart.js-4.4.1/chart.umd.js"


def test_chart_dependency_is_local_and_core_precached() -> None:
    analytics_html = (SITE / "analytics.html").read_text(encoding="utf-8")
    service_worker = (SITE / "sw.js").read_text(encoding="utf-8")

    assert f'src="{CHART_ASSET}"' in analytics_html
    assert "https://cdn.jsdelivr.net/npm/chart.js" not in analytics_html
    assert "var CACHE_VERSION = 'v1.6.1';" in service_worker
    assert f"'./{CHART_ASSET}'" in service_worker
    assert (SITE / CHART_ASSET).is_file()
