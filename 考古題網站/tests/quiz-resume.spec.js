// @ts-check
const { test, expect } = require('@playwright/test');

const SESSION_KEY = 'exam-quiz-active';
const FIXTURE_INDEX = {
  columns: {
    cat: Array(10).fill('行政警察學系'),
    yr: Array(10).fill(114),
    sub: Array(10).fill('警察法規'),
    no: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    type: Array(10).fill('choice'),
    stem: Array.from({ length: 10 }, (_, i) => `固定題目第${i + 1}題`),
    optA: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項A`),
    optB: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項B`),
    optC: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項C`),
    optD: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項D`),
    ans: ['A', 'B', 'C', 'D', 'A', 'B', 'C', 'D', 'A', 'B'],
  },
  facets: { categories: ['行政警察學系'], years: [114], subjects: ['警察法規'] },
  stats: { total: 10, choice: 10, essay: 0, categories: 1, subjects: 1 },
};

test.use({ serviceWorkers: 'block' });

async function gotoQuizWithFixture(page) {
  await page.route('**/data/search-index.json', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(FIXTURE_INDEX),
  }));
  await page.goto('/quiz.html');
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('#startBtn')).toBeEnabled();
}

async function startFixtureExam(page) {
  await page.locator('#segCount button[data-v="10"]').click();
  await page.locator('#segTime button[data-v="60"]').click();
  await page.locator('#startBtn').click();
  await expect(page.locator('#examView')).toBeVisible();
}

function readCheckpoint(page) {
  return page.evaluate(key => {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, SESSION_KEY);
}

test.describe('模擬考試中斷恢復', () => {
  test('可恢復答題進度並在交卷後清除 checkpoint', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);

    for (let i = 0; i < 3; i++) {
      await page.locator('#choices .choice').first().click();
      if (i < 2) await page.locator('#nextBtn').click();
    }
    await page.locator('#nextBtn').click();
    await page.locator('#flagBtn').click();
    await page.locator('#nextBtn').click();
    await expect(page.locator('#qNum')).toHaveText('第 5 題');

    const stemsBefore = await page.evaluate(() => questions.map(q => q.stem));
    const checkpoint = await readCheckpoint(page);
    expect(checkpoint).toMatchObject({ cur: 4, durSec: 3600, timed: true });
    expect(checkpoint.answers.filter(answer => answer !== null)).toHaveLength(3);
    expect(checkpoint.flags[3]).toBe(true);

    await page.reload();
    await expect(page.locator('#resumeCard')).toBeVisible();
    await expect(page.locator('#setupView')).toBeVisible();
    await page.locator('#resumeBtn').click();

    await expect(page.locator('#examView')).toBeVisible();
    await expect(page.locator('#qNum')).toHaveText('第 5 題');
    expect(await page.evaluate(() => questions.map(q => q.stem))).toEqual(stemsBefore);
    await expect(page.locator('#miniGrid .mini.done')).toHaveCount(3);
    await expect(page.locator('#miniGrid .mini.flag')).toHaveCount(1);
    await page.locator('#miniGrid .mini').nth(3).click();
    await expect(page.locator('#flagBtn')).toHaveClass(/on/);
    const [minutes, seconds] = (await page.locator('#timerText').textContent()).split(':').map(Number);
    expect(minutes * 60 + seconds).toBeGreaterThan(0);
    expect(minutes * 60 + seconds).toBeLessThanOrEqual(3600);

    page.on('dialog', dialog => dialog.accept());
    await page.locator('#submitBtn').click();
    await expect(page.locator('#resultView')).toBeVisible();
    expect(await readCheckpoint(page)).toBeNull();

    await page.reload();
    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
  });

  test('窄螢幕重新整理後也可恢復目前題目', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    await page.locator('#choices .choice').first().click();
    await page.locator('#nextBtn').click();
    await expect(page.locator('#qNum')).toHaveText('第 2 題');

    await page.reload();
    await expect(page.locator('#resumeCard')).toBeVisible();
    await page.locator('#resumeBtn').click();
    await expect(page.locator('#examView')).toBeVisible();
    await expect(page.locator('#qNum')).toHaveText('第 2 題');
    await expect(page.locator('#miniGrid .mini.done')).toHaveCount(1);
  });

  test('已完成的分頁不會被舊分頁的 pagehide checkpoint 復活', async ({ page, context }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    const secondPage = await context.newPage();
    await gotoQuizWithFixture(secondPage);
    await secondPage.locator('#resumeBtn').click();
    secondPage.on('dialog', dialog => dialog.accept());
    await secondPage.locator('#submitBtn').click();
    await expect(secondPage.locator('#resultView')).toBeVisible();
    expect(await readCheckpoint(secondPage)).toBeNull();

    await page.close();
    const reopened = await context.newPage();
    await gotoQuizWithFixture(reopened);
    await expect(reopened.locator('#resumeCard')).toBeHidden();
    await expect(reopened.locator('#setupView')).toBeVisible();
    await secondPage.close();
    await reopened.close();
  });

  test('可捨棄已保存的考試並開始新考試', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    await page.locator('#choices .choice').first().click();
    await page.reload();
    await expect(page.locator('#resumeCard')).toBeVisible();
    await page.locator('#discardBtn').click();
    expect(await readCheckpoint(page)).toBeNull();
    await expect(page.locator('#resumeCard')).toBeHidden();
    await startFixtureExam(page);
    await expect(page.locator('#qNum')).toHaveText('第 1 題');
  });

  test('損毀 checkpoint 安全退回設定畫面並清除', async ({ page }) => {
    await page.addInitScript(key => localStorage.setItem(key, '{broken json'), SESSION_KEY);
    await gotoQuizWithFixture(page);
    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    expect(await page.evaluate(key => localStorage.getItem(key), SESSION_KEY)).toBeNull();
  });

  test('過期 checkpoint 安全退回設定畫面並清除', async ({ page }) => {
    await page.addInitScript(key => {
      const question = { subj: 'subject', stem: 'stem', opts: ['a', 'b', 'c', 'd'], ans: 0 };
      localStorage.setItem(key, JSON.stringify({
        v: 1,
        savedAt: Date.now() - 25 * 60 * 60 * 1000,
        timed: true,
        questions: [question],
        answers: [null],
        flags: [false],
        cur: 0,
        durSec: 3600,
        remain: 3600,
        elapsed: 0,
      }));
    }, SESSION_KEY);
    await gotoQuizWithFixture(page);
    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    expect(await page.evaluate(key => localStorage.getItem(key), SESSION_KEY)).toBeNull();
  });
});
