const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const sourcePath = path.join(__dirname, '..', '考古題網站', 'js', 'review-queue.js');
const source = fs.readFileSync(sourcePath, 'utf8');

function makeStorage() {
  const values = new Map();
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
    has(key) { return values.has(key); },
  };
}

const window = {};
vm.runInNewContext(source, { window }, { filename: sourcePath });
const ReviewQueue = window.ReviewQueue;
assert.ok(ReviewQueue, 'ReviewQueue should be exposed for the browser');

const storage = makeStorage();
const now = '2026-09-30T12:00:00.000Z';
const datasetVersion = 'search-index-fixture-v1';

function question(category, subject, number, stem = `${category}-${number}`) {
  return {
    cat: category,
    yr: 115,
    sub: subject,
    no: String(number),
    type: 'choice',
    stem,
    optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A',
  };
}

const a = Array.from({ length: 5 }, (_, i) => question('A', '科目 A', i + 1));
const b = Array.from({ length: 5 }, (_, i) => question('B', '科目 B', i + 1));
const c = Array.from({ length: 5 }, (_, i) => question('C', '科目 C', i + 1));
const d = Array.from({ length: 5 }, (_, i) => question('D', '科目 D', i + 1));

// Five weak questions should remain first-class ledger events, including a marked item.
a.forEach((q, i) => ReviewQueue.recordQuizAttempt(
  [q], ['B'], [i === 0], { attemptedAt: '2026-09-29T12:00:00.000Z', datasetVersion, quizMode: 'simulated' }, storage,
));

// B is old enough to be due; C is an untouched coverage opportunity; D was recently correct.
b.forEach((q, i) => ReviewQueue.recordQuizAttempt(
  [q], ['A'], [false], { attemptedAt: '2026-08-01T12:00:00.000Z', datasetVersion, quizMode: 'simulated' }, storage,
));
d.forEach((q) => ReviewQueue.recordQuizAttempt(
  [q], ['A'], [false], { attemptedAt: '2026-09-29T12:00:00.000Z', datasetVersion, quizMode: 'simulated' }, storage,
));

const aState = ReviewQueue.deriveReviewState(a[0], ReviewQueue.getLedger(storage).attempts, now, datasetVersion);
assert.equal(aState.attempts, 1);
assert.equal(aState.wrong_count, 1);
assert.equal(aState.correct_streak, 0);
assert.ok(aState.reason_codes.includes('last_wrong'));
assert.ok(aState.reason_codes.includes('marked_review'));
assert.ok(ReviewQueue.getLedger(storage).attempts[0].outcome_codes.includes('marked_review'));

const streakQuestion = question('streak', '連續測試', 1);
ReviewQueue.recordQuizAttempt([streakQuestion], ['B'], [false], { attemptedAt: '2026-09-27T12:00:00.000Z', datasetVersion }, storage);
ReviewQueue.recordQuizAttempt([streakQuestion], ['B'], [false], { attemptedAt: '2026-09-28T12:00:00.000Z', datasetVersion }, storage);
const streakState = ReviewQueue.deriveReviewState(streakQuestion, ReviewQueue.getLedger(storage).attempts, now, datasetVersion);
assert.equal(streakState.wrong_count, 2);
assert.ok(streakState.reason_codes.includes('repeated_wrong'));

const correctStreakQuestion = question('streak', '連續測試', 2);
ReviewQueue.recordQuizAttempt([correctStreakQuestion], ['A'], [false], { attemptedAt: '2026-09-20T12:00:00.000Z', datasetVersion }, storage);
ReviewQueue.recordQuizAttempt([correctStreakQuestion], ['A'], [false], { attemptedAt: '2026-09-25T12:00:00.000Z', datasetVersion }, storage);
const correctStreakState = ReviewQueue.deriveReviewState(correctStreakQuestion, ReviewQueue.getLedger(storage).attempts, now, datasetVersion);
assert.equal(correctStreakState.correct_streak, 2);
assert.equal(correctStreakState.due_at, '2026-10-02T12:00:00.000Z');

// wrong → correct → wrong is not "連續答錯": the streak label must be consecutive.
const mixedQuestion = question('streak', '連續測試', 3);
ReviewQueue.recordQuizAttempt([mixedQuestion], ['B'], [false], { attemptedAt: '2026-09-25T12:00:00.000Z', datasetVersion }, storage);
ReviewQueue.recordQuizAttempt([mixedQuestion], ['A'], [false], { attemptedAt: '2026-09-26T12:00:00.000Z', datasetVersion }, storage);
ReviewQueue.recordQuizAttempt([mixedQuestion], ['B'], [false], { attemptedAt: '2026-09-27T12:00:00.000Z', datasetVersion }, storage);
const mixedState = ReviewQueue.deriveReviewState(mixedQuestion, ReviewQueue.getLedger(storage).attempts, now, datasetVersion);
assert.equal(mixedState.wrong_count, 2);
assert.ok(mixedState.reason_codes.includes('last_wrong'));
assert.ok(!mixedState.reason_codes.includes('repeated_wrong'));

const settings = ReviewQueue.normalizeSettings({
  deadline_enabled: true,
  target_date: '2026-10-14',
  daily_question_limit: 5,
  daily_minutes: 40,
});

// An unanswered attempt must enter the queue under the unanswered reason.
const skippedQuestion = question('skip', '未答測試', 1);
ReviewQueue.recordQuizAttempt([skippedQuestion], [null], [false], { attemptedAt: now, datasetVersion }, storage);
const skipState = ReviewQueue.deriveReviewState(skippedQuestion, ReviewQueue.getLedger(storage).attempts, now, datasetVersion);
assert.ok(skipState.reason_codes.includes('unanswered'));
const skipQueue = ReviewQueue.buildReviewQueue(
  [skippedQuestion], ReviewQueue.getLedger(storage), settings, now, datasetVersion,
);
assert.equal(skipQueue.items[0].reason_code, 'unanswered');

// A never-seen question in an already-covered subject is exploration, not a gap.
// Coverage is keyed on hash-compatible attempts: pass the bank rows too, as the
// production caller does, so the subject's attempted questions can prove coverage.
const newInCovered = question('A', '科目 A', 99);
const exploreQueue = ReviewQueue.buildReviewQueue(
  [...a, newInCovered], ReviewQueue.getLedger(storage), settings, now, datasetVersion,
);
const exploreItem = exploreQueue.items.find((item) => item.question.no === '99');
assert.equal(exploreItem.reason_code, 'unseen');
assert.equal(exploreItem.priority, 4);
const firstQueue = ReviewQueue.buildReviewQueue(
  [...a, ...b, ...c, ...d], ReviewQueue.getLedger(storage), settings, now, datasetVersion,
);
assert.equal(firstQueue.items.length, 5);
assert.ok(firstQueue.items.some((item) => item.reason_code === 'marked_review'));
assert.ok(firstQueue.items.some((item) => item.reason_code === 'due'));
assert.ok(firstQueue.items.some((item) => item.reason_code === 'coverage_gap'));
assert.ok(firstQueue.items.filter((item) => item.question.cat === 'A').length <= 3, 'one weak subject must not starve coverage');
// The deadline clamp is the local end of the target day, not a fixed UTC bound.
const targetDayEnd = new Date(2026, 9, 14, 23, 59, 59, 999).toISOString();
assert.ok(firstQueue.items.every((item) => item.scheduled_due_at <= targetDayEnd));
assert.deepEqual(
  firstQueue.items.map((item) => [item.question.cat, item.question.no, item.reason_code]),
  ReviewQueue.buildReviewQueue([...a, ...b, ...c, ...d], ReviewQueue.getLedger(storage), settings, now, datasetVersion)
    .items.map((item) => [item.question.cat, item.question.no, item.reason_code]),
);

const overloaded = ReviewQueue.buildReviewQueue(
  [...a, ...b, ...c, ...d], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ deadline_enabled: true, target_date: '2026-10-01', daily_question_limit: 2 }),
  now, datasetVersion,
);
assert.equal(overloaded.overload.is_overloaded, true);
assert.ok(overloaded.overload.backlog > 0);

const deadlineQuestion = question('deadline', '截止日測試', 1);
ReviewQueue.recordQuizAttempt([deadlineQuestion], ['B'], [false], { attemptedAt: now, datasetVersion }, storage);
const deadlineQueue = ReviewQueue.buildReviewQueue(
  [deadlineQuestion], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ deadline_enabled: true, target_date: '2026-09-30', daily_question_limit: 5 }),
  now, datasetVersion,
);
assert.equal(deadlineQueue.items[0].scheduled_due_at, new Date(2026, 8, 30, 23, 59, 59, 999).toISOString());

const changed = { ...a[0], stem: 'changed source text' };
const changedState = ReviewQueue.deriveReviewState(
  changed, ReviewQueue.getLedger(storage).attempts, now, datasetVersion,
);
assert.equal(changedState.status, 'STALE');
assert.ok(changedState.reason_codes.includes('dataset_changed'));
const changedQueue = ReviewQueue.buildReviewQueue([changed], ReviewQueue.getLedger(storage), settings, now, datasetVersion);
assert.equal(changedQueue.items[0].reason_code, 'dataset_changed');
assert.equal(changedQueue.items[0].state.wrong_count, 0, 'stale attempts must not be silently reused');

// Stale items outrank everything else, even at the smallest capacity.
const staleFirst = ReviewQueue.buildReviewQueue(
  [changed, a[1]], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ daily_question_limit: 1 }),
  now, datasetVersion,
);
assert.equal(staleFirst.items.length, 1);
assert.equal(staleFirst.items[0].reason_code, 'dataset_changed');

// Re-attempting the changed content must clear STALE instead of pinning it.
ReviewQueue.recordQuizAttempt([changed], ['A'], [false], { attemptedAt: '2026-09-30T13:00:00.000Z', datasetVersion: 'search-index-fixture-v2' }, storage);
const recovered = ReviewQueue.deriveReviewState(
  changed, ReviewQueue.getLedger(storage).attempts, now, 'search-index-fixture-v2',
);
assert.equal(recovered.status, 'CURRENT');
assert.equal(recovered.attempts, 1);
assert.equal(recovered.correct_streak, 1);

// A dataset rebuild that leaves content untouched must re-map existing attempts.
const remapped = ReviewQueue.deriveReviewState(
  a[1], ReviewQueue.getLedger(storage).attempts, now, 'search-index-fixture-v9',
);
assert.equal(remapped.status, 'CURRENT');
assert.equal(remapped.wrong_count, 1);

// Deadline mode without a target date must not fabricate a backlog.
const noDeadlineDate = ReviewQueue.buildReviewQueue(
  [...a, ...b, ...c, ...d], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ deadline_enabled: true, target_date: null, daily_question_limit: 2 }),
  now, datasetVersion,
);
assert.equal(noDeadlineDate.overload.is_overloaded, false);
assert.equal(noDeadlineDate.overload.backlog, 0);

// A target date already in the past reports the full weak set as backlog.
const pastDeadline = ReviewQueue.buildReviewQueue(
  [...a, ...b, ...c, ...d], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ deadline_enabled: true, target_date: '2026-09-01', daily_question_limit: 2 }),
  now, datasetVersion,
);
assert.equal(pastDeadline.overload.is_overloaded, true);
assert.equal(pastDeadline.overload.available_capacity, 0);
assert.equal(pastDeadline.overload.backlog, pastDeadline.overload.required);

// Import must drop malformed attempt rows instead of corrupting derived state.
const validLocator = { category: 'c', year: '115', subject: 's', number: '1', index: null };
const malformedStorage = makeStorage();
ReviewQueue.importData({
  schema_version: 1,
  ledger: { schema_version: 1, attempts: [
    { question_id: '', outcome: 'correct', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000', source_locator: validLocator },
    { question_id: 'q1', outcome: 'guessed', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000', source_locator: validLocator },
    { question_id: 'q2', outcome: 'wrong', attempted_at: 'not-a-date', source_hash: 'fnv1a-00000000', source_locator: validLocator },
    { question_id: 'q5', outcome: 'wrong', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000' },
    { question_id: 'q3', outcome: 'wrong', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000', source_locator: validLocator },
    { question_id: 'q4', outcome: 'correct', attempted_at: '2026-03-03', source_hash: 'fnv1a-00000000', source_locator: validLocator },
  ] },
}, malformedStorage);
assert.equal(ReviewQueue.getLedger(malformedStorage).attempts.length, 2);
assert.equal(ReviewQueue.getLedger(malformedStorage).attempts[0].question_id, 'q3');
// Non-ISO timestamps are normalized so lexicographic ordering stays valid.
assert.equal(ReviewQueue.getLedger(malformedStorage).attempts[1].attempted_at, '2026-03-03T00:00:00.000Z');

// Persistence failure must be reported to the caller, not swallowed.
const failingStorage = {
  getItem() { return null; },
  setItem() { throw new Error('quota exceeded'); },
  removeItem() {},
};
const failedRecord = ReviewQueue.recordQuizAttempt(
  [a[0]], ['A'], [false], { attemptedAt: now, datasetVersion }, failingStorage,
);
assert.equal(failedRecord.persisted, false);
assert.equal(ReviewQueue.saveQuizSummary({ date: now, correct: 1, total: 1, pct: 100, elapsed: 5 }, failingStorage), false);
assert.equal(ReviewQueue.saveQuizSummary({ date: now, correct: 1, total: 1, pct: 100, elapsed: 5 }, makeStorage()), true);

// The exploration reserve binds the weak-item quota too: at capacity 2 the
// queue still keeps a coverage slot instead of being all wrong items.
const tinyCap = ReviewQueue.buildReviewQueue(
  [...a, c[0]], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ daily_question_limit: 2 }), now, datasetVersion,
);
assert.equal(tinyCap.items.length, 2);
assert.ok(tinyCap.items.some((item) => item.reason_code === 'coverage_gap'));

// At capacity 1 the single slot goes to the highest-priority item.
const oneSlot = ReviewQueue.buildReviewQueue(
  [a[1], c[0]], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ daily_question_limit: 1 }), now, datasetVersion,
);
assert.equal(oneSlot.items.length, 1);
assert.equal(oneSlot.items[0].reason_code, 'last_wrong');

// An unparseable target date is discarded instead of fabricating a deadline.
const badDate = ReviewQueue.buildReviewQueue(
  [...a, ...b], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ deadline_enabled: true, target_date: 'not-a-date', daily_question_limit: 2 }),
  now, datasetVersion,
);
assert.equal(badDate.settings.target_date, null);
assert.equal(badDate.overload.is_overloaded, false);

// A minute budget under one question honestly yields an empty queue.
const zeroCap = ReviewQueue.buildReviewQueue(
  [...a, ...b], ReviewQueue.getLedger(storage),
  ReviewQueue.normalizeSettings({ deadline_enabled: true, target_date: '2026-10-14', daily_minutes: 1 }),
  now, datasetVersion,
);
assert.equal(zeroCap.items.length, 0);
assert.ok(zeroCap.overload.is_overloaded);

// A corrupt or foreign ledger blob is quarantined, not silently destroyed.
const corruptStorage = makeStorage();
corruptStorage.setItem('exam-attempt-ledger-v1', '{"schema_version":999,"attempts":[]}');
assert.equal(ReviewQueue.getLedger(corruptStorage).attempts.length, 0);
assert.equal(corruptStorage.getItem('exam-attempt-ledger-v1.corrupt'), '{"schema_version":999,"attempts":[]}');
ReviewQueue.clearLearnerData(corruptStorage);
assert.equal(corruptStorage.getItem('exam-attempt-ledger-v1.corrupt'), null);

// A locator collision (same 類科|年份|科目|題號, different row index/content)
// must not mark the never-attempted sibling STALE.
const collidedA = { ...question('dup', '碰撞科目', 1, 'first copy'), idx: 100 };
const collidedB = { ...question('dup', '碰撞科目', 1, 'second copy'), idx: 101 };
assert.equal(
  ReviewQueue.questionIdentity(collidedA).question_id,
  ReviewQueue.questionIdentity(collidedB).question_id,
);
ReviewQueue.recordQuizAttempt([collidedA], ['B'], [false], { attemptedAt: now, datasetVersion }, storage);
const siblingState = ReviewQueue.deriveReviewState(collidedB, ReviewQueue.getLedger(storage).attempts, now, datasetVersion);
assert.equal(siblingState.status, 'CURRENT');
assert.ok(!siblingState.reason_codes.includes('dataset_changed'));
const siblingQueue = ReviewQueue.buildReviewQueue(
  [collidedA, collidedB], ReviewQueue.getLedger(storage), settings, now, datasetVersion,
);
assert.equal(siblingQueue.items.find((item) => item.question_id === siblingState.question_id && item.question.idx === 101).reason_code, 'coverage_gap');

// The same locator at the same index with changed content stays STALE.
const indexedChanged = { ...question('idx', '索引科目', 1, 'old text'), idx: 200 };
ReviewQueue.recordQuizAttempt([indexedChanged], ['B'], [false], { attemptedAt: now, datasetVersion }, storage);
const indexedStale = ReviewQueue.deriveReviewState(
  { ...indexedChanged, stem: 'new text' }, ReviewQueue.getLedger(storage).attempts, now, datasetVersion,
);
assert.equal(indexedStale.status, 'STALE');
assert.ok(indexedStale.reason_codes.includes('dataset_changed'));

// Attempt history is bounded per question so the ledger cannot outgrow the quota.
const cappedStorage = makeStorage();
const cappedQuestion = question('cap', '容量測試', 1);
for (let i = 0; i < 32; i++) {
  ReviewQueue.recordQuizAttempt(
    [cappedQuestion], ['B'], [false],
    { attemptedAt: new Date(Date.UTC(2026, 0, 1 + i)).toISOString(), datasetVersion },
    cappedStorage,
  );
}
const cappedAttempts = ReviewQueue.getLedger(cappedStorage).attempts;
assert.equal(cappedAttempts.length, 30);
// The two oldest events were trimmed; the rest keep append order.
assert.equal(cappedAttempts[0].attempted_at, new Date(Date.UTC(2026, 0, 3)).toISOString());
assert.equal(cappedAttempts[29].attempted_at, new Date(Date.UTC(2026, 0, 32)).toISOString());

const importedStorage = makeStorage();
ReviewQueue.saveSettings(settings, storage);
const exportedWithSettings = ReviewQueue.exportData(storage, datasetVersion);
ReviewQueue.importData(exportedWithSettings, importedStorage);
assert.deepEqual(ReviewQueue.getLedger(importedStorage), ReviewQueue.getLedger(storage));
assert.deepEqual(ReviewQueue.getSettings(importedStorage), ReviewQueue.getSettings(storage));

storage.setItem('exam-bookmarks', '{"keep":true}');
ReviewQueue.clearLearnerData(storage);
assert.equal(storage.getItem('exam-bookmarks'), '{"keep":true}');
assert.equal(ReviewQueue.getLedger(storage).attempts.length, 0);

// The standalone engine module's aggregate path must stay aggregate-only:
// quiz.html's finish() owns the per-question ledger write, and a second
// writer would double-record every quiz once the module is loaded by a page.
const engineSource = fs.readFileSync(
  path.join(__dirname, '..', '考古題網站', 'js', 'quiz-engine.js'), 'utf8');
const engineWindow = {};
const engineStorage = makeStorage();
vm.runInNewContext(engineSource, { window: engineWindow, localStorage: engineStorage });
engineWindow.QuizEngine.saveHistory({ correct: 1, total: 2, pct: 50, elapsed: 10 });
engineWindow.QuizEngine.saveHistory({ correct: 2, total: 2, pct: 100, elapsed: 8 });
assert.equal(JSON.parse(engineStorage.getItem('exam-quiz-history')).length, 1,
  'saveHistory must stay idempotent');
assert.equal(engineStorage.getItem('exam-attempt-ledger-v1'), null,
  'the aggregate engine path must not write the attempt ledger');

// A calendar-impossible target date must be discarded, not turn the whole
// weak set into phantom backlog while escaping the deadline clamp.
const badCalendar = ReviewQueue.normalizeSettings({
  deadline_enabled: true, target_date: '2026-02-31', daily_question_limit: 5,
});
assert.equal(badCalendar.target_date, null);
const phantomBacklog = ReviewQueue.buildReviewQueue(
  [...a, ...b], ReviewQueue.getLedger(storage), badCalendar, now, datasetVersion,
);
assert.equal(phantomBacklog.overload.is_overloaded, false);

// A subject whose entire history went stale is still a coverage gap:
// unseen questions there outrank routine exploration in a covered subject.
const driftStorage = makeStorage();
const driftOld = question('drift', '漂移科目', 1, 'old stem');
const driftNew = { ...driftOld, stem: 'new stem' };
const driftUnseen = question('drift', '漂移科目', 2, 'never seen');
ReviewQueue.recordQuizAttempt(
  [driftOld], ['B'], [false], { attemptedAt: now, datasetVersion }, driftStorage);
const driftQueue = ReviewQueue.buildReviewQueue(
  [driftNew, driftUnseen], ReviewQueue.getLedger(driftStorage),
  ReviewQueue.normalizeSettings({ daily_question_limit: 10 }), now, datasetVersion,
);
assert.equal(driftQueue.items.find((item) => item.question.no === '1').reason_code, 'dataset_changed');
assert.equal(driftQueue.items.find((item) => item.question.no === '2').reason_code, 'coverage_gap',
  'stale-only history must not shield a subject from the coverage tier');

// A question without a gradeable answer key cannot be scored wrong;
// the chosen answer is still recorded for the audit trail.
const noKeyStorage = makeStorage();
const noKey = { ...question('key', '無答案科目', 1), ans: 'E' };
ReviewQueue.recordQuizAttempt(
  [noKey], ['B'], [false], { attemptedAt: now, datasetVersion }, noKeyStorage);
const noKeyAttempt = ReviewQueue.getLedger(noKeyStorage).attempts[0];
assert.equal(noKeyAttempt.outcome, 'unanswered');
assert.equal(noKeyAttempt.chosen_answer, 'B');

// The corrupt-ledger quarantine blob is written once, not on every read.
const quarantine = {
  blob: '{"schema_version":999}',
  corrupt: null,
  writes: 0,
  getItem(key) {
    if (key === 'exam-attempt-ledger-v1') return this.blob;
    if (key === 'exam-attempt-ledger-v1.corrupt') return this.corrupt;
    return null;
  },
  setItem(key, value) {
    if (key === 'exam-attempt-ledger-v1.corrupt') { this.writes += 1; this.corrupt = value; }
  },
  removeItem() {},
};
ReviewQueue.getLedger(quarantine);
ReviewQueue.getLedger(quarantine);
assert.equal(quarantine.writes, 1);

// Import must reject a foreign ledger schema and locator rows that cannot
// re-map to a stable question identity.
assert.throws(() => ReviewQueue.importData({
  schema_version: 1,
  ledger: { schema_version: 999, attempts: [] },
}, makeStorage()));
const weakLocator = makeStorage();
ReviewQueue.importData({
  schema_version: 1,
  ledger: { schema_version: 1, attempts: [
    { question_id: 'q7', outcome: 'wrong', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000', source_locator: { subject: 's' } },
    { question_id: 'q8', outcome: 'wrong', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000', source_locator: validLocator },
  ] },
}, weakLocator);
assert.deepEqual(
  ReviewQueue.getLedger(weakLocator).attempts.map((item) => item.question_id), ['q8'],
);

console.log('review queue contract: ok');
