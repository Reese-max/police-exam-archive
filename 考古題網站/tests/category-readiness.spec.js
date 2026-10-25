const { test, expect } = require('@playwright/test');

const category = '/行政警察學系/行政警察學系考古題總覽.html';

test.describe('類科互動功能就緒', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('腳本慢載時明確停用控制，完成後才能用滑鼠與鍵盤篩選', async ({ page }) => {
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    let requested;
    const requestSeen = new Promise(resolve => { requested = resolve; });
    await page.route('**/js/app.js*', async route => {
      requested();
      await pending;
      await route.continue();
    });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    try {
      await page.goto(category, { waitUntil: 'commit' });
      const year = page.locator('.filter-chip[data-year="115"]');
      await year.waitFor({ state: 'visible' });
      await requestSeen;
      await expect(year).toBeDisabled();
      await expect(page.locator('#searchInput')).toBeDisabled();
      await expect(page.locator('#viewSubject')).toBeDisabled();
      await expect(page.locator('.subject-header').first()).toHaveAttribute('inert', '');
      await expect(page.locator('#appLoadingStatus')).toBeVisible();
      await expect(page.locator('#appLoadingStatus')).toContainText('載入中');
      await expect(page.locator('.sidebar-home[href="../index.html"]')).not.toHaveAttribute('inert', '');
      // A physical pointer click must remain disabled rather than waiting for
      // Playwright's automatic enabled check and masking the original race.
      const box = await year.boundingBox();
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      await page.keyboard.press('Tab');
      expect(await page.evaluate(() => document.activeElement.hasAttribute('data-app-pending'))).toBe(false);
      await page.waitForTimeout(500);
      expect(errors).toEqual([]);
      release();
      await page.waitForLoadState('load');
      await expect(year).toBeEnabled();
      await expect(page.locator('#appLoadingStatus')).toBeHidden();
      await expect(page.locator('.subject-header').first()).not.toHaveAttribute('inert', '');
      await year.focus();
      await page.keyboard.press('Enter');
      await expect(year).toHaveClass(/active/);
      await expect(page.locator('#year-114')).toBeHidden();
      await page.locator('.filter-chip[data-year="114"]').click();
      await expect(page.locator('#year-114')).toBeVisible();
      await expect(page.locator('#year-115')).toBeHidden();
      await page.locator('.filter-chip[data-year=""]').click();
      await expect(page.locator('#year-115')).toBeVisible();
      await expect(page.locator('#year-114')).toBeVisible();
      await page.locator('#searchInput').fill('憲法');
      await expect(page.locator('#searchStatsText')).toContainText('找到');
      expect(errors).toEqual([]);
    } finally {
      release();
    }
  });

  test('腳本載入失敗保留明確狀態與停用控制，不重播操作', async ({ page }) => {
    await page.route('**/js/app.js*', route => route.abort());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(category);
    await expect(page.locator('.filter-chip[data-year="115"]')).toBeDisabled();
    await expect(page.locator('#searchInput')).toBeDisabled();
    await expect(page.locator('#appLoadingStatus')).toBeVisible();
    await expect(page.locator('#appLoadingStatus')).toContainText('重新整理');
    await expect(page.locator('.sidebar-home[href="../index.html"]')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('無延遲的正常類科頁保留年份、科目與練習控制', async ({ page }) => {
    await page.goto(category);
    await expect(page.locator('.stat-value')).toHaveText(['10', '70', '2042']);
    await expect(page.locator('#appLoadingStatus')).toBeHidden();
    await page.locator('.filter-chip[data-year="115"]').click();
    await expect(page.locator('#year-115 .subject-card')).toHaveCount(7);
    await page.locator('#viewSubject').click();
    await expect(page.locator('#subjectView')).toBeVisible();
    await page.locator('#viewYear').click();
    await expect(page.locator('#yearView')).toBeVisible();
    await page.locator('#practiceToggle').click();
    await expect(page.locator('body')).toHaveClass(/practice-mode/);
    await page.locator('#practiceToggle').click();
    await expect(page.locator('body')).not.toHaveClass(/practice-mode/);
  });

  test('原生 SW 的舊無版本腳本快取不會配上新的停用控制頁面', async ({ page }) => {
    await page.goto('/index.html');
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    await page.evaluate(async () => {
      const cache = await caches.open('core-v1.7.3');
      // Deliberate legacy-cache canary. This checks cache-key isolation,
      // rather than claiming the canary is a real old application bundle.
      await cache.put(new URL('/js/app.js', location.origin), new Response(
        'window.legacyUnversionedAppCanary = true;',
        { headers: { 'Content-Type': 'application/javascript' } },
      ));
    });
    await page.goto(category);
    await expect(page.locator('.filter-chip[data-year="115"]')).toBeEnabled();
    await expect(page.locator('#appLoadingStatus')).toBeHidden();
    expect(await page.evaluate(() => window.legacyUnversionedAppCanary)).toBeUndefined();
    await page.locator('.filter-chip[data-year="115"]').click();
    await expect(page.locator('#year-114')).toBeHidden();
  });
});

test.describe('版本化類科腳本的匯出模組路徑', () => {
  test.use({ serviceWorkers: 'block' });

  test('保留原生相對模組路徑，不把 app 查詢參數接到檔名', async ({ page }) => {
    // Bounded loader contract only; these empty external dependency fixtures
    // do not prove PDF generation or font rendering.
    await page.route('https://cdn.jsdelivr.net/npm/pdf-lib@*/**', route =>
      route.fulfill({ contentType: 'application/javascript', body: '/* loader fixture */' }));
    await page.route('https://cdn.jsdelivr.net/npm/@pdf-lib/fontkit@*/**', route =>
      route.fulfill({ contentType: 'application/javascript', body: '/* loader fixture */' }));
    await page.goto(category);
    const response = page.waitForResponse(response => new URL(response.url()).pathname === '/js/pdf-export.js');
    await page.evaluate(() => _loadPdfLibraries());
    expect((await response).status()).toBe(200);
    expect(await page.evaluate(() => typeof PdfExport.extractExamData)).toBe('function');
  });
});
