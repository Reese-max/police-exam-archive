"""Exercise the deployed category/layout sequence, not CI's /tmp-only build."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.apply_layout_refinements import check


ROOT = Path(__file__).resolve().parents[1]


def test_pages_workflow_keeps_layout_after_last_category_build(tmp_path):
    site = ROOT / "考古題網站"
    (tmp_path / "css").mkdir()
    shutil.copy2(site / "index.html", tmp_path / "index.html")
    shutil.copy2(site / "css/layout-refinements.css", tmp_path / "css/layout-refinements.css")
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    commands = re.findall(
        r"^\s+(?:run: )?python scripts/(build_category_pages|apply_layout_refinements)\.py([^\n]*)$",
        workflow,
        re.MULTILINE,
    )
    assert commands, "Pages category/layout commands were not found"
    assert ("build_category_pages", "") in commands
    assert ("apply_layout_refinements", "") in commands
    assert ("apply_layout_refinements", " --check") in commands
    for script, arguments in commands:
        args = arguments.split()
        assert not args or args == ["--check"], "Update regression for new workflow arguments"
        destination = "--output" if script == "build_category_pages" else "--site-root"
        subprocess.run(
            [sys.executable, str(ROOT / f"scripts/{script}.py"), *args, destination, str(tmp_path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    check(tmp_path)
