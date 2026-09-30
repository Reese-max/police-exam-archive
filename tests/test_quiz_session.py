"""Contract checks for the browser checkpoint module.

The repository's primary verifier is pytest, while the site behavior is
covered by Playwright in the nested site project.  This test executes the
same browser module in a small Node VM so the primary suite also guards the
checkpoint validation contract.
"""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "考古題網站" / "js" / "quiz-session.js"


def test_quiz_session_rejects_corrupt_and_unsafe_checkpoints() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');

const values = new Map();
const context = {
  window: {},
  localStorage: {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
  },
  Date: { now: () => 1000000 },
  isFinite,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const session = context.window.QuizSession;
if (!session) throw new Error('QuizSession was not installed');

const question = { subj: 'subject', stem: 'stem', opts: ['a', 'b', 'c', 'd'], ans: 0 };
session.save({
  force: true,
  sessionId: 'test-session-123',
  timed: true,
  questions: [question],
  answers: [null],
  flags: [false],
  cur: 0,
  durSec: 60,
  remain: 60,
  elapsed: 0,
});
if (!session.load(1000000)) throw new Error('valid checkpoint did not load');

const key = session.KEY;
const saved = JSON.parse(values.get(key));
values.set(key, JSON.stringify({ ...saved, timed: false }));
if (session.load(1000000) !== null) throw new Error('inconsistent timer mode was accepted');

session.save({
  force: true,
  sessionId: 'test-session-123',
  timed: true,
  questions: [question],
  answers: [null],
  flags: [false],
  cur: 0,
  durSec: 60,
  remain: 60,
  elapsed: 0,
});
const unsafe = JSON.parse(values.get(key));
unsafe.questions[0].stem = '<img src=x onerror=alert(1)>';
values.set(key, JSON.stringify(unsafe));
if (session.load(1000000) !== null) throw new Error('unsafe question text was accepted');
"""
    result = subprocess.run(
        ["node", "-e", script, str(MODULE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
