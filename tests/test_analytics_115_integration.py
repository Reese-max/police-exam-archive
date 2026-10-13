"""Keep Analytics offline safety and 115 remediation intact together."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_combined_service_worker_preserves_both_asset_contracts():
    worker = (ROOT / "考古題網站/sw.js").read_text(encoding="utf-8")
    core_assets = worker.split("var CORE_ASSETS = [", 1)[1].split("];", 1)[0]
    for asset in (
        "./analytics-chart-bundle.js",
        "./vendor/chart.js-4.4.1/chart.umd.js",
        "./js/answer-utils.js",
    ):
        assert asset in core_assets
    assert "'./analytics-chart.js'" not in core_assets
    assert "'./analytics-chart-data.js'" not in core_assets
    assert "analyticsBundle(event.request)" in worker
    assert "Promise.resolve(Response.error())" in worker
    version = worker.split("var CACHE_VERSION = 'v", 1)[1].split("'", 1)[0]
    assert tuple(map(int, version.split("."))) > (1, 6, 2)


def test_combined_ci_keeps_required_names_and_independent_regressions():
    workflows = ROOT / ".github/workflows"
    ci = (workflows / "ci.yml").read_text(encoding="utf-8")
    quality = (workflows / "data-quality.yml").read_text(encoding="utf-8")
    pages = (workflows / "pages.yml").read_text(encoding="utf-8")
    assert "name: CI / test (${{ matrix.python-version }})" in ci
    assert "name: Data Quality Check / quality-check" in quality
    for check in (
        "verify_115_integrity.py",
        "quiz-answer-contract.js",
        "analytics-pair.test.js",
        "analytics-offline.spec.js",
    ):
        assert check in ci
    assert "test_115_remediation.py" in quality
    assert "analytics-chart-bundle.js" in pages
    assert "build_category_pages.py" in pages
    assert not (workflows / "ingest-115-police.yml").exists()
