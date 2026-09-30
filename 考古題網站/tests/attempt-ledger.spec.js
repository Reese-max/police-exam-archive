const { test, expect } = require('@playwright/test');

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
