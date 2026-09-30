// @ts-check
const { test, expect } = require('@playwright/test');

/* ===== 模擬考試中斷恢復（issue #69）=====
   以固定 10 題索引 fixture 攔截 data/search-index.json，
   驗證 start → 作答/標記 → checkpoint → reload/restore → finish 全流程。 */

const SESSION_KEY = 'exam-quiz-active';

// 固定 10 題 fixture（column-oriented，與 scripts/build_search_index.py 產出格式一致）
const FIXTURE_INDEX = {
  columns: {
    cat: Array(10).fill('行政警察學系'),
    yr: Array(10).fill(114),
    sub: Array(10).fill('警察法規'),
    no: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    type: Array(10).fill('choice'),
    stem: Array.from({ length: 10 }, (_, i) => `固定題目第${i + 1}題：下列何者正確？`),
    optA: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項A`),
    optB: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項B`),
    optC: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項C`),
    optD: Array.from({ length: 10 }, (_, i) => `第${i + 1}題選項D`),
    ans: ['A', 'B', 'C', 'D', 'A', 'B', 'C', 'D', 'A', 'B'],
  },
  facets: { categories: ['行政警察學系'], years: [114], subjects: ['警察法規'] },
  stats: { total: 10, choice: 10, essay: 0, categories: 1, subjects: 1 },
};

// sw.js 註冊後會接管 fetch（network-first），其 SW 內部 fetch 不經 page.route → reload 時攔截失效，故停用
test.use({ serviceWorkers: 'block' });

/** 安裝固定索引攔截 + 進入 quiz 頁並等待索引就緒 */
async function gotoQuizWithFixture(page) {
  await page.route('**/data/search-index.json', route =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(FIXTURE_INDEX) })
  );
  await page.goto('/quiz.html');
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('#startBtn')).toBeEnabled();
}

/** 開始一場 10 題 / 60 分鐘考試 */
async function startFixtureExam(page) {
  await page.locator('#segCount button[data-v="10"]').click();
  await page.locator('#segTime button[data-v="60"]').click();
  await page.locator('#startBtn').click();
  await expect(page.locator('#examView')).toBeVisible();
}

/** 讀取 localStorage 中的 checkpoint（不存在回傳 null） */
function readCheckpoint(page) {
  return page.evaluate(key => {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, SESSION_KEY);
}

test.describe('模擬考試中斷恢復', () => {
  test('重新整理後可恢復相同題目、作答、標記、位置與計時狀態', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);

    // 第 1–3 題作答（皆選第一個選項）
    for (let i = 0; i < 3; i++) {
      await page.locator('#choices .choice').first().click();
      if (i < 2) await page.locator('#nextBtn').click();
    }
    // 到第 4 題標記，再前往第 5 題
    await page.locator('#nextBtn').click();
    await page.locator('#flagBtn').click();
    await page.locator('#nextBtn').click();
    await expect(page.locator('#qNum')).toHaveText('第 5 題');

    // 記錄中斷前的題目順序與 checkpoint
    const stemsBefore = await page.evaluate(() => questions.map(q => q.stem));
    const cp = await readCheckpoint(page);
    expect(cp).not.toBeNull();

    // 模擬中斷：重新整理
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    // 應出現恢復提示而非直接進入考試
    await expect(page.locator('#resumeCard')).toBeVisible();
    await expect(page.locator('#setupView')).toBeVisible();
    await page.locator('#resumeBtn').click();

    // 相同題目、位置、標記、作答全部恢復
    await expect(page.locator('#examView')).toBeVisible();
    await expect(page.locator('#qNum')).toHaveText('第 5 題');
    const stemsAfter = await page.evaluate(() => questions.map(q => q.stem));
    expect(stemsAfter).toEqual(stemsBefore);
    await expect(page.locator('#flagBtn')).not.toHaveClass(/on/); // 當前第 5 題未標記

    // mini 導航列：3 題已答、1 題標記、當前第 5 題
    await expect(page.locator('#miniGrid .mini.done')).toHaveCount(3);
    await expect(page.locator('#miniGrid .mini.flag')).toHaveCount(1);
    await expect(page.locator('#miniGrid .mini.cur')).toHaveText('5');

    // 跳回第 4 題確認標記狀態確實恢復
    await page.locator('#miniGrid .mini').nth(3).click();
    await expect(page.locator('#flagBtn')).toHaveClass(/on/);

    // 計時狀態恢復且有界（60 分鐘場景）
    const timerText = await page.locator('#timerText').textContent();
    const [mm, ss] = timerText.split(':').map(Number);
    const remain = mm * 60 + ss;
    expect(remain).toBeGreaterThan(0);
    expect(remain).toBeLessThanOrEqual(3600);
  });

  test('窄螢幕（手機版）重新整理後同樣可恢復', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    await page.locator('#choices .choice').first().click();
    await page.locator('#nextBtn').click();
    await expect(page.locator('#qNum')).toHaveText('第 2 題');

    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#resumeCard')).toBeVisible();
    await page.locator('#resumeBtn').click();
    await expect(page.locator('#examView')).toBeVisible();
    await expect(page.locator('#qNum')).toHaveText('第 2 題');
    await expect(page.locator('#miniGrid .mini.done')).toHaveCount(1);
  });

  test('恢復提示停留期間不會暫停限時考試倒數', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    await page.reload();
    await expect(page.locator('#resumeCard')).toBeVisible();

    // pagehide 會寫回 checkpoint，因此在恢復提示出現後才模擬時間流逝。
    await page.evaluate(key => {
      const cp = JSON.parse(localStorage.getItem(key));
      cp.remain = 30;
      cp.elapsed = cp.durSec - 30;
      cp.savedAt = Date.now() - 31_000;
      localStorage.setItem(key, JSON.stringify(cp));
    }, SESSION_KEY);
    expect(await page.evaluate(() => QuizSession.load().expired)).toBe(true);
    await page.locator('#resumeBtn').click();
    await expect(page.locator('#resultView')).toBeVisible();
    expect(await readCheckpoint(page)).toBeNull();
  });

  test('不限時模式恢復後計時從已用時間繼續（非重置為 0）', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await page.locator('#segCount button[data-v="10"]').click();
    await page.locator('#segTime button[data-v="0"]').click(); // 不限時
    await page.locator('#startBtn').click();
    await expect(page.locator('#examView')).toBeVisible();
    await page.locator('#choices .choice').first().click();

    // 讓計時走幾秒後中斷
    await page.waitForTimeout(2100);
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#resumeCard')).toBeVisible();
    await page.locator('#resumeBtn').click();
    await expect(page.locator('#examView')).toBeVisible();

    // 顯示應為已用時間（>=2s），不是 00:00
    const timerText = await page.locator('#timerText').textContent();
    const [mm, ss] = timerText.split(':').map(Number);
    expect(mm * 60 + ss).toBeGreaterThanOrEqual(2);
  });

  test('可明確捨棄已存考試並重新開始', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    await page.locator('#choices .choice').first().click();
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('#resumeCard')).toBeVisible();
    await page.locator('#discardBtn').click();

    // checkpoint 已清除、回到設定畫面、可重新開始
    expect(await readCheckpoint(page)).toBeNull();
    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    await startFixtureExam(page);
    await expect(page.locator('#qNum')).toHaveText('第 1 題');
  });

  test('交卷後清除 checkpoint，重整不再復活已完成考試', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    await page.locator('#choices .choice').first().click();

    page.on('dialog', d => d.accept()); // 未答完 confirm → 接受
    await page.locator('#submitBtn').click();
    await expect(page.locator('#resultView')).toBeVisible();
    expect(await readCheckpoint(page)).toBeNull();

    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
  });

  test('損毀的 checkpoint 安全退回設定畫面並清除', async ({ page }) => {
    await page.addInitScript(key => {
      localStorage.setItem(key, '{corrupted!!!');
    }, SESSION_KEY);
    await gotoQuizWithFixture(page);

    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    expect(await page.evaluate(k => localStorage.getItem(k), SESSION_KEY)).toBeNull();
  });

  test('結構不符的 checkpoint 安全退回（題數與作答數不一致）', async ({ page }) => {
    await page.addInitScript(key => {
      localStorage.setItem(key, JSON.stringify({
        v: 1, savedAt: Date.now(), timed: true,
        questions: [{ subj: 'x', stem: 'x', opts: ['a', 'b', 'c', 'd'], ans: 0 }],
        answers: [null, null, null], // 長度不一致
        flags: [false],
        cur: 0, durSec: 3600, remain: 3000, elapsed: 600,
      }));
    }, SESSION_KEY);
    await gotoQuizWithFixture(page);

    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    expect(await page.evaluate(k => localStorage.getItem(k), SESSION_KEY)).toBeNull();
  });

  test('過期的 checkpoint 視為 stale，安全退回設定畫面', async ({ page }) => {
    await page.addInitScript(key => {
      const q = { subj: '114年 警察法規', stem: '題幹', opts: ['a', 'b', 'c', 'd'], ans: 0 };
      localStorage.setItem(key, JSON.stringify({
        v: 1, savedAt: Date.now() - 25 * 3600 * 1000, timed: true,
        questions: Array(10).fill(q),
        answers: Array(10).fill(null),
        flags: Array(10).fill(false),
        cur: 0, durSec: 3600, remain: 3500, elapsed: 100,
      }));
    }, SESSION_KEY);
    await gotoQuizWithFixture(page);

    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    expect(await page.evaluate(k => localStorage.getItem(k), SESSION_KEY)).toBeNull();
  });

  for (const minutes of [60, 0]) {
    test(`中斷補償：${minutes} 分鐘模式在計時器停頓後保存及重開仍計入經過時間`, async ({ page, context }) => {
      await page.clock.install();
      await gotoQuizWithFixture(page);
      await page.locator('#segCount button[data-v="10"]').click();
      await page.locator(`#segTime button[data-v="${minutes}"]`).click();
      await page.locator('#startBtn').click();
      await page.locator('#choices .choice').first().click();
      const before = await readCheckpoint(page);

      // 模擬背景分頁／系統暫停：時間前進，但 interval 只補發一次。
      await page.clock.fastForward(31_000);
      await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
      const saved = await readCheckpoint(page);
      expect(saved.elapsed).toBeGreaterThanOrEqual(before.elapsed + 31);
      if (minutes) expect(saved.remain).toBeLessThanOrEqual(before.remain - 31);

      await page.close();
      const reopened = await context.newPage();
      await gotoQuizWithFixture(reopened);
      await reopened.locator('#resumeBtn').click();
      await expect(reopened.locator('#examView')).toBeVisible();
      await expect(reopened.locator('#miniGrid .mini.done')).toHaveCount(1);
    });
  }

  test('損毀計時資料：拒絕非布林模式及互相矛盾的計時欄位', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    const checkpoint = await readCheckpoint(page);
    const invalid = [
      { timed: 'false' }, { timed: null }, { timed: 1 },
      { timed: false }, { durSec: 0, remain: 0 },
      { timed: false, durSec: 0, remain: 'invalid' },
    ];
    for (const changes of invalid) {
      const loaded = await page.evaluate(({ key, checkpoint, changes }) => {
        localStorage.setItem(key, JSON.stringify({ ...checkpoint, ...changes }));
        return QuizSession.load();
      }, { key: SESSION_KEY, checkpoint, changes });
      expect(loaded, JSON.stringify(changes)).toBeNull();
    }
  });

  test('損毀題目資料：checkpoint 不能將 HTML 帶入題幹、選項或交卷回顧', async ({ page }) => {
    await gotoQuizWithFixture(page);
    await startFixtureExam(page);
    const checkpoint = await readCheckpoint(page);
    await page.reload();
    await expect(page.locator('#resumeCard')).toBeVisible();

    for (const field of ['stem', 'subj', 'opts']) {
      const loaded = await page.evaluate(({ key, checkpoint, field }) => {
        const cp = JSON.parse(JSON.stringify(checkpoint));
        const markup = '<img src="invalid:" onerror="window.checkpointScriptRan=true">';
        if (field === 'opts') cp.questions[0].opts[0] = markup;
        else cp.questions[0][field] = markup;
        localStorage.setItem(key, JSON.stringify(cp));
        return QuizSession.load();
      }, { key: SESSION_KEY, checkpoint, field });
      expect(loaded, field).toBeNull();
    }
    await page.locator('#resumeBtn').click();
    await expect(page.locator('#resumeCard')).toBeHidden();
    await expect(page.locator('#setupView')).toBeVisible();
    expect(await readCheckpoint(page)).toBeNull();
    expect(await page.evaluate(() => window.checkpointScriptRan)).toBeUndefined();
  });
});
