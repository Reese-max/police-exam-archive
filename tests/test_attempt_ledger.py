import json
import shutil
import subprocess
from pathlib import Path

import pytest


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
        encoding="utf-8",
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


@pytest.mark.parametrize("scenario", {
    "source_metadata_and_serialized_locator_survive_export": r"""
const original = {...q, sourcePdf:'official.pdf', sourcePage:3, sourceSha256:'a'.repeat(64),
  sourceLocator:JSON.stringify({cat:'A', year:113, subject:'Law', no:1, file:'source.json', index:0})};
const event = ledger.createEvent({question:original, answerOutcome:'wrong'});
assert.equal(event.sourceLocator.subject, 'Law');
assert.equal(event.sourceMetadata.page, '3');
assert.equal(JSON.parse(event.sourceMetadata.locator).file, 'source.json');
ledger.replace([event]);
const payload = ledger.exportData(); ledger.clearLearnerData(); ledger.importData(payload);
assert.equal(ledger.getLedger()[0].sourceMetadata.sha256, 'a'.repeat(64));
""",
    "review_limit_matches_durable_checkpoint_bound": r"""
ledger.saveSettings({dailyQuestionLimit:201, dailyMinutes:1500});
assert.equal(ledger.getSettings().dailyMinutes, 1440);
ledger.saveSettings({dailyMinutes:0});
assert.equal(ledger.getSettings().dailyQuestionLimit, 200);
const pool = Array.from({length:201}, (_, index) => ({...q, no:index+1}));
assert.equal(ledger.buildQueue(pool, {now}).items.length, 200);
const exported = JSON.parse(ledger.exportData());
exported.reviewSettings.dailyQuestionLimit=201;
assert.throws(() => ledger.importData(exported));
""",
    "time_budget_limits_queue_and_backlog": r"""
const questions = Array.from({length: 20}, (_, index) => ({...q, no: index + 1}));
ledger.replace(questions.map(question => attempt(question, 'wrong', now)));
ledger.saveSettings({enabled: true, targetExamDate: '2026-09-30', dailyQuestionLimit:20, dailyMinutes:4, planningMinutesPerQuestion:2});
const queue = ledger.buildQueue(questions, {now});
assert.equal(queue.items.length, 2);
assert.equal(queue.capacity, 2);
assert.equal(queue.backlogCount, 18);
assert.equal(queue.overload, true);
assert.equal(queue.planning.status, 'ESTIMATED');
ledger.saveSettings({dailyMinutes:1});
assert.equal(ledger.buildQueue(questions, {now}).items.length, 0);
ledger.saveSettings({dailyMinutes:0});
assert.equal(ledger.buildQueue(questions, {now}).items.length, 20);
""",
    "bonus_alternative_and_finish_retry_facts": r"""
const questions = [{...q, no:1, ans:'送分'}, {...q, no:2, ans:'A或C'}];
ledger.recordQuiz({questions, answers:[null,2], attemptId:'owned-session', attemptedAt:now});
assert.deepEqual(Array.from(ledger.getLedger(), event => event.answerOutcome), ['correct','correct']);
ledger.recordQuiz({questions, answers:[null,2], attemptId:'owned-session', attemptedAt:now});
assert.equal(ledger.getLedger().length, 2);
ledger.recordQuiz({questions:[questions[1]], answers:[1], attemptId:'different-session', attemptedAt:now});
assert.equal(ledger.getLedger()[2].answerOutcome, 'wrong');
""",
    "passage_and_image_changes_invalidate_old_attempts": r"""
const original = {...q, passage:'原文章', optImageA:'images/original.png'};
ledger.replace([attempt(original, 'correct', now)]);
assert.equal(ledger.getReviewState({...original, passage:'更正文章'}, {now}).sourceCompat, 'stale');
assert.equal(ledger.getReviewState({...original, optImageA:'images/revised.png'}, {now}).sourceCompat, 'stale');
assert.equal(ledger.getReviewState(original, {now}).sourceCompat, 'current');
""",
    "compatible_relearning": r"""
const revised = { ...q, stem: 'revised', datasetVersion: 'v2' };
ledger.replace([attempt(q, 'wrong')]);
assert.equal(ledger.getReviewState(revised).sourceCompat, 'stale');
ledger.append(attempt(revised, 'correct'));
ledger.append(attempt(revised, 'correct'));
const state = ledger.getReviewState({ ...revised, datasetVersion: 'v3' });
assert.equal(state.sourceCompat, 'current');
assert.equal(state.compatibleAttempts, 2);
assert.equal(state.correctStreak, 2);
assert.equal(state.wrongCount, 0);
assert.equal(ledger.getLedger().length, 3);
""",
    "not_due": r"""
ledger.replace([attempt(q, 'correct', now)]);
assert.equal(ledger.buildQueue([q], { now }).items.length, 0);
""",
    "coverage_rotation": r"""
const questions = [q, { ...q, cat: 'B' }, { ...q, cat: 'C', sub: 'Other' }];
ledger.replace(questions.map(question => attempt(question, 'wrong')));
const visited = new Set();
for (let i = 0; i < questions.length; i++) {
  const options = { now, limit: 1 };
  const item = ledger.buildQueue(questions, options).items[0];
  assert.equal(item.questionId, ledger.buildQueue([...questions].reverse(), options).items[0].questionId);
  visited.add(item.question.cat);
  ledger.append(attempt(item.question, 'wrong', now));
}
assert.equal(visited.size, 3);
""",
    "priority_with_coverage": r"""
const weak = Array.from({ length: 5 }, (_, no) => ({ ...q, no: no + 1 }));
const unseen = Array.from({ length: 10 }, (_, no) => ({ ...q, cat: 'new' + no }));
ledger.replace(weak.map(question => attempt(question, 'wrong', now)));
const items = ledger.buildQueue([...weak, ...unseen], { now, limit: 5 }).items;
assert.ok(items.filter(item => item.category === 'urgent').length >= 3);
assert.ok(items.some(item => item.reasonCodes.includes('探索新題')));
""",
    "engine_propagates_storage_failure": r"""
vm.runInNewContext(fs.readFileSync(process.argv[1].replace('attempt-ledger.js', 'quiz-engine.js'), 'utf8'),
  { window, localStorage: window.localStorage });
window.QuizEngine.getState().questions = [q];
window.localStorage.setItem = () => { throw new Error('QuotaExceededError'); };
assert.throws(() => window.QuizEngine.saveHistory({ correct: 0, total: 1, pct: 0, elapsed: 0 }));
""",
    "stale_backlog_and_expired_deadline": r"""
const questions = Array.from({ length: 10 }, (_, no) => ({ ...q, no: no + 1 }));
ledger.replace(questions.map(question => attempt(question, 'wrong')));
ledger.saveSettings({ enabled: true, targetExamDate: '2026-09-30', dailyQuestionLimit: 1 });
const changed = questions.map(question => ({ ...question, stem: 'changed' }));
const queue = ledger.buildQueue(changed, { now });
assert.equal(queue.weakCount, 10);
assert.equal(queue.overload, true);
assert.equal(queue.backlogCount, 9);
ledger.saveSettings({ targetExamDate: '2026-09-29' });
assert.equal(ledger.buildQueue(changed, { now }).capacity, 0);
""",
    "settings_and_state_agree": r"""
ledger.replace([attempt(q, 'correct'), attempt(q, 'correct'), attempt(q, 'correct')]);
ledger.saveSettings({ enabled: true, targetExamDate: '2026-09-30', dailyMinutes: 0 });
assert.equal(ledger.getSettings().dailyMinutes, 0);
const state = ledger.getReviewState(q, { now });
assert.equal(state.dueAt, ledger.buildQueue([q], { now }).states[0].dueAt);
assert.ok(Date.parse(state.dueAt) <= new Date('2026-09-30T23:59:59.999').getTime());
ledger.saveSettings({ enabled: false });
assert.ok(Date.parse(ledger.getReviewState(q, { now }).dueAt) > Date.parse(state.dueAt));
""",
    "invalid_import_preserves_data": r"""
ledger.replace([attempt(q, 'correct')]);
const saved = store.get('exam-question-attempt-ledger');
const payload = JSON.parse(ledger.exportData());
const invalid = [
  { ...payload, schemaVersion: 2 },
  { ...payload, attemptLedger: [null] },
  ...[
    { answerOutcome: 'invented' }, { attemptedAt: 'invalid' },
    { questionId: 5 }, { chosenAnswer: 'E' }, { chosenAnswer: ['A'] }, { sourceLocator: null },
    { elapsedMs: -1 }, { markedReview: 'true' },
  ].map(patch => ({ ...payload, attemptLedger: [{ ...payload.attemptLedger[0], ...patch }] })),
  { ...payload, reviewSettings: { dailyQuestionLimit: 'oops' } },
];
for (const data of invalid) {
  assert.throws(() => ledger.importData(data));
  assert.equal(store.get('exam-question-attempt-ledger'), saved);
}
""",
    "storage_failure_and_import_rollback": r"""
ledger.replace([attempt(q, 'correct')]);
ledger.saveSettings({ dailyQuestionLimit: 5 });
const previous = new Map(store);
const payload = JSON.parse(ledger.exportData());
payload.attemptLedger = [attempt(q, 'wrong')];
payload.reviewSettings.dailyQuestionLimit = 10;
const setItem = window.localStorage.setItem;
window.localStorage.setItem = (key, value) => {
  if (key === 'exam-question-attempt-ledger') throw new Error('QuotaExceededError');
  setItem(key, value);
};
assert.throws(() => ledger.recordAttempt({ question: q, answerOutcome: 'wrong' }));
assert.equal(store.get('exam-question-attempt-ledger'), previous.get('exam-question-attempt-ledger'));
window.localStorage.setItem = (key, value) => {
  if (key === 'exam-review-settings') throw new Error('QuotaExceededError');
  setItem(key, value);
};
assert.throws(() => ledger.importData(payload));
assert.equal(store.get('exam-question-attempt-ledger'), previous.get('exam-question-attempt-ledger'));
assert.equal(store.get('exam-review-settings'), previous.get('exam-review-settings'));
""",
}.items(), ids=lambda value: value[0])
def test_attempt_ledger_regressions(scenario):
    _, script = scenario
    harness = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const store = new Map();
const window = { localStorage: {
  getItem: key => store.get(key) ?? null,
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: key => store.delete(key),
} };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), { window, Date });
const ledger = window.AttemptLedger;
const now = '2026-09-30T12:00:00.000Z';
const q = { cat: 'A', yr: 113, sub: 'Law', no: 1, stem: 'Q1', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A', datasetVersion: 'v1' };
const attempt = (question, answerOutcome, attemptedAt = '2026-09-29T00:00:00.000Z') =>
  ledger.createEvent({ question, answerOutcome, attemptedAt });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", harness + script, str(LEDGER)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
