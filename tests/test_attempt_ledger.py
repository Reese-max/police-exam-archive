import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "考古題網站" / "js" / "attempt-ledger.js"


def test_attempt_ledger_contract_runs_in_node_vm():
    node = shutil.which("node")
    assert node, "node is required for the browser ledger contract test"

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const store = new Map();
const window = {
  localStorage: {
    getItem: key => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
  },
};
const context = { window, Date, JSON, Math, Number, Object, Array, String, Boolean, console };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const ledger = window.AttemptLedger;
if (!ledger) throw new Error('AttemptLedger was not exported');
const question = { cat: 'A', yr: 113, sub: '法規', no: 1, stem: 'Q1', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' };
const event = ledger.createEvent({
  question,
  attemptedAt: '2026-09-29T00:00:00.000Z',
  answerOutcome: 'wrong',
  chosenAnswer: 'B',
  markedReview: true,
});
ledger.replace([event]);
ledger.saveSettings({ enabled: true, targetExamDate: '2026-10-01', dailyQuestionLimit: 1 });
const queue = ledger.buildQueue([question], { now: '2026-09-30T00:00:00.000Z', limit: 1 });
const state = ledger.getReviewState(question, { now: '2026-09-30T00:00:00.000Z' });
const changed = ledger.getReviewState({ ...question, stem: 'Q1 revised' }, { now: '2026-09-30T00:00:00.000Z' });
process.stdout.write(JSON.stringify({ event, state, queue, changed, exportData: ledger.exportData() }));
"""
    result = subprocess.run(
        [node, "-e", harness, str(LEDGER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)

    assert payload["event"]["questionId"] == "A|113|法規|1"
    assert payload["event"]["answerOutcome"] == "wrong"
    assert payload["event"]["markedReview"] is True
    assert "上次答錯" in payload["state"]["reasonCodes"]
    assert "標記回顧" in payload["state"]["reasonCodes"]
    assert payload["queue"]["items"][0]["questionId"] == "A|113|法規|1"
    assert payload["changed"]["sourceCompat"] == "stale"
    assert payload["changed"]["compatibleAttempts"] == 0
    assert "attemptLedger" in payload["exportData"]
