"""Issue #69 regression tests — the quiz.html exam lifecycle, executed.

The repository's enforced gate is ``python3 -m pytest -q``; the nested
Playwright suite is not part of it.  These tests therefore drive the real
inline script of ``考古題網站/quiz.html`` under Node through
``tests/quiz_dom_harness.js`` (a small DOM stub) and assert on what the page
actually does — start → answer/flag → checkpoint → reload → resume → finish,
plus discard and corrupt/expired-state cases.

``tests/test_quiz_checkpoint.py`` covers the checkpoint module's own contract;
everything here is behavioural, so deleting a wiring line from quiz.html turns
these red.
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
QUIZ_HTML = SITE / "quiz.html"
HARNESS = Path(__file__).resolve().parent / "quiz_dom_harness.js"

NODE = shutil.which("node")

# Wall-clock instant the fixture starts from (must match T0 in the JS prelude).
T0 = 1760000000000

if NODE is None and os.environ.get("REQUIRE_NODE_FOR_TESTS") == "1":
    raise RuntimeError("node is required to run the quiz.html checkpoint tests")

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
async function createPage(options) {
  const page = createQuizPage(options);
  await page.ready();
  return page;
}
async function open(store, clock, indexedDB) {
  return createPage({ html: HTML, checkpointJs: CHECKPOINT_JS, storage: store, clock: clock, indexedDB });
}

/* Start a 10-question / 60-minute exam and work it into the fixture state:
 * answer Q1-Q3, flag Q4, park on Q5, run the timer for 30 s. */
async function startWorkedExam(page) {
  await page.selectSeg('segCount', 10);
  await page.selectSeg('segTime', 60);
  await page.click('startBtn');
  await page.choose(0);                 // Q1
  await page.goto(1); await page.choose(1);   // Q2
  await page.goto(2); await page.choose(2);   // Q3
  await page.goto(3); await page.click('flagBtn');   // flag Q4
  await page.goto(4);                   // park on Q5
  await page.tick(30);                  // advance the timer by 30 s
  return page;
}

/* Mirror of quiz.html's fmtMMSS/fmt so expected labels are derived, not typed. */
function split(sec) {
  const m = Math.floor(sec / 60);
  return [m, sec - m * 60];
}
function fmtMMSS(sec) {
  const parts = split(sec);
  return String(parts[0]).padStart(2, '0') + ':' + String(parts[1]).padStart(2, '0');
}
function fmt(sec) {
  const parts = split(sec);
  return parts[0] + ':' + String(parts[1]).padStart(2, '0');
}

async function context(extra) {
  const store = readStore();
  const clock = { value: T0 };
  return { store: store, clock: clock, page: await open(store, clock) };
}
""" % json.dumps(str(ROOT))


def run_flow(script: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [NODE, "-e", PRELUDE + "\n(async()=>{\n" + textwrap.dedent(script) + "\n})().catch(error=>{console.error(error);process.exitCode=1;});"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, f"node exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "flow-ok" in proc.stdout, f"scenario did not complete\n{proc.stdout}\n{proc.stderr}"


def test_reload_restores_the_same_exam_and_finish_clears_the_checkpoint() -> None:
    """start → answer/flag → checkpoint → reload → resume → finish (issue scenario)."""
    run_flow(
        """
        const { store, clock, page } = await context();
        await startWorkedExam(page);

        const before = page.state();
        assert.strictEqual(before.view, 'exam', 'the exam view must be showing');
        assert.strictEqual(before.total, 10);
        assert.deepStrictEqual(before.answers.slice(0, 4), [0, 1, 2, null]);
        assert.strictEqual(before.flags[3], true, 'Q4 must be flagged');
        assert.strictEqual(before.cur, 4, 'pointer on Q5');
        assert.strictEqual(before.remain, 3600 - 30);

        // The tab is interrupted: the page is hidden and then reloaded.
        await page.pagehide();
        clock.value += 45 * 1000;

        const reloaded = await open(store, clock);
        let state = reloaded.state();
        assert.strictEqual(state.view, 'setup', 'a reload lands back on setup');
        assert.strictEqual(state.bannerHidden, false, 'the resume banner must be offered');
        assert.ok(state.resumeInfo.indexOf('第 5 / 10 題') !== -1, state.resumeInfo);
        assert.ok(state.resumeInfo.indexOf('剩餘 58:45') !== -1, state.resumeInfo);

        await reloaded.click('resumeBtn');
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
        await reloaded.click('submitBtn');
        state = reloaded.state();
        assert.strictEqual(state.view, 'result');
        assert.strictEqual(reloaded.checkpoint(), null, 'finish() must clear the checkpoint');
        assert.strictEqual(store.getItem(KEY), null, 'the storage key must be gone');

        // Unloading a finished exam must not write a fresh checkpoint: pagehide
        // still fires after finish(), so the examDone guard is load-bearing.
        await reloaded.pagehide();
        await reloaded.tick(3);
        assert.strictEqual(reloaded.checkpoint(), null, 'pagehide after finish must not resurrect');

        clock.value += 60 * 1000;
        const reopened = await open(store, clock);
        assert.strictEqual(reopened.state().bannerHidden, true, 'a completed exam must not resurrect');
        console.log('flow-ok');
        """
    )


def test_stale_tab_cannot_resurrect_an_exam_finished_in_another_tab() -> None:
    run_flow("""
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        const resumed = await open(store, clock);
        await resumed.click('resumeBtn');
        await resumed.click('submitBtn');
        assert.strictEqual(store.getItem(KEY), null);
        await page.goto(5); await page.tick(6); await page.pagehide();
        assert.strictEqual(store.getItem(KEY), null, 'stale original tab must not resurrect a completed exam');
        assert.strictEqual((await open(store, clock)).state().bannerHidden, true);
        console.log('flow-ok');
    """)


def test_resumed_tab_owns_writes_without_losing_its_new_answers() -> None:
    run_flow("""
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        const oldId = JSON.parse(store.getItem(KEY)).sessionId;
        const resumed = await open(store, clock); await resumed.click('resumeBtn');
        await resumed.goto(5); await resumed.choose(3);
        const current = store.getItem(KEY);
        assert.notStrictEqual(JSON.parse(current).sessionId, oldId, 'resume claims fresh writing ownership');
        await page.goto(6); await page.pagehide();
        assert.strictEqual(store.getItem(KEY), current, 'stale tab cannot erase recovered progress');
        assert.strictEqual(JSON.parse(current).answers[5], 3);
        await resumed.click('submitBtn'); await page.pagehide();
        assert.strictEqual(store.getItem(KEY), null);
        console.log('flow-ok');
    """)


def test_old_tab_cannot_overwrite_or_clear_a_new_exam() -> None:
    run_flow("""
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        const newer = await open(store, clock);
        await newer.click('discardResumeBtn');
        await startWorkedExam(newer);
        const current = store.getItem(KEY);
        await page.goto(6); await page.pagehide();
        assert.strictEqual(store.getItem(KEY), current, 'old tab cannot overwrite a new exam');
        await page.click('submitBtn');
        assert.strictEqual(store.getItem(KEY), current, 'old tab cannot clear a new exam');
        assert.strictEqual((await open(store, clock)).state().bannerHidden, false);
        console.log('flow-ok');
    """)


def test_legacy_checkpoint_can_resume_and_receive_a_session_identity() -> None:
    run_flow("""
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        const legacy = JSON.parse(store.getItem(KEY));
        delete legacy.sessionId;
        const legacyStore=readStore(); legacyStore.setItem(KEY, JSON.stringify(legacy));
        const restored = await open(legacyStore, clock);
        await restored.click('resumeBtn');
        assert.strictEqual(restored.state().view, 'exam', 'older v1 snapshot remains resumable');
        const upgraded = JSON.parse(legacyStore.getItem(KEY));
        assert.strictEqual(typeof upgraded.sessionId, 'string');
        assert.ok(upgraded.sessionId.length > 0);
        await restored.goto(6); await restored.pagehide();
        assert.strictEqual(JSON.parse(legacyStore.getItem(KEY)).cur, 6, 'upgraded owner can keep saving');
        console.log('flow-ok');
    """)


def test_stale_legacy_banner_cannot_discard_a_new_exam() -> None:
    run_flow("""
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        const legacy = JSON.parse(store.getItem(KEY)); delete legacy.sessionId;
        const legacyStore=readStore(); legacyStore.setItem(KEY, JSON.stringify(legacy));
        const stale = await open(legacyStore, clock);
        const newer = await open(legacyStore, clock);
        await newer.click('discardResumeBtn'); await startWorkedExam(newer);
        const current = legacyStore.getItem(KEY);
        await stale.click('discardResumeBtn');
        assert.strictEqual(legacyStore.getItem(KEY), current, 'stale legacy banner cannot discard newer exam');
        console.log('flow-ok');
    """)


def test_resume_charges_time_spent_on_the_setup_screen() -> None:
    """Idling on setup after a reload must not hand out free exam time.

    The checkpoint's wall-clock deduction is computed once when the page loads;
    if the banner is only a snapshot of that load, every minute spent deciding
    whether to resume is refunded to the countdown.
    """
    run_flow(
        """
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        await page.pagehide();
        clock.value += 60 * 1000;

        const reloaded = await open(store, clock);
        assert.strictEqual(reloaded.state().bannerHidden, false);

        // 10 more minutes sitting on the setup screen before clicking 繼續作答.
        clock.value += 10 * 60 * 1000;
        await reloaded.click('resumeBtn');

        const state = reloaded.state();
        assert.strictEqual(state.view, 'exam');
        assert.strictEqual(state.remain, 3600 - 30 - 60 - 600, 'all wall-clock time must be charged');
        assert.strictEqual(state.elapsed, 30 + 60 + 600);
        console.log('flow-ok');
        """
    )


def test_expired_countdown_is_never_offered_as_resumable() -> None:
    """A countdown that ran out while the surface was closed must fail safely.

    Resuming it as-is drops the user into an exam view stuck at 00:00 for a
    full tick before auto-submitting, and reports 用時 longer than the exam
    allows. The session must not even be advertised on the setup screen.
    """
    run_flow(
        """
        const { store, clock, page } = await context();
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 30);
        await page.click('startBtn');
        await page.choose(0);
        await page.tick(5);

        clock.value += 40 * 60 * 1000;   // closed far longer than the exam allows
        const reloaded = await open(store, clock);
        let state = reloaded.state();
        assert.strictEqual(state.bannerHidden, true, 'an expired session must not be offered');
        assert.ok(reloaded.get('resumeNote').textContent.indexOf('逾時') !== -1,
                  'the user must be told why: ' + reloaded.get('resumeNote').textContent);
        assert.strictEqual(reloaded.checkpoint(), null, 'the expired checkpoint must be cleared');

        // Clicking the (hidden) resume button must stay on setup and start nothing.
        await reloaded.click('resumeBtn');
        await reloaded.tick(5);
        state = reloaded.state();
        assert.strictEqual(state.view, 'setup', 'setup must stay usable');
        assert.strictEqual(state.examDone, false);

        // The setup screen still starts a normal exam.
        await reloaded.selectSeg('segCount', 10);
        await reloaded.selectSeg('segTime', 60);
        await reloaded.click('startBtn');
        assert.strictEqual(reloaded.state().view, 'exam');
        assert.strictEqual(reloaded.state().durSec, 3600);
        console.log('flow-ok');
        """
    )


def test_resume_aligns_the_setup_form_with_the_session() -> None:
    """「再考一次」 must not silently switch to the form defaults.

    The banner advertises a 10-question / 30-minute session; if the segmented
    controls stay on 20 題 / 60 分 the next exam is a different one.
    """
    run_flow(
        """
        const { store, clock, page } = await context();
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 30);
        await page.click('startBtn');
        await page.tick(5);
        await page.pagehide();

        clock.value += 30 * 1000;
        const reloaded = await open(store, clock);
        await reloaded.click('resumeBtn');
        assert.strictEqual(reloaded.state().view, 'exam');

        // Back to the form via 再考一次.
        await reloaded.click('submitBtn');
        await reloaded.click('retryBtn');
        assert.strictEqual(reloaded.state().view, 'setup');
        const selected = (id) => reloaded.get(id).children
          .filter((b) => b.classes.has('on'))
          .map((b) => b.dataset.v);
        assert.deepStrictEqual(selected('segCount'), ['10'], selected('segCount').join(','));
        assert.deepStrictEqual(selected('segTime'), ['30'], selected('segTime').join(','));
        console.log('flow-ok');
        """
    )


def test_unusable_storage_does_not_break_an_exam() -> None:
    """Private mode / a full quota must degrade to "no recovery", not an error."""
    run_flow(
        """
        const broken = {
          getItem: () => null,
          setItem: () => { throw new Error('QuotaExceededError'); },
          removeItem: () => {},
        };
        const clock = { value: T0 };
        const page = await open(broken, clock, null);
        assert.strictEqual(page.state().view, 'setup');

        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 30);
        await page.click('startBtn');
        await page.choose(0);
        await page.goto(1); await page.choose(1);
        await page.tick(2);
        await page.pagehide();

        const state = page.state();
        assert.strictEqual(state.view, 'exam', 'the exam must keep running');
        assert.strictEqual(state.cur, 1);
        assert.deepStrictEqual(state.answers.slice(0, 2), [0, 1]);
        assert.strictEqual(state.remain, 1800 - 2);

        await page.click('submitBtn');
        assert.strictEqual(page.state().view, 'result', 'finishing must still work');

        // And a fresh page over the same broken store simply offers nothing.
        const reopened = await open(broken, clock, null);
        assert.strictEqual(reopened.state().bannerHidden, true);
        console.log('flow-ok');
        """
    )


def test_discard_clears_the_checkpoint_and_a_new_exam_starts_clean() -> None:
    """The explicit discard path drops the saved session and starts fresh."""
    run_flow(
        """
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        await page.pagehide();
        clock.value += 30 * 1000;

        const reloaded = await open(store, clock);
        assert.strictEqual(reloaded.state().bannerHidden, false);
        await reloaded.click('discardResumeBtn');
        assert.strictEqual(reloaded.state().bannerHidden, true, 'discard must hide the banner');
        assert.strictEqual(reloaded.checkpoint(), null, 'discard must clear the checkpoint');

        // Starting an exam over a discarded session must not resurrect it.
        await reloaded.selectSeg('segCount', 20);
        await reloaded.selectSeg('segTime', 90);
        await reloaded.click('startBtn');
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

        await reloaded.pagehide();
        clock.value += 1000;
        const reopened = await open(store, clock);
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
            const page = await open(store, clock);
            const state = page.state();
            assert.strictEqual(state.bannerHidden, true, '%s: no banner for unusable state');
            assert.strictEqual(state.view, 'setup');
            assert.strictEqual(page.checkpoint(), null, '%s: unusable state must be cleared');

            // Setup must still be fully usable after falling back.
            await page.selectSeg('segCount', 10);
            await page.selectSeg('segTime', 30);
            await page.click('startBtn');
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
        const { page } = await context();
        assert.strictEqual(page.state().bannerHidden, true);
        assert.strictEqual(page.state().view, 'setup');
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 60);
        await page.click('startBtn');
        assert.strictEqual(page.state().view, 'exam');
        console.log('flow-ok');
        """
    )


def test_hidden_tab_flushes_the_checkpoint() -> None:
    """Mobile backgrounding kills ``pagehide`` on some engines, so
    ``visibilitychange`` must flush the in-progress session on its own."""
    run_flow(
        """
        const { store, clock, page } = await context();
        await startWorkedExam(page);
        await page.goto(6); await page.choose(3);
        // A one-second tick changes the timer without reaching the five-second
        // periodic flush. Keep the ownership key: deleting it models discard
        // in another tab, which the hidden tab must not undo.
        const before = page.checkpoint();
        await page.tick(1);
        assert.strictEqual(page.checkpoint().savedAt, before.savedAt);
        await page.hide();

        const checkpoint = page.checkpoint();
        assert.ok(checkpoint, 'hiding the tab must flush the checkpoint');
        assert.strictEqual(checkpoint.cur, 6, 'the flushed position must be current');
        assert.strictEqual(checkpoint.answers[6], 3, 'the last answer must be in the checkpoint');
        assert.strictEqual(checkpoint.answers[0], 0);
        assert.strictEqual(checkpoint.flags[3], true, 'the flag must be in the checkpoint');
        assert.strictEqual(checkpoint.savedAt, clock.value, 'visibilitychange must flush the current timer');
        assert.strictEqual(checkpoint.remain, before.remain - 1);
        console.log('flow-ok');
        """
    )


def test_timer_ticks_flush_the_checkpoint_without_any_click() -> None:
    """The timer path must checkpoint on its own.

    Nothing is clicked during these ticks, so if only interaction handlers
    wrote the checkpoint the stored snapshot would still carry the state and
    savedAt from the moment the exam started.
    """
    run_flow(
        """
        const { store, clock, page } = await context();
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 60);
        await page.click('startBtn');
        const started = page.checkpoint();
        assert.ok(started, 'starting an exam checkpoints it');
        const savedAt = started.savedAt;

        await page.tick(30);   // 30 s of pure timer ticks, no interaction

        const checkpoint = page.checkpoint();
        assert.strictEqual(checkpoint.savedAt, clock.value, 'the timer path must advance the checkpoint');
        assert.ok(checkpoint.savedAt > savedAt, 'the checkpoint must not be frozen at start');
        assert.strictEqual(checkpoint.remain, 3600 - 30);
        assert.strictEqual(checkpoint.elapsed, 30);
        console.log('flow-ok');
        """
    )


def test_resume_banner_keeps_counting_down_while_it_is_offered() -> None:
    """The banner is a decision screen; its numbers must not freeze at load."""
    run_flow(
        """
        const { store, clock, page } = await context();
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 60);
        await page.click('startBtn');
        await page.tick(10);
        await page.pagehide();

        clock.value += 60 * 1000;
        const reloaded = await open(store, clock);
        const offered = reloaded.state().resumeInfo;
        assert.ok(offered.indexOf('剩餘 ' + fmtMMSS(3600 - 10 - 60)) !== -1, offered);

        // 30 more seconds pass on the setup screen while the banner is up.
        clock.value += 30 * 1000;
        await reloaded.tick(1);
        const refreshed = reloaded.state().resumeInfo;
        assert.ok(refreshed.indexOf('剩餘 ' + fmtMMSS(3600 - 10 - 60 - 30 - 1)) !== -1,
                  'banner must keep counting down: ' + refreshed);
        assert.ok(refreshed.indexOf('第 1 / 10 題') !== -1, refreshed);

        // And it must not offer a session that another tab already finished.
        await page.click('submitBtn');
        await reloaded.tick(1);
        assert.strictEqual(reloaded.state().bannerHidden, true, 'a vanished session must drop the banner');
        console.log('flow-ok');
        """
    )


def test_every_setup_duration_round_trips() -> None:
    """Each #segTime duration must survive a checkpoint round-trip.

    quiz-checkpoint.js only accepts durations the setup screen offers, so a new
    segment without updating ALLOWED_DUR would silently make every exam of that
    length unresumable.
    """
    run_flow(
        """
        const store = readStore();
        const clock = { value: T0 };
        const first = await open(store, clock);
        const durations = first.get('segTime').children.map((b) => b.dataset.v);
        assert.deepStrictEqual(durations, ['0', '30', '60', '90', '120'],
                               'the setup segments changed; keep ALLOWED_DUR in sync');

        for (const minutes of durations) {
          const store2 = readStore();
          const clock2 = { value: T0 };
          const page = await open(store2, clock2);
          await page.selectSeg('segCount', 10);
          await page.selectSeg('segTime', minutes);
          await page.click('startBtn');
          await page.choose(0);
          await page.tick(3);
          const seconds = (+minutes) * 60;
          assert.ok(page.checkpoint(), minutes + ' min: an active exam must be checkpointed');
          await page.pagehide();

          clock2.value += 20 * 1000;
          const reloaded = await open(store2, clock2);
          assert.strictEqual(reloaded.state().bannerHidden, false, minutes + ' min: must be resumable');
          await reloaded.click('resumeBtn');
          const state = reloaded.state();
          assert.strictEqual(state.view, 'exam', minutes + ' min: resume must open the exam');
          assert.strictEqual(state.durSec, seconds, minutes + ' min: duration restored');
          const expectedRemain = seconds > 0 ? seconds - 3 - 20 : 0;
          assert.strictEqual(state.remain, expectedRemain, minutes + ' min: countdown restored');
          assert.strictEqual(state.answers[0], 0, minutes + ' min: answer restored');
          assert.strictEqual(state.selectedChoice, '0', minutes + ' min: selection repainted');
          console.log('flow-ok');
        }
        """
    )


def test_untimed_exam_resumes_with_elapsed_time() -> None:
    """不限時 exams have no countdown, so elapsed time is the only timer state."""
    run_flow(
        """
        const { store, clock, page } = await context();
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 0);
        await page.click('startBtn');
        assert.strictEqual(page.state().durSec, 0);
        assert.strictEqual(page.state().timerText, '00:00', 'an untimed exam starts at zero');
        await page.choose(0);
        await page.tick(7);
        await page.pagehide();

        clock.value += 30 * 1000;
        const reloaded = await open(store, clock);
        const state = reloaded.state();
        assert.strictEqual(state.bannerHidden, false);
        assert.ok(state.resumeInfo.indexOf('已作答 ' + fmt(7 + 30)) !== -1, state.resumeInfo);

        await reloaded.click('resumeBtn');
        const resumed = reloaded.state();
        assert.strictEqual(resumed.view, 'exam');
        assert.strictEqual(resumed.durSec, 0);
        assert.strictEqual(resumed.remain, 0, 'an untimed exam has no countdown');
        assert.strictEqual(resumed.elapsed, 37);
        assert.strictEqual(resumed.timerText, fmtMMSS(37), 'the elapsed timer must be repainted');
        assert.strictEqual(resumed.timerWarn, false);

        await reloaded.tick(5);
        assert.strictEqual(reloaded.state().elapsed, 42);
        assert.strictEqual(reloaded.state().timerText, fmtMMSS(42));

        // Timer writes are throttled, so the stored snapshot may lag by the
        // throttle window; load() reconciles it from savedAt.
        const checkpoint = reloaded.checkpoint();
        assert.ok(checkpoint, 'untimed exams must checkpoint too');
        assert.ok(checkpoint.elapsed >= 37 && checkpoint.elapsed <= 42, checkpoint.elapsed);
        assert.ok(checkpoint.savedAt >= clock.value - 5000, 'the checkpoint must not fall stale');

        await reloaded.pagehide();
        clock.value += 10 * 1000;
        const again = await open(store, clock);
        assert.strictEqual(again.state().bannerHidden, false);
        await again.click('resumeBtn');
        assert.strictEqual(again.state().elapsed, 52, 'a reload must reconcile the throttled clock');
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
        const page = await createPage({
          html: HTML, checkpointJs: CHECKPOINT_JS, storage: store, clock: clock,
          pool: %s,
        });
        await page.selectSeg('segCount', 10);
        await page.selectSeg('segTime', 60);
        await page.click('startBtn');

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
