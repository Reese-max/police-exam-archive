"""Keep verified import commits stable when only generated timestamps change."""
from pathlib import Path
import subprocess
import sys
import json
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_import_changes.py"
OLD = "2026-10-02T16:37:53+00:00"
NEW = "2026-10-03T07:30:00+00:00"
JSON_PATHS = ["考古題庫/115_import_manifest.json", "考古題庫/dataset_manifest.json"]
REPORT = "docs/115-import-report.md"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Import Guard Test")
    git(tmp_path, "config", "user.email", "import-guard@example.invalid")
    for path in JSON_PATHS:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"schema_version": 1, "generated_at": OLD, "counts": {"questions": 42518}}, ensure_ascii=False) + "\n", encoding="utf-8")
    target = tmp_path / REPORT
    target.parent.mkdir(parents=True)
    target.write_text("# 匯入報告\n\n- 執行時間：" + OLD + "\n- 題數：42,518\n", encoding="utf-8")
    git(tmp_path, "add", "--", *JSON_PATHS, REPORT)
    git(tmp_path, "commit", "-qm", "test baseline")
    return tmp_path


def classify(repository):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(repository)], capture_output=True, text=True)


def refresh_timestamps(repository):
    for path in JSON_PATHS + [REPORT]:
        target = repository / path
        target.write_text(target.read_text(encoding="utf-8").replace(OLD, NEW), encoding="utf-8")


def test_clean_repository_and_timestamp_only_updates_do_not_need_a_commit(repository):
    head = git(repository, "rev-parse", "HEAD")
    assert classify(repository).returncode == 1
    refresh_timestamps(repository)
    before = {path: (repository / path).read_bytes() for path in JSON_PATHS + [REPORT]}
    result = classify(repository)
    assert result.returncode == 1, result.stderr
    assert "Only generated timestamps" in result.stdout
    assert git(repository, "rev-parse", "HEAD") == head
    assert {path: (repository / path).read_bytes() for path in before} == before


@pytest.mark.parametrize("path", JSON_PATHS)
def test_substantive_json_changes_still_need_a_commit(repository, path):
    refresh_timestamps(repository)
    target = repository / path
    data = json.loads(target.read_text(encoding="utf-8"))
    data["counts"]["questions"] += 1
    target.write_text(json.dumps(data), encoding="utf-8")
    assert classify(repository).returncode == 0


def test_other_report_content_is_substantive(repository):
    refresh_timestamps(repository)
    path = repository / REPORT
    path.write_text(path.read_text(encoding="utf-8").replace("42,518", "42,519"), encoding="utf-8")
    assert classify(repository).returncode == 0


def test_untracked_new_data_is_substantive(repository):
    refresh_timestamps(repository)
    (repository / "新增試題.json").write_text("{}\n", encoding="utf-8")
    assert classify(repository).returncode == 0


def test_staged_data_changes_are_also_checked(repository):
    target = repository / JSON_PATHS[0]
    data = json.loads(target.read_text(encoding="utf-8"))
    data["schema_version"] = 2
    target.write_text(json.dumps(data), encoding="utf-8")
    git(repository, "add", "--", JSON_PATHS[0])
    assert classify(repository).returncode == 0


def test_deletion_is_substantive(repository):
    (repository / REPORT).unlink()
    assert classify(repository).returncode == 0


@pytest.mark.parametrize("bad", ["not a timestamp", None, 3, "2026-10-03"])
def test_invalid_generated_at_is_not_silently_ignored(repository, bad):
    path = repository / JSON_PATHS[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["generated_at"] = bad
    path.write_text(json.dumps(data), encoding="utf-8")
    result = classify(repository)
    assert result.returncode == 2
    assert result.stderr.startswith("Import commit guard failed:")



def test_bad_json_stops_the_commit_guard(repository):
    (repository / JSON_PATHS[0]).write_text("{", encoding="utf-8")
    result = classify(repository)
    assert result.returncode == 2
    assert result.stderr.startswith("Import commit guard failed:")


def test_git_failure_stops_instead_of_approving_a_commit(tmp_path):
    result = classify(tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("Import commit guard failed:")


def test_duplicate_report_time_lines_are_not_hidden(repository):
    path = repository / REPORT
    path.write_text(path.read_text(encoding="utf-8") + "- 執行時間：" + NEW + "\n", encoding="utf-8")
    result = classify(repository)
    assert result.returncode == 2
    assert result.stderr.startswith("Import commit guard failed:")

def test_json_type_changes_are_substantive(repository):
    path = repository / JSON_PATHS[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert classify(repository).returncode == 0


def test_duplicate_json_keys_stop_the_guard(repository):
    path = repository / JSON_PATHS[0]
    path.write_text('{"generated_at": "' + NEW + '", "schema_version": 1, "schema_version": 1}', encoding="utf-8")
    result = classify(repository)
    assert result.returncode == 2
    assert result.stderr.startswith("Import commit guard failed:")


def prepare_workflow_repository(repository):
    import shutil
    target = repository / "scripts" / "check_import_changes.py"
    target.parent.mkdir()
    shutil.copy2(SCRIPT, target)
    git(repository, "add", "--", "scripts/check_import_changes.py")
    git(repository, "commit", "-qm", "test workflow guard")
    origin = repository.parent / (repository.name + ".origin.git")
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    git(repository, "remote", "add", "origin", str(origin))
    git(repository, "push", "-q", "origin", "HEAD:import-guard-test")
    return origin


def run_actual_commit_step(repository):
    import os
    source = (ROOT / ".github/workflows/ingest-115-police.yml").read_text(encoding="utf-8")
    step = source.split("      - name: Commit verified data\n", 1)[1].split("      - name: Upload audit evidence\n", 1)[0]
    lines = step.split("        run: |\n", 1)[1].splitlines()
    shell = "\n".join(line[10:] for line in lines if line.strip())
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", shell], cwd=repository, env={**os.environ, "HEAD_BRANCH": "import-guard-test"}, capture_output=True, text=True)


def test_actual_workflow_does_not_push_timestamp_only_commit(repository):
    origin = prepare_workflow_repository(repository)
    head = git(repository, "rev-parse", "HEAD")
    refresh_timestamps(repository)
    result = run_actual_commit_step(repository)
    assert result.returncode == 0, result.stderr
    assert git(repository, "rev-parse", "HEAD") == head
    assert git(origin, "rev-parse", "refs/heads/import-guard-test") == head
    assert NEW in (repository / REPORT).read_text(encoding="utf-8")


def test_actual_workflow_still_pushes_verified_data_changes(repository):
    origin = prepare_workflow_repository(repository)
    head = git(repository, "rev-parse", "HEAD")
    refresh_timestamps(repository)
    path = repository / JSON_PATHS[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["counts"]["questions"] += 1
    path.write_text(json.dumps(data), encoding="utf-8")
    result = run_actual_commit_step(repository)
    assert result.returncode == 0, result.stderr
    current = git(repository, "rev-parse", "HEAD")
    assert current != head
    assert git(origin, "rev-parse", "refs/heads/import-guard-test") == current


def test_actual_workflow_stops_on_guard_error_without_committing(repository):
    origin = prepare_workflow_repository(repository)
    head = git(repository, "rev-parse", "HEAD")
    (repository / JSON_PATHS[0]).write_text("{", encoding="utf-8")
    result = run_actual_commit_step(repository)
    assert result.returncode == 2
    assert git(repository, "rev-parse", "HEAD") == head
    assert git(origin, "rev-parse", "refs/heads/import-guard-test") == head


def test_actual_workflow_stops_on_deep_json_without_committing(repository):
    origin = prepare_workflow_repository(repository)
    head = git(repository, "rev-parse", "HEAD")
    (repository / JSON_PATHS[0]).write_text(
        '{"generated_at": "' + NEW + '", "nested": ' + '[' * 20000 + '0' + ']' * 20000 + '}',
        encoding="utf-8",
    )
    guard = classify(repository)
    assert guard.returncode == 2
    assert guard.stderr.startswith("Import commit guard failed:")
    result = run_actual_commit_step(repository)
    assert result.returncode == 2
    assert git(repository, "rev-parse", "HEAD") == head
    assert git(origin, "rev-parse", "refs/heads/import-guard-test") == head


def test_actual_workflow_commits_report_mode_changes(repository):
    origin = prepare_workflow_repository(repository)
    git(repository, "config", "core.fileMode", "true")
    head = git(repository, "rev-parse", "HEAD")
    (repository / JSON_PATHS[0]).chmod(0o755)
    assert classify(repository).returncode == 0
    result = run_actual_commit_step(repository)
    assert result.returncode == 0, result.stderr
    current = git(repository, "rev-parse", "HEAD")
    assert current != head
    assert git(origin, "rev-parse", "refs/heads/import-guard-test") == current
    assert git(repository, "ls-tree", "HEAD", "--", JSON_PATHS[0]).startswith("100755 ")


def test_actual_workflow_commits_a_new_allowlisted_report(repository):
    path = JSON_PATHS[0]
    content = (repository / path).read_bytes()
    git(repository, "rm", "--", path)
    git(repository, "commit", "-qm", "test checkout without one report")
    origin = prepare_workflow_repository(repository)
    head = git(repository, "rev-parse", "HEAD")
    (repository / path).write_bytes(content)
    assert classify(repository).returncode == 0
    result = run_actual_commit_step(repository)
    assert result.returncode == 0, result.stderr
    current = git(repository, "rev-parse", "HEAD")
    assert current != head
    assert git(origin, "rev-parse", "refs/heads/import-guard-test") == current
    assert git(repository, "show", "HEAD:" + path).encode() == content
