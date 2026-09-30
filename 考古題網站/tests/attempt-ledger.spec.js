const { test, expect } = require('@playwright/test');

async function routeLedgerFixture(page, version = 'v1') {
  const questions = [
    { cat: 'A', yr: 113, sub: 'Law', no: '1', type: 'choice', stem: version === 'v1' ? 'Q1' : 'Revised Q1', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' },
    { cat: 'B', yr: 114, sub: 'Other', no: '2', type: 'choice', stem: 'Q2', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' },
  ];
  await page.unroute('**/data/search-index.json');
  await page.route('**/data/search-index.json', route => route.fulfill({ json: {
    v: 1, datasetVersion: version, stats: { total: 2 },
    facets: { categories: ['A', 'B'], years: [113, 114], subjects: ['Law', 'Other'] },
    columns: Object.fromEntries(Object.keys(questions[0]).map(key => [key, questions.map(q => q[key])])),
  } }));
}

test.describe('PR80 UI regression', () => {
  test.use({ serviceWorkers: 'block', viewport: { width: 390, height: 844 } });
  test.beforeEach(async ({ page }) => {
    // These flows use SearchEngine's column filter, not CDN text search.
    await page.route('**/minisearch@*/**', route => route.fulfill({
      contentType: 'application/javascript', body: 'window.MiniSearch = class { addAll() {} };',
    }));
    await routeLedgerFixture(page);
    await page.goto('/quiz.html');
    await expect(page.locator('#queueCount')).toHaveText('2 題');
  });

  test('empty filters clear the old review queue', async ({ page }) => {
    await page.locator('#fCat').selectOption('B');
    await page.locator('#fYear').selectOption('113');
    await expect(page.locator('#matchCount')).toHaveText('0 題');
    await expect(page.locator('#queueCount')).toHaveText('0 題');
    await expect(page.locator('#reviewQueueList li')).toHaveCount(0);
    await expect(page.locator('#reviewStartBtn')).toBeDisabled();
  });

  test('failed persistence keeps answers available for resubmission', async ({ page }) => {
    await page.locator('#reviewStartBtn').click();
    await page.locator('.choice[data-i="0"]').click();
    await page.locator('#nextBtn').click();
    await page.locator('.choice[data-i="0"]').click();
    await page.evaluate(() => {
      window.originalSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === 'exam-question-attempt-ledger') throw new DOMException('Full', 'QuotaExceededError');
        window.originalSetItem.call(this, key, value);
      };
    });
    const messages = [];
    page.on('dialog', async dialog => { messages.push(dialog.message()); await dialog.accept(); });
    await page.locator('#submitBtn').click();
    await expect(page.locator('#examView')).toBeVisible();
    expect(messages.join(' ')).toContain('未儲存');
    await page.evaluate(() => { Storage.prototype.setItem = window.originalSetItem; });
    await page.locator('#submitBtn').click();
    await expect(page.locator('#sOk')).toHaveText('2');
    expect(await page.evaluate(() => AttemptLedger.getLedger().length)).toBe(2);
  });

  test('mobile submission reload versions and JSON roundtrip', async ({ page }) => {
    page.on('dialog', dialog => dialog.accept());
    await page.locator('#reviewStartBtn').click();
    await page.locator('.choice[data-i="0"]').click();
    await page.locator('#flagBtn').click();
    await page.locator('#nextBtn').click();
    await page.locator('#submitBtn').click();
    await expect(page.locator('#sOk')).toHaveText('1');
    await expect(page.locator('#sSkip')).toHaveText('1');
    await page.reload();
    const before = await page.evaluate(() => AttemptLedger.getLedger());
    expect(before).toHaveLength(2);
    expect(before[0]).toMatchObject({ answerOutcome: 'correct', markedReview: true, quizMode: 'review', datasetVersion: 'v1' });
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#exportLearningBtn').click();
    const download = await downloadPromise;
    const payload = await require('fs/promises').readFile(await download.path());
    await page.locator('#clearLearningBtn').click();
    await page.locator('#importLearningFile').setInputFiles({ name: 'learning.json', mimeType: 'application/json', buffer: payload });
    await expect.poll(() => page.evaluate(() => AttemptLedger.getLedger())).toEqual(before);
    await routeLedgerFixture(page, 'v2');
    await page.reload();
    await expect(page.locator('#queueCount')).toHaveText('2 題');
    const states = await page.evaluate(() => SearchEngine.search('', {}, 10).map(q => AttemptLedger.getReviewState(q)));
    expect(states[0].sourceCompat).toBe('stale');
    expect(states[1].sourceCompat).toBe('current');
    await page.locator('#deadlineEnabled').check();
    const today = await page.evaluate(() => new Date().toLocaleDateString('en-CA'));
    await page.locator('#targetExamDate').fill(today);
    await page.locator('#dailyQuestionLimit').fill('1');
    await page.locator('#dailyQuestionLimit').blur();
    await expect(page.locator('#queueStatus')).toContainText('backlog');
  });
});

test.describe('逐題作答 ledger 與考前複習佇列', () => {
  test('可保存逐題事實並以截止日 deterministic 產生帶原因的複習佇列', async ({ page }) => {
    await page.goto('/quiz.html');

    const result = await page.evaluate(() => {
      const questions = [
        { cat: 'A', yr: 113, sub: '法規', no: 1, stem: 'A1', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' },
        { cat: 'A', yr: 113, sub: '法規', no: 2, stem: 'A2', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'B' },
        { cat: 'B', yr: 112, sub: '英文', no: 1, stem: 'B1', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'C' },
      ];
      const now = Date.parse('2026-09-30T00:00:00.000Z');
      const events = [
        { question: questions[0], attemptedAt: '2026-09-29T00:00:00.000Z', answerOutcome: 'wrong', chosenAnswer: 'D', markedReview: true },
        { question: questions[1], attemptedAt: '2026-09-01T00:00:00.000Z', answerOutcome: 'correct', chosenAnswer: 'B' },
      ];
      AttemptLedger.replace(events.map(event => AttemptLedger.createEvent(event)));
      AttemptLedger.saveSettings({ enabled: true, targetExamDate: '2026-10-02', dailyQuestionLimit: 1 });
      const queue = AttemptLedger.buildQueue(questions, { now, limit: 5 });
      return {
        ledger: AttemptLedger.getLedger(),
        queue: queue.items,
        backlog: queue.overload,
        exported: AttemptLedger.exportData(),
      };
    });

    expect(result.ledger).toHaveLength(2);
    expect(result.ledger[0]).toMatchObject({
      questionId: 'A|113|法規|1',
      answerOutcome: 'wrong',
      markedReview: true,
      datasetVersion: expect.any(String),
      questionHash: expect.any(String),
    });
    expect(result.queue[0]).toMatchObject({
      questionId: 'A|113|法規|1',
      reasonCodes: expect.arrayContaining(['上次答錯', '標記回顧']),
    });
    expect(result.exported).toContain('attemptLedger');
    expect(result.backlog).toBe(false);
  });

  test('hash 變更會 fail closed，deadline 會限制 due date 並回報 backlog', async ({ page }) => {
    await page.goto('/quiz.html');

    const result = await page.evaluate(() => {
      const questions = Array.from({ length: 6 }, (_, index) => ({
        cat: 'A', yr: 113, sub: '法規', no: index + 1,
        stem: '原始題目 ' + index, optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A',
      }));
      const now = Date.parse('2026-09-30T00:00:00.000Z');
      AttemptLedger.replace(questions.map(question => AttemptLedger.createEvent({
        question,
        attemptedAt: '2026-09-29T00:00:00.000Z',
        answerOutcome: 'wrong',
        chosenAnswer: 'B',
      })));
      AttemptLedger.saveSettings({ enabled: true, targetExamDate: '2026-10-01', dailyQuestionLimit: 2 });
      const changed = { ...questions[0], stem: '修正版題目 0' };
      const queue = AttemptLedger.buildQueue([changed, ...questions.slice(1)], { now, limit: 6 });
      const state = queue.states[0];
      return {
        state,
        queue: queue.items,
        exportText: AttemptLedger.exportData(),
      };
    });

    expect(result.state.sourceCompat).toBe('stale');
    expect(result.state.attempts).toBe(1);
    expect(result.state.compatibleAttempts).toBe(0);
    expect(result.state.reasonCodes).toContain('資料集版本不相容');
    expect(result.queue.every(item => item.dueAt === null || item.dueAt <= '2026-10-01T23:59:59.999Z')).toBeTruthy();
    expect(result.queue.some(item => item.sourceCompat === 'stale')).toBeTruthy();
    expect(result.exportText).toContain('reviewSettings');
  });

  test('import/export 與清除只作用於 learner state', async ({ page }) => {
    await page.goto('/quiz.html');

    const result = await page.evaluate(() => {
      localStorage.setItem('exam-bookmarks', JSON.stringify({ keep: true }));
      localStorage.setItem('exam-quiz-history', JSON.stringify([{ total: 1 }]));
      const question = { cat: 'C', yr: 111, sub: '英文', no: 7, stem: 'Q', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'C' };
      AttemptLedger.replace([AttemptLedger.createEvent({ question, answerOutcome: 'unanswered', markedReview: true })]);
      AttemptLedger.saveSettings({ enabled: true, targetExamDate: '2026-12-31', dailyQuestionLimit: 5 });
      const payload = AttemptLedger.exportData();
      AttemptLedger.clearLearnerData();
      const cleared = { ledger: AttemptLedger.getLedger(), settings: AttemptLedger.getSettings(), bookmark: localStorage.getItem('exam-bookmarks'), history: localStorage.getItem('exam-quiz-history') };
      AttemptLedger.importData(payload);
      return { cleared, restored: AttemptLedger.getLedger(), settings: AttemptLedger.getSettings() };
    });

    expect(result.cleared.ledger).toEqual([]);
    expect(result.cleared.settings.deadlineEnabled).toBe(false);
    expect(result.cleared.bookmark).toBe('{"keep":true}');
    expect(result.cleared.history).toBeNull();
    expect(result.restored).toHaveLength(1);
    expect(result.restored[0]).toMatchObject({ answerOutcome: 'unanswered', markedReview: true });
    expect(result.settings.dailyQuestionLimit).toBe(5);
  });

  test('derived state tracks correct streak and consecutive wrong reason deterministically', async ({ page }) => {
    await page.goto('/quiz.html');

    const result = await page.evaluate(() => {
      const correctQuestion = { cat: 'D', yr: 110, sub: '行政法', no: 1, stem: 'correct', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' };
      const wrongQuestion = { cat: 'D', yr: 110, sub: '行政法', no: 2, stem: 'wrong', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' };
      AttemptLedger.replace([
        AttemptLedger.createEvent({ question: correctQuestion, attemptedAt: '2026-09-20T00:00:00.000Z', answerOutcome: 'correct', chosenAnswer: 'A' }),
        AttemptLedger.createEvent({ question: correctQuestion, attemptedAt: '2026-09-21T00:00:00.000Z', answerOutcome: 'correct', chosenAnswer: 'A' }),
        AttemptLedger.createEvent({ question: wrongQuestion, attemptedAt: '2026-09-20T00:00:00.000Z', answerOutcome: 'wrong', chosenAnswer: 'B' }),
        AttemptLedger.createEvent({ question: wrongQuestion, attemptedAt: '2026-09-21T00:00:00.000Z', answerOutcome: 'wrong', chosenAnswer: 'B' }),
      ]);
      return {
        correct: AttemptLedger.getReviewState(correctQuestion, { now: '2026-09-30T00:00:00.000Z' }),
        wrong: AttemptLedger.getReviewState(wrongQuestion, { now: '2026-09-30T00:00:00.000Z' }),
      };
    });

    expect(result.correct).toMatchObject({ attempts: 2, correctStreak: 2, wrongCount: 0 });
    expect(result.wrong).toMatchObject({ attempts: 2, consecutiveWrongCount: 2, wrongCount: 2 });
    expect(result.wrong.reasonCodes).toContain('連續 2 次答錯');
  });
});
