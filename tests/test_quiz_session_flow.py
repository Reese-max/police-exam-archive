"""Issue #69 regression tests — the quiz.html exam lifecycle, executed.

The repository's enforced gate is ``python3 -m pytest -q``; the nested
Playwright suite is not part of it.  These tests therefore drive the real
inline script of ``考古題網站/quiz.html`` under Node through
``tests/quiz_dom_harness.js`` (a small DOM stub) and assert on what the page
actually does — start → answer/flag → checkpoint → reload → resume → finish,
plus discard and corrupt/expired-state cases.

Structural grep assertions over quiz.html live in
``tests/test_quiz_checkpoint.py``; everything here is behavioural, so deleting
a wiring line from quiz.html turns these red.
"""

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "考古題網站"
QUIZ_HTML = SITE / "quiz.html"
HARNESS = Path(__file__).resolve().parent / "quiz_dom_harness.js"

NODE = shutil.which("node")

# Wall-clock instant the fixture starts from (must match T0 in the JS prelude).
T0 = 1760000000000

pytestmark = pytest.mark.skipif(NODE is None, reason="node runtime required for quiz.html flow tests")

# Deterministic 10-question fixture: the issue's regression scenario is a
# 10-question / 60-minute exam with Q1-3 answered, Q4 flagged and the pointer
# left on Q5.
PRELUDE = """
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const ROOT = %s;
const { createQuizPage, readStore } = require(path.join(ROOT, 'tests', 'quiz_dom_harness.js'));
const HTML = fs.readFileSync(path.join(ROOT, '考古題網站', 'quiz.html'), 'utf8');
const CHECKPOINT_JS = path.join(ROOT, '考古題網站', 'js', 'quiz-checkpoint.js');

const T0 = 1760000000000;
const KEY = 'exam-quiz-active';

/* Open a page over `store` at wall-clock `now` (defaults to the shared clock). */
function open(store, clock) {
  return createQuizPage({ html: HTML, checkpointJs: CHECKPOINT_JS, storage: store, clock: clock });
}

/* Start a 10-question / 60-minute exam and work it into the fixture state:
 * answer Q1-Q3, flag Q4, park on Q5, run the timer for 30 s. */
function startWorkedExam(page) {
  page.selectSeg('segCount', 10);
  page.selectSeg('segTime', 60);
  page.click('startBtn');
  page.choose(0);                 // Q1
  page.goto(1); page.choose(1);   // Q2
  page.goto(2); page.choose(2);   // Q3
  page.goto(3); page.click('flagBtn');   // flag Q4
  page.goto(4);                   // park on Q5
  page.tick(30);                  // advance the timer by 30 s
  return page;
}

function context(extra) {
  const store = readStore();
  const clock = { value: T0 };
  return { store: store, clock: clock, page: open(store, clock) };
}
""" % json.dumps(str(ROOT))


def run_flow(script: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [NODE, "-e", PRELUDE + textwrap.dedent(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"node exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "flow-ok" in proc.stdout, f"scenario did not complete\n{proc.stdout}\n{proc.stderr}"


def test_reload_restores_the_same_exam_and_finish_clears_the_checkpoint() -> None:
    """start → answer/flag → checkpoint → reload → resume → finish (issue scenario)."""
    run_flow(
        """
        const { store, clock, page } = context();
        startWorkedExam(page);

        const before = page.state();
        assert.strictEqual(before.view, 'exam', 'the exam view must be showing');
        assert.strictEqual(before.total, 10);
        assert.deepStrictEqual(before.answers.slice(0, 4), [0, 1, 2, null]);
        assert.strictEqual(before.flags[3], true, 'Q4 must be flagged');
        assert.strictEqual(before.cur, 4, 'pointer on Q5');
        assert.strictEqual(before.remain, 3600 - 30);

        // The tab is interrupted: the page is hidden and then reloaded.
        page.pagehide();
        clock.value += 45 * 1000;

        const reloaded = open(store, clock);
        let state = reloaded.state();
        assert.strictEqual(state.view, 'setup', 'a reload lands back on setup');
        assert.strictEqual(state.bannerHidden, false, 'the resume banner must be offered');
        assert.ok(state.resumeInfo.indexOf('第 5 / 10 題') !== -1, state.resumeInfo);
        assert.ok(state.resumeInfo.indexOf('剩餘 58:45') !== -1, state.resumeInfo);

        reloaded.click('resumeBtn');
        state = reloaded.state();
        assert.strictEqual(state.view, 'exam', 'resume must show the exam, not setup');
        assert.strictEqual(state.cur, 4, 'same position');
        assert.strictEqual(state.curNum, '5');
        assert.strictEqual(state.totalNum, '10');
        assert.deepStrictEqual(state.stems, before.stems, 'the same 10 questions');
        assert.deepStrictEqual(state.answers, before.answers, 'the same 3 answers');
        assert.deepStrictEqual(state.flags, before.flags, 'the same flag');
        assert.strictEqual(state.selectedChoice, undefined, 'Q5 is unanswered');
        assert.strictEqual(state.remain, 3600 - 30 - 45, 'wall-clock offline time is charged');
        assert.strictEqual(state.elapsed, 30 + 45);

        // Finishing clears the checkpoint and a later load must not resurrect it.
        reloaded.click('submitBtn');
        state = reloaded.state();
        assert.strictEqual(state.view, 'result');
        assert.strictEqual(reloaded.checkpoint(), null, 'finish() must clear the checkpoint');
        assert.strictEqual(store.getItem(KEY), null, 'the storage key must be gone');

        // Unloading a finished exam must not write a fresh checkpoint: pagehide
        // still fires after finish(), so the examDone guard is load-bearing.
        reloaded.pagehide();
        reloaded.tick(3);
        assert.strictEqual(reloaded.checkpoint(), null, 'pagehide after finish must not resurrect');

        clock.value += 60 * 1000;
        const reopened = open(store, clock);
        assert.strictEqual(reopened.state().bannerHidden, true, 'a completed exam must not resurrect');
        console.log('flow-ok');
        """
    )


def test_resume_charges_time_spent_on_the_setup_screen() -> None:
    """Idling on setup after a reload must not hand out free exam time.

    The checkpoint's wall-clock deduction is computed once when the page loads;
    if the banner is only a snapshot of that load, every minute spent deciding
    whether to resume is refunded to the countdown.
    """
    run_flow(
        """
        const { store, clock, page } = context();
        startWorkedExam(page);
        page.pagehide();
        clock.value += 60 * 1000;

        const reloaded = open(store, clock);
        assert.strictEqual(reloaded.state().bannerHidden, false);

        // 10 more minutes sitting on the setup screen before clicking 繼續作答.
        clock.value += 10 * 60 * 1000;
        reloaded.click('resumeBtn');

        const state = reloaded.state();
        assert.strictEqual(state.view, 'exam');
        assert.strictEqual(state.remain, 3600 - 30 - 60 - 600, 'all wall-clock time must be charged');
        assert.strictEqual(state.elapsed, 30 + 60 + 600);
        console.log('flow-ok');
        """
    )


def test_expired_countdown_does_not_resume_into_a_dead_exam_view() -> None:
    """A countdown that ran out while the surface was closed must fail safely.

    Resuming it as-is drops the user into an exam view stuck at 00:00 for a
    full tick before auto-submitting, and reports 用時 longer than the exam
    allows.
    """
    run_flow(
        """
        const { store, clock, page } = context();
        page.selectSeg('segCount', 10);
        page.selectSeg('segTime', 30);
        page.click('startBtn');
        page.choose(0);
        page.tick(5);

        clock.value += 40 * 60 * 1000;   // closed far longer than the exam allows
        const reloaded = open(store, clock);
        reloaded.click('resumeBtn');

        const state = reloaded.state();
        assert.notStrictEqual(state.view, 'exam', 'an expired exam must not open the exam view');
        assert.strictEqual(state.bannerHidden, true, 'the stale banner must be dismissed');
        assert.strictEqual(reloaded.checkpoint(), null, 'the expired checkpoint must be cleared');

        // And no phantom timer is left ticking.
        reloaded.tick(5);
        assert.strictEqual(reloaded.state().view, 'setup', 'setup must stay usable');
        console.log('flow-ok');
        """
    )


def test_discard_clears_the_checkpoint_and_a_new_exam_starts_clean() -> None:
    """The explicit discard path drops the saved session and starts fresh."""
    run_flow(
        """
        const { store, clock, page } = context();
        startWorkedExam(page);
        page.pagehide();
        clock.value += 30 * 1000;

        const reloaded = open(store, clock);
        assert.strictEqual(reloaded.state().bannerHidden, false);
        reloaded.click('discardResumeBtn');
        assert.strictEqual(reloaded.state().bannerHidden, true, 'discard must hide the banner');
        assert.strictEqual(reloaded.checkpoint(), null, 'discard must clear the checkpoint');

        // Starting an exam over a discarded session must not resurrect it.
        reloaded.selectSeg('segCount', 20);
        reloaded.selectSeg('segTime', 90);
        reloaded.click('startBtn');
        const fresh = reloaded.state();
        assert.strictEqual(fresh.view, 'exam');
        assert.strictEqual(fresh.total, 20);
        assert.strictEqual(fresh.cur, 0);
        assert.deepStrictEqual(fresh.answers, new Array(20).fill(null));
        assert.deepStrictEqual(fresh.flags, new Array(20).fill(false));
        assert.strictEqual(fresh.durSec, 90 * 60);
        assert.strictEqual(fresh.remain, 90 * 60);

        // And the brand-new session is what gets checkpointed, not the old one.
        const checkpoint = reloaded.checkpoint();
        assert.ok(checkpoint, 'the new exam must be checkpointed');
        assert.strictEqual(checkpoint.cur, 0);
        assert.strictEqual(checkpoint.questions.length, 20);

        reloaded.pagehide();
        clock.value += 1000;
        const reopened = open(store, clock);
        assert.strictEqual(reopened.state().bannerHidden, false, 'the new session is resumable');
        assert.ok(reopened.state().resumeInfo.indexOf('第 1 / 20 題') !== -1, reopened.state().resumeInfo);
        console.log('flow-ok');
        """
    )


def test_corrupt_or_mismatched_checkpoint_falls_back_to_setup() -> None:
    """Broken stored state must never produce a mismatched exam."""
    for label, payload in (
        ("corrupt JSON", "{not json"),
        ("answers shorter than questions", json.dumps(
            {"v": 1, "savedAt": T0, "questions": [{"subj": "a", "stem": "b", "opts": ["w", "x", "y", "z"], "ans": 0}],
             "answers": [0, 0], "flags": [False], "cur": 0, "durSec": 3600, "remain": 3600, "elapsed": 0},
            ensure_ascii=False)),
        ("answer index out of range", json.dumps(
            {"v": 1, "savedAt": T0, "questions": [{"subj": "a", "stem": "b", "opts": ["w", "x", "y", "z"], "ans": 0}],
             "answers": [9], "flags": [False], "cur": 0, "durSec": 3600, "remain": 3600, "elapsed": 0},
            ensure_ascii=False)),
        ("unknown schema version", json.dumps(
            {"v": 99, "savedAt": T0, "questions": [{"subj": "a", "stem": "b", "opts": ["w", "x", "y", "z"], "ans": 0}],
             "answers": [None], "flags": [False], "cur": 0, "durSec": 3600, "remain": 3600, "elapsed": 0},
            ensure_ascii=False)),
        ("duration outside the setup segments", json.dumps(
            {"v": 1, "savedAt": T0, "questions": [{"subj": "a", "stem": "b", "opts": ["w", "x", "y", "z"], "ans": 0}],
             "answers": [None], "flags": [False], "cur": 0, "durSec": 4500, "remain": 4500, "elapsed": 0},
            ensure_ascii=False)),
        ("stale checkpoint", json.dumps(
            {"v": 1, "savedAt": T0 - 25 * 60 * 60 * 1000,
             "questions": [{"subj": "a", "stem": "b", "opts": ["w", "x", "y", "z"], "ans": 0}],
             "answers": [None], "flags": [False], "cur": 0, "durSec": 3600, "remain": 3600, "elapsed": 0},
            ensure_ascii=False)),
    ):
        run_flow(
            """
            const store = readStore();
            const clock = { value: T0 };
            store.setItem(KEY, %s);
            const page = open(store, clock);
            const state = page.state();
            assert.strictEqual(state.bannerHidden, true, '%s: no banner for unusable state');
            assert.strictEqual(state.view, 'setup');
            assert.strictEqual(page.checkpoint(), null, '%s: unusable state must be cleared');

            // Setup must still be fully usable after falling back.
            page.selectSeg('segCount', 10);
            page.selectSeg('segTime', 30);
            page.click('startBtn');
            assert.strictEqual(page.state().view, 'exam');
            assert.strictEqual(page.state().total, 10);
            console.log('flow-ok');
            """
            % (json.dumps(payload), label, label)
        )


def test_no_checkpoint_shows_no_banner() -> None:
    """A first-time visitor must not be offered a resume."""
    run_flow(
        """
        const { page } = context();
        assert.strictEqual(page.state().bannerHidden, true);
        assert.strictEqual(page.state().view, 'setup');
        page.selectSeg('segCount', 10);
        page.selectSeg('segTime', 60);
        page.click('startBtn');
        assert.strictEqual(page.state().view, 'exam');
        console.log('flow-ok');
        """
    )


def test_hidden_tab_flushes_the_checkpoint() -> None:
    """Mobile backgrounding kills ``pagehide`` on some engines, so
    ``visibilitychange`` must flush the in-progress session on its own."""
    run_flow(
        """
        const { store, clock, page } = context();
        startWorkedExam(page);
        store.removeItem(KEY);        // the checkpoint is lost to a hard kill
        page.goto(6); page.choose(3);
        page.hide();

        const checkpoint = page.checkpoint();
        assert.ok(checkpoint, 'hiding the tab must flush the checkpoint');
        assert.strictEqual(checkpoint.cur, 6, 'the flushed position must be current');
        assert.strictEqual(checkpoint.answers[6], 3, 'the last answer must be in the checkpoint');
        assert.strictEqual(checkpoint.answers[0], 0);
        assert.strictEqual(checkpoint.flags[3], true, 'the flag must be in the checkpoint');
        console.log('flow-ok');
        """
    )


def test_question_text_is_escaped_before_it_is_checkpointed_and_rendered() -> None:
    """buildQuestions output is persisted and re-rendered through innerHTML.

    validate() rejects raw < >, so an unescaped field would both re-open the
    markup hole and silently disable checkpointing for the whole exam.
    """
    markup_pool = [
        {
            "yr": 114,
            "sub": "腳本<script>alert(1)</script>",
            "stem": "題幹<img src=x onerror=alert(1)>",
            "optA": "<b>甲</b>", "optB": "乙", "optC": "丙", "optD": "丁",
            "ans": "A",
        }
    ] * 12
    run_flow(
        """
        const store = readStore();
        const clock = { value: T0 };
        const page = createQuizPage({
          html: HTML, checkpointJs: CHECKPOINT_JS, storage: store, clock: clock,
          pool: %s,
        });
        page.selectSeg('segCount', 10);
        page.selectSeg('segTime', 60);
        page.click('startBtn');

        const rendered = page.get('qStem').innerHTML;
        assert.ok(rendered.indexOf('<img') === -1, 'raw markup must not reach innerHTML: ' + rendered);
        assert.ok(rendered.indexOf('&lt;img') !== -1, 'markup must be escaped: ' + rendered);

        const checkpoint = page.checkpoint();
        assert.ok(checkpoint, 'escaped questions must still be checkpointable');
        assert.strictEqual(checkpoint.questions.length, 10);
        assert.ok(checkpoint.questions[0].stem.indexOf('<') === -1);
        assert.ok(checkpoint.questions[0].subj.indexOf('<') === -1);
        console.log('flow-ok');
        """
        % json.dumps(markup_pool, ensure_ascii=False)
    )