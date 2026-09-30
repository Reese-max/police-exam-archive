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

const settings = ReviewQueue.normalizeSettings({
  deadline_enabled: true,
  target_date: '2026-10-14',
  daily_question_limit: 5,
  daily_minutes: 40,
});
const firstQueue = ReviewQueue.buildReviewQueue(
  [...a, ...b, ...c, ...d], ReviewQueue.getLedger(storage), settings, now, datasetVersion,
);
assert.equal(firstQueue.items.length, 5);
assert.ok(firstQueue.items.some((item) => item.reason_code === 'marked_review'));
assert.ok(firstQueue.items.some((item) => item.reason_code === 'due'));
assert.ok(firstQueue.items.some((item) => item.reason_code === 'coverage_gap'));
assert.ok(firstQueue.items.filter((item) => item.question.cat === 'A').length <= 3, 'one weak subject must not starve coverage');
assert.ok(firstQueue.items.every((item) => item.scheduled_due_at <= '2026-10-14T23:59:59.999Z'));
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
assert.equal(deadlineQueue.items[0].scheduled_due_at, '2026-09-30T23:59:59.999Z');

const changed = { ...a[0], stem: 'changed source text' };
const changedState = ReviewQueue.deriveReviewState(
  changed, ReviewQueue.getLedger(storage).attempts, now, datasetVersion,
);
assert.equal(changedState.status, 'STALE');
assert.ok(changedState.reason_codes.includes('dataset_changed'));
const changedQueue = ReviewQueue.buildReviewQueue([changed], ReviewQueue.getLedger(storage), settings, now, datasetVersion);
assert.equal(changedQueue.items[0].reason_code, 'dataset_changed');
assert.equal(changedQueue.items[0].state.wrong_count, 0, 'stale attempts must not be silently reused');

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
const malformedStorage = makeStorage();
ReviewQueue.importData({
  schema_version: 1,
  ledger: { schema_version: 1, attempts: [
    { question_id: '', outcome: 'correct', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000' },
    { question_id: 'q1', outcome: 'guessed', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000' },
    { question_id: 'q2', outcome: 'wrong', attempted_at: 'not-a-date', source_hash: 'fnv1a-00000000' },
    { question_id: 'q3', outcome: 'wrong', attempted_at: '2026-09-01T00:00:00.000Z', source_hash: 'fnv1a-00000000' },
  ] },
}, malformedStorage);
assert.equal(ReviewQueue.getLedger(malformedStorage).attempts.length, 1);
assert.equal(ReviewQueue.getLedger(malformedStorage).attempts[0].question_id, 'q3');

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

console.log('review queue contract: ok');
