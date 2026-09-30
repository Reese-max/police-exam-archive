const { test, expect } = require('@playwright/test');

test.describe('逐題作答帳本與今日複習', () => {
  test('交卷後保存逐題結果，重整仍可建立帶理由的複習題列', async ({ page }) => {
    await page.goto('/quiz.html');
    await page.evaluate(() => {
      localStorage.removeItem('exam-attempt-ledger-v1');
      localStorage.removeItem('exam-review-settings-v1');
      localStorage.removeItem('exam-quiz-history');
    });
    await page.reload();
    await page.waitForFunction(() => /題/.test(document.querySelector('#matchCount')?.textContent || ''));

    await expect(page.locator('#startBtn')).toBeEnabled();
    await page.locator('#startBtn').click();
    await expect(page.locator('#examView')).toBeVisible();

    await page.locator('.choice').first().click();
    await page.locator('#flagBtn').click();
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#submitBtn').click();
    await expect(page.locator('#resultView')).toBeVisible();

    const ledger = await page.evaluate(() => JSON.parse(localStorage.getItem('exam-attempt-ledger-v1')));
    expect(ledger.attempts).toHaveLength(20);
    expect(ledger.attempts.every(item => item.question_id && item.dataset_version && item.outcome)).toBe(true);
    expect(ledger.attempts.some(item => item.outcome === 'unanswered')).toBe(true);
    expect(ledger.attempts.some(item => item.marked_review)).toBe(true);

    await page.reload();
    await page.waitForFunction(() => /今天可做/.test(document.querySelector('#reviewStatus')?.textContent || ''));
    await expect(page.locator('#startReviewBtn')).toBeEnabled();
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#exportLearningBtn').click();
    expect((await downloadPromise).suggestedFilename()).toBe('police-exam-learning-data.json');

    await page.locator('#startReviewBtn').click();
    await expect(page.locator('#examView')).toBeVisible();
    await expect(page.locator('#qReason')).toBeVisible();
    await expect(page.locator('#qReason')).not.toHaveText('');
  });
});
