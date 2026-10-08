"""確認一次性資料流程不再自動寫入、開 PR 或合併 master。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_obsolete_one_time_workflows_are_removed() -> None:
    obsolete = {
        "finalize-115-pipeline.yml",
        "ingest-115-police.yml",
        "merge-115-after-ci.yml",
        "merge-verified-115.yml",
        "rescue-115-pipeline.yml",
    }
    assert not obsolete.intersection(p.name for p in WORKFLOWS.iterdir())


def test_remaining_workflows_cannot_merge_or_push_master() -> None:
    forbidden = ("gh pr merge", "git push origin master", "git push origin HEAD:master")
    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8").lower()
        assert not any(token in text for token in forbidden), workflow.name
