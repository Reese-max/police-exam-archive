from pathlib import Path
import subprocess


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
