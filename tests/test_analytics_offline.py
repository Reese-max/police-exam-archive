"""Regression guards for the first-offline Analytics visit (issue #75).

`sw.js` declares Analytics an offline-capable core page: ``analytics.html``,
``analytics-chart.js`` and ``analytics-chart-data.js`` are all precached in
the versioned core cache at service-worker install time.  Every runtime
dependency of that page must therefore also be a controlled same-origin core
asset.  A Chart.js copy that only reaches the runtime CDN cache *after* an
online Analytics visit leaves the precached page without the ``Chart`` global
on the first offline open.
"""

import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "考古題網站"
CHART_VERSION = "4.4.1"
CHART_ASSET = f"vendor/chart.js-{CHART_VERSION}/chart.umd.js"
CACHE_VERSION = "v1.6.1"

CORE_ASSETS_RE = re.compile(r"var CORE_ASSETS\s*=\s*\[(.*?)\];", re.S)
SCRIPT_SRC_RE = re.compile(r'<script[^>]*?\ssrc="([^"]+)"')
REMOTE_SRC_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:)?//")


def _sw() -> str:
    return (SITE / "sw.js").read_text(encoding="utf-8")


def _core_assets() -> list[str]:
    match = CORE_ASSETS_RE.search(_sw())
    assert match, "sw.js must define CORE_ASSETS"
    return re.findall(r"'([^']+)'", match.group(1))


def test_analytics_scripts_are_same_origin() -> None:
    """No remote <script src>: an offline-core page cannot depend on the CDN."""
    html = (SITE / "analytics.html").read_text(encoding="utf-8")
    srcs = SCRIPT_SRC_RE.findall(html)
    assert srcs, "analytics.html loads no external scripts at all"
    remote = [src for src in srcs if REMOTE_SRC_RE.match(src)]
    assert remote == [], f"analytics.html depends on remote scripts: {remote}"
    assert "cdn.jsdelivr.net/npm/chart.js" not in html


def test_analytics_runtime_deps_are_core_precached() -> None:
    """Every JS asset analytics.html needs must land in the install-time core cache."""
    assets = _core_assets()
    for required in (
        "./analytics.html",
        "./analytics-chart.js",
        "./analytics-chart-data.js",
        f"./{CHART_ASSET}",
    ):
        assert required in assets, f"{required} missing from CORE_ASSETS"


def test_vendored_chartjs_is_the_pinned_real_bundle() -> None:
    """The vendored file must be the real pinned Chart.js, referenced by the page."""
    asset = SITE / CHART_ASSET
    assert asset.is_file(), f"{CHART_ASSET} is not vendored"
    blob = asset.read_bytes()
    assert len(blob) > 100_000, "vendored Chart.js looks like a stub"
    assert f"Chart.js v{CHART_VERSION}".encode() in blob
    html = (SITE / "analytics.html").read_text(encoding="utf-8")
    assert f'src="{CHART_ASSET}"' in html


def test_cache_version_bumped_and_core_assets_exist() -> None:
    """A new core asset requires a new CACHE_VERSION so old caches are evicted,
    and every precached entry must resolve to a real file or install fails."""
    assert f"var CACHE_VERSION = '{CACHE_VERSION}';" in _sw()
    for entry in _core_assets():
        rel = entry[2:] if entry.startswith("./") else entry
        if rel == "":
            continue  # './' precaches the site root itself
        assert (SITE / rel).is_file(), f"CORE_ASSETS entry {entry} missing on disk"
