"""Issue #69 regression tests — the checkpoint module contract.

Drives ``考古題網站/js/quiz-checkpoint.js`` under Node with an in-memory
localStorage stub and asserts its validation, save/load and clear behaviour:
round-tripping a live session, wall-clock deduction, clearing on finish and
failing safe on corrupt/stale/mismatched state.

The end-to-end wiring in ``考古題網站/quiz.html`` (start → answer/flag →
checkpoint → reload → resume → finish) is covered behaviourally in
``tests/test_quiz_session_flow.py``, which executes the real page script.
"""

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "考古題網站"
CHECKPOINT_JS = SITE / "js" / "quiz-checkpoint.js"

NODE = shutil.which("node")

if NODE is None and os.environ.get("REQUIRE_NODE_FOR_TESTS") == "1":
    raise RuntimeError("node is required to run the quiz.html checkpoint tests")

pytestmark = pytest.mark.skipif(NODE is None, reason="node runtime required for JS checkpoint tests")


def run_node(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, "-e", script],
        cwd=str(SITE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def assert_node_ok(proc: subprocess.CompletedProcess, marker: str) -> None:
    assert proc.returncode == 0, f"node exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert marker in proc.stdout, f"expected {marker!r} in stdout\n{proc.stdout}"


NODE_PRELUDE = """
const assert = require('assert');
const QC = require(%s);

function memStore() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => { m.set(k, String(v)); },
    removeItem: (k) => { m.delete(k); },
    dump: () => Object.fromEntries(m),
  };
}

const NOW = 1760000000000;

function fixtureQuestions(n) {
  return Array.from({ length: n }, (_, i) => ({
    subj: '115年 測試科目',
    stem: '第' + (i + 1) + '題題幹',
    opts: ['選項甲', '選項乙', '選項丙', '選項丁'],
    ans: i %% 4,
  }));
}

// Issue regression fixture: 10-question exam, 60 minutes,
// Q1-3 answered, Q4 flagged, position on Q5, timer advanced.
function inProgressState() {
  return {
    questions: fixtureQuestions(10),
    answers: [0, 1, 2, null, null, null, null, null, null, null],
    flags: [false, false, false, true, false, false, false, false, false, false],
    cur: 4,
    durSec: 3600,
    remain: 3300,
    elapsed: 300,
  };
}
""" % json.dumps(str(CHECKPOINT_JS))


def test_checkpoint_module_loadable() -> None:
    """quiz-checkpoint.js must exist, parse, and export the checkpoint API."""
    assert CHECKPOINT_JS.is_file(), "考古題網站/js/quiz-checkpoint.js is missing"
    proc = subprocess.run(
        [NODE, "--check", str(CHECKPOINT_JS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    proc = run_node(
        NODE_PRELUDE
        + textwrap.dedent(
            """
            for (const fn of ['save', 'load', 'clear', 'build', 'validate']) {
              assert.strictEqual(typeof QC[fn], 'function', fn + ' must be exported');
            }
            assert.strictEqual(typeof QC.KEY, 'string');
            assert.ok(QC.KEY.length > 0);
            console.log('module-ok');
            """
        )
    )
    assert_node_ok(proc, "module-ok")


def test_checkpoint_roundtrip_restores_in_progress_exam() -> None:
    """save() then load() on a fresh page must restore the identical session."""
    proc = run_node(
        NODE_PRELUDE
        + textwrap.dedent(
            """
            const store = memStore();
            const state = inProgressState();
            assert.strictEqual(QC.save(state, store, NOW), true, 'save must succeed');

            // Simulated reload at the same instant: identical session restored.
            const snap = QC.load(store, NOW);
            assert.ok(snap, 'checkpoint must be restorable');
            assert.deepStrictEqual(snap.questions, state.questions, 'same 10 questions');
            assert.deepStrictEqual(snap.answers, state.answers, 'same 3 answers');
            assert.deepStrictEqual(snap.flags, state.flags, 'same flag on Q4');
            assert.strictEqual(snap.cur, 4, 'resume on question 5');
            assert.strictEqual(snap.durSec, 3600);
            assert.strictEqual(snap.remain, 3300, 'bounded remaining time restored');
            assert.strictEqual(snap.elapsed, 300);

            // Reload 60 s later: wall-clock offline time is deducted so that
            // reloading cannot act as a free timer pause.
            const later = QC.load(store, NOW + 60000);
            assert.strictEqual(later.remain, 3240, 'offline time deducted from countdown');
            assert.strictEqual(later.elapsed, 360, 'offline time added to elapsed');

            // Exam expired while offline: remain clamps to 0 (auto-finish on resume).
            const store2 = memStore();
            QC.save(inProgressState(), store2, NOW);
            const expired = QC.load(store2, NOW + 4000 * 1000);
            assert.strictEqual(expired.remain, 0);
            assert.strictEqual(expired.elapsed, 4300);
            console.log('roundtrip-ok');
            """
        )
    )
    assert_node_ok(proc, "roundtrip-ok")


def test_finish_clears_checkpoint_and_does_not_resurrect() -> None:
    """Finishing an exam clears the checkpoint; a later load must not revive it."""
    proc = run_node(
        NODE_PRELUDE
        + textwrap.dedent(
            """
            const store = memStore();
            assert.strictEqual(QC.save(inProgressState(), store, NOW), true);
            assert.ok(QC.load(store, NOW), 'pre-finish checkpoint exists');

            QC.clear(store);                       // finish()
            assert.strictEqual(QC.load(store, NOW), null, 'checkpoint must be gone');
            assert.strictEqual(store.getItem(QC.KEY), null, 'key removed');
            assert.strictEqual(QC.load(store, NOW + 1000), null, 'must not resurrect');
            console.log('clear-ok');
            """
        )
    )
    assert_node_ok(proc, "clear-ok")


def test_corrupt_or_stale_checkpoint_fails_safe_to_setup() -> None:
    """Missing/corrupt/stale/mismatched checkpoints must load() as null."""
    proc = run_node(
        NODE_PRELUDE
        + textwrap.dedent(
            """
            const store = memStore();
            const expectNull = (label) => {
              const got = QC.load(store, NOW);
              assert.strictEqual(got, null, label + ' must fail safe to setup');
              assert.strictEqual(store.getItem(QC.KEY), null, label + ' must be cleared');
            };

            // Missing key.
            assert.strictEqual(QC.load(store, NOW), null);

            // Corrupt JSON.
            store.setItem(QC.KEY, '{not valid json');
            expectNull('corrupt JSON');

            // Non-object payloads.
            store.setItem(QC.KEY, JSON.stringify(42));
            expectNull('scalar payload');
            store.setItem(QC.KEY, JSON.stringify(['array']));
            expectNull('array payload');

            // Wrong schema version.
            const wrongVer = QC.build(inProgressState(), NOW);
            wrongVer.v = 99;
            store.setItem(QC.KEY, JSON.stringify(wrongVer));
            expectNull('wrong version');

            // Stale checkpoint (older than MAX_AGE_MS).
            const stale = QC.build(inProgressState(), NOW);
            stale.savedAt = NOW - QC.MAX_AGE_MS - 1;
            store.setItem(QC.KEY, JSON.stringify(stale));
            expectNull('stale checkpoint');

            // Mismatched answers length.
            let bad = QC.build(inProgressState(), NOW);
            bad.answers = bad.answers.slice(0, 5);
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('answers length mismatch');

            // Answer index out of range.
            bad = QC.build(inProgressState(), NOW);
            bad.answers[0] = 7;
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('answer out of range');

            // Flags length mismatch.
            bad = QC.build(inProgressState(), NOW);
            bad.flags = [];
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('flags mismatch');

            // cur out of bounds.
            bad = QC.build(inProgressState(), NOW);
            bad.cur = 10;
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('cur out of bounds');

            // Unbounded / tampered timer values.
            bad = QC.build(inProgressState(), NOW);
            bad.remain = 999999;
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('remain > durSec');
            bad = QC.build(inProgressState(), NOW);
            bad.durSec = 4500;
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('non-segment durSec');

            // Mismatched question shape.
            bad = QC.build(inProgressState(), NOW);
            bad.questions[3] = { stem: 'x' };
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('bad question shape');
            bad = QC.build(inProgressState(), NOW);
            bad.questions = [];
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('empty questions');

            // Crafted markup payload — legit snapshots are pre-escaped by
            // buildQuestions, so raw < > must be rejected rather than injected
            // into the DOM via innerHTML on restore.
            bad = QC.build(inProgressState(), NOW);
            bad.questions[0].stem = '<img src=x onerror=alert(1)>';
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('markup stem');
            bad = QC.build(inProgressState(), NOW);
            bad.questions[0].opts[1] = '<svg onload=alert(1)>';
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('markup opt');
            bad = QC.build(inProgressState(), NOW);
            bad.questions[0].subj = '115年 <b>測試</b>';
            store.setItem(QC.KEY, JSON.stringify(bad));
            expectNull('markup subj');
            console.log('corrupt-ok');
            """
        )
    )
    assert_node_ok(proc, "corrupt-ok")


def test_save_rejects_invalid_state_and_untimed_exam_roundtrip() -> None:
    """save() refuses nonsense state; an untimed (0-min) exam still restores."""
    proc = run_node(
        NODE_PRELUDE
        + textwrap.dedent(
            """
            const store = memStore();
            assert.strictEqual(QC.save(null, store, NOW), false);
            assert.strictEqual(QC.save({ questions: [] }, store, NOW), false);
            assert.strictEqual(store.getItem(QC.KEY), null, 'invalid saves must not write');

            const untimed = inProgressState();
            untimed.durSec = 0;
            untimed.remain = 0;
            untimed.elapsed = 120;
            assert.strictEqual(QC.save(untimed, store, NOW), true);
            const snap = QC.load(store, NOW + 5000);
            assert.ok(snap, 'untimed checkpoint must restore');
            assert.strictEqual(snap.durSec, 0);
            assert.strictEqual(snap.remain, 0);
            assert.strictEqual(snap.elapsed, 125, 'offline seconds accrue to elapsed');

            // A question with an empty stem is odd but renderable — it must not
            // silently disable checkpointing for the whole exam.
            const withEmptyStem = inProgressState();
            withEmptyStem.questions[2].stem = '';
            assert.strictEqual(QC.save(withEmptyStem, store, NOW), true, 'empty stem must still checkpoint');
            const restoredEmpty = QC.load(store, NOW);
            assert.strictEqual(restoredEmpty.questions[2].stem, '');
            console.log('untimed-ok');
            """
        )
    )
    assert_node_ok(proc, "untimed-ok")
