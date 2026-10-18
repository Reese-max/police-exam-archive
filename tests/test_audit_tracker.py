"""Keep the audit tracker's evidence navigable and its status scoped."""

import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "docs/audits/50-persona-tracker.md"
REPO = "https://github.com/Reese-max/police-exam-archive"


def test_tracker_links_findings_and_evidence():
    text = TRACKER.read_text(encoding="utf-8")
    links = dict(re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text))
    for number in sorted(set(re.findall(r"#(\d+)\b", text)), key=int):
        assert links.get(f"#{number}") in {
            f"{REPO}/issues/{number}", f"{REPO}/pull/{number}"
        }, f"#{number} needs an explicit issue/PR link"
    for reference in re.findall(r"`([^`]*\.md)`", text):
        assert any(
            reference.rsplit("/", 1)[-1] in url for url in links.values()
        ), reference
    for url in links.values():
        if "/blob/" in url:
            assert re.search(r"/blob/[0-9a-f]{40}/", url), url
        elif not url.startswith("https://"):
            assert (TRACKER.parent / url).is_file(), url


def test_tracker_dates_historical_status():
    text = TRACKER.read_text(encoding="utf-8")
    snapshot = re.search(r"(?m)^Snapshot date: `(\d{4}-\d{2}-\d{2})`", text)
    assert snapshot, "Historical issue/PR states need a snapshot date"
    date.fromisoformat(snapshot[1])
    assert "Current status:" not in text


def test_tracker_keeps_p2_validation_gaps_in_clean_gate():
    text = TRACKER.read_text(encoding="utf-8")
    related = text.split("Related ", 1)[1].split("## CLEAN gate", 1)[0]
    assert "non-blocking" not in related, "P2 gaps cannot bypass CLEAN"
    assert "P2" in related and "#70" in related
    gate = text.split("## CLEAN gate", 1)[1].split("## Evidence boundary")[0]
    assert "`not_planned`" in gate, "CLEAN needs closure or not_planned"
