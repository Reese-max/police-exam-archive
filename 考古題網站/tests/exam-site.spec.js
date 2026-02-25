// @ts-check
const { test, expect } = require('@playwright/test');

/* ===== 首頁測試 ===== */
test.describe('首頁', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/index.html');
    await page.waitForLoadState('domcontentloaded');
  });

  test('應有正確的頁面標題', async ({ page }) => {
    await expect(page).toHaveTitle(/三等警察特考考古題總覽/);
  });

  test('應有 17 個類科連結指向考古題總覽頁面', async ({ page }) => {
    const deptLinks = page.locator('.category-list a[href*="考古題總覽"]');
    await expect(deptLinks).toHaveCount(17);
  });

  test('每個類科連結路徑應正確且可點擊', async ({ page }) => {
    const links = page.locator('.category-list a[href*="考古題總覽"]');
    const count = await links.count();
    for (let i = 0; i < count; i++) {
      const href = await links.nth(i).getAttribute('href');
      expect(href).toMatch(/\.html$/);
      expect(href).toContain('考古題總覽');
    }
  });

  test('Hero 統計區應顯示 17 類科 / 1090 試卷 / 22523 題目', async ({ page }) => {
    const values = page.locator('.hero-stat-value');
    await expect(values).toHaveCount(3);
    await expect(values.nth(0)).toHaveText('17');
    await expect(values.nth(1)).toHaveText('1090');
    await expect(values.nth(2)).toHaveText('22523');
  });

  test('暗色模式切換（首頁）', async ({ page }) => {
    await page.locator('#darkToggle').click();
    await expect(page.locator('html')).toHaveClass(/dark/);
    // 再點一次切回淺色
    await page.locator('#darkToggle').click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);
  });
});

/* ===== 類科頁面：行政警察學系 ===== */
test.describe('類科頁面 - 行政警察學系', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB%E8%80%83%E5%8F%A4%E9%A1%8C%E7%B8%BD%E8%A6%BD.html');
    await page.waitForLoadState('domcontentloaded');
  });

  test('頁面標題包含行政警察學系', async ({ page }) => {
    await expect(page).toHaveTitle(/行政警察學系/);
  });

  test('統計列應顯示正確數據', async ({ page }) => {
    const statValues = page.locator('.stat-value');
    await expect(statValues).toHaveCount(3);
    // 9 年度、63 試卷、1812 題目
    await expect(statValues.nth(0)).toHaveText('9');
    await expect(statValues.nth(1)).toHaveText('63');
    await expect(statValues.nth(2)).toHaveText('1812');
  });

  /* --- 搜尋功能 --- */
  test('搜尋功能：輸入關鍵字後顯示篩選結果', async ({ page }) => {
    const searchInput = page.locator('#searchInput');
    await searchInput.fill('憲法');
    // 等待 debounce
    await page.waitForTimeout(500);
    const stats = page.locator('#searchStatsText');
    const statsText = await stats.textContent();
    expect(statsText).toContain('找到');
    expect(statsText).toContain('匹配');
  });

  test('搜尋功能：高亮標記應出現', async ({ page }) => {
    const searchInput = page.locator('#searchInput');
    await searchInput.fill('憲法');
    await page.waitForTimeout(500);
    const highlights = page.locator('.highlight');
    expect(await highlights.count()).toBeGreaterThan(0);
  });

  test('搜尋功能：清空輸入後恢復全部', async ({ page }) => {
    const searchInput = page.locator('#searchInput');
    await searchInput.fill('憲法');
    await page.waitForTimeout(500);
    await searchInput.fill('');
    await page.waitForTimeout(300);
    const stats = page.locator('#searchStatsText');
    await expect(stats).toHaveText('');
    // 所有卡片應可見
    const hiddenCards = page.locator('#yearView .subject-card[style*="display: none"]');
    expect(await hiddenCards.count()).toBe(0);
  });

  /* --- 年度篩選 --- */
  test('年度篩選：點擊年份 chip 後只顯示該年度', async ({ page }) => {
    // 點擊 114 年份
    const chip114 = page.locator('.filter-chip[data-year="114"]');
    await chip114.click();
    await expect(chip114).toHaveClass(/active/);
    // 114 年度區段應可見
    const year114 = page.locator('#year-114');
    await expect(year114).toBeVisible();
    // 其他年度區段應被隱藏
    const year106 = page.locator('#year-106');
    await expect(year106).toBeHidden();
  });

  /* --- 書籤功能 --- */
  test('書籤：點擊後變星號，重整後保留', async ({ page }) => {
    // 展開第一張卡片讓書籤可見
    const firstCard = page.locator('#yearView .subject-card').first();
    const firstBookmarkBtn = firstCard.locator('.bookmark-btn');
    // 點擊書籤
    await firstBookmarkBtn.click();
    await expect(firstBookmarkBtn).toHaveClass(/active/);
    await expect(firstBookmarkBtn).toHaveText('★');

    // 重新載入
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    // 確認書籤保留
    const reloadedBtn = page.locator('#yearView .subject-card').first().locator('.bookmark-btn');
    await expect(reloadedBtn).toHaveClass(/active/);
    await expect(reloadedBtn).toHaveText('★');

    // 清理：取消書籤
    await reloadedBtn.click();
    await expect(reloadedBtn).not.toHaveClass(/active/);
  });

  /* --- 暗色模式 --- */
  test('暗色模式：切換並重整後保留', async ({ page }) => {
    // 先確認不是暗色
    const html = page.locator('html');
    // 點擊暗色切換
    await page.locator('#darkToggle').click();
    await expect(html).toHaveClass(/dark/);

    // 重新載入
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('html')).toHaveClass(/dark/);

    // 清理：切回淺色
    await page.locator('#darkToggle').click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);
  });

  /* --- 匯出面板 --- */
  test('匯出面板：開啟後顯示年度和科目 checkbox', async ({ page }) => {
    const exportBtn = page.locator('#exportBtn');
    await exportBtn.click();
    const panel = page.locator('#exportPanel');
    await expect(panel).toBeVisible();

    // 應有年度 checkbox
    const yearChecks = page.locator('#exportSelectors input[data-export-year]');
    expect(await yearChecks.count()).toBeGreaterThan(0);

    // 應有科目 checkbox
    const subjectChecks = page.locator('#exportSelectors input[data-export-subject]');
    expect(await subjectChecks.count()).toBeGreaterThan(0);

    // 應顯示匯出數量預覽
    const countText = page.locator('#exportCount');
    const text = await countText.textContent();
    expect(text).toContain('將匯出');
    expect(text).toContain('份試卷');
  });

  test('匯出面板：取消按鈕關閉面板', async ({ page }) => {
    await page.locator('#exportBtn').click();
    await expect(page.locator('#exportPanel')).toBeVisible();
    await page.locator('.export-cancel').click();
    await expect(page.locator('#exportPanel')).toBeHidden();
  });

  /* --- 練習模式 --- */
  test('練習模式：開啟後 body 加上 practice-mode class', async ({ page }) => {
    await page.locator('#practiceToggle').click();
    await expect(page.locator('body')).toHaveClass(/practice-mode/);
    // 分數面板應可見
    await expect(page.locator('#practiceScore')).toHaveClass(/visible/);
  });

  test('練習模式：點擊選項後顯示作答反饋', async ({ page }) => {
    // 開啟練習模式
    await page.locator('#practiceToggle').click();
    await expect(page.locator('body')).toHaveClass(/practice-mode/);

    // 展開第一張卡片
    const firstHeader = page.locator('#yearView .subject-header').first();
    await firstHeader.click();
    await page.waitForTimeout(300);

    // 找到第一個有選項的 q-block
    const firstBlock = page.locator('#yearView .q-block[data-answer]').first();
    const firstOpt = firstBlock.locator('.mc-opt').first();
    if (await firstOpt.isVisible()) {
      await firstOpt.click();
      // q-block 應標記已作答
      await expect(firstBlock).toHaveClass(/answered/);
      // 選項應有 correct 或 wrong class
      const hasCorrect = await firstOpt.evaluate(el => el.classList.contains('correct'));
      const hasWrong = await firstOpt.evaluate(el => el.classList.contains('wrong'));
      expect(hasCorrect || hasWrong).toBe(true);
      // 分數應更新
      const scoreTotal = page.locator('#scoreTotal');
      await expect(scoreTotal).not.toHaveText('0');
    }
  });

  test('練習模式：結束後清除 practice-mode', async ({ page }) => {
    await page.locator('#practiceToggle').click();
    await expect(page.locator('body')).toHaveClass(/practice-mode/);
    // 再點一次結束
    await page.locator('#practiceToggle').click();
    await expect(page.locator('body')).not.toHaveClass(/practice-mode/);
  });

  /* --- 卡片展開/收合 --- */
  test('卡片展開收合', async ({ page }) => {
    const firstCard = page.locator('#yearView .subject-card').first();
    const header = firstCard.locator('.subject-header');
    // 初始應該是收合
    await expect(firstCard).not.toHaveClass(/open/);
    // 點擊展開
    await header.click();
    await expect(firstCard).toHaveClass(/open/);
    // subject-body 應可見
    await expect(firstCard.locator('.subject-body')).toBeVisible();
    // 再點一次收合
    await header.click();
    await expect(firstCard).not.toHaveClass(/open/);
  });

  /* --- 科目瀏覽切換 --- */
  test('切換依科目瀏覽', async ({ page }) => {
    await page.locator('#viewSubject').click();
    await expect(page.locator('#subjectView')).toBeVisible();
    await expect(page.locator('#yearView')).toBeHidden();
    // 切回年份瀏覽
    await page.locator('#viewYear').click();
    await expect(page.locator('#yearView')).toBeVisible();
    await expect(page.locator('#subjectView')).toBeHidden();
  });

  /* --- 側邊欄 --- */
  test('側邊欄年份手風琴展開', async ({ page }) => {
    // 桌面版側邊欄預設可見
    const firstSidebarYear = page.locator('.sidebar-year').first();
    await firstSidebarYear.click();
    await expect(firstSidebarYear).toHaveClass(/active/);
    // 對應的 sidebar-subjects 應展開（CSS: .sidebar-year.active + .sidebar-subjects { display:block; }）
    const subjects = page.locator('.sidebar-year.active + .sidebar-subjects');
    await expect(subjects).toBeVisible();
  });

  /* --- 顯示/隱藏全部答案 --- */
  test('顯示答案按鈕切換', async ({ page }) => {
    const answerBtn = page.locator('#answerToggle');
    await answerBtn.click();
    await expect(answerBtn).toHaveClass(/active/);
    await expect(answerBtn).toHaveText('隱藏答案');
    // q-block 應加上 show-answer
    const showAnswer = page.locator('#yearView .q-block.show-answer');
    expect(await showAnswer.count()).toBeGreaterThan(0);
    // 再切換回來
    await answerBtn.click();
    await expect(answerBtn).not.toHaveClass(/active/);
    await expect(answerBtn).toHaveText('顯示答案');
  });
});

/* ===== 手機偵測 ===== */
test.describe('手機偵測', () => {
  test('桌面環境下 isMobileDevice 應回傳 false', async ({ page }) => {
    await page.goto('/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB%E8%80%83%E5%8F%A4%E9%A1%8C%E7%B8%BD%E8%A6%BD.html');
    await page.waitForLoadState('domcontentloaded');
    const result = await page.evaluate(() => {
      return typeof isMobileDevice === 'function' ? isMobileDevice() : null;
    });
    expect(result).toBe(false);
  });
});

/* ===== 只看書籤篩選 ===== */
test.describe('書籤篩選', () => {
  test('只看書籤切換', async ({ page }) => {
    await page.goto('/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB%E8%80%83%E5%8F%A4%E9%A1%8C%E7%B8%BD%E8%A6%BD.html');
    await page.waitForLoadState('domcontentloaded');
    const filterBtn = page.locator('#bookmarkFilter');
    await filterBtn.click();
    await expect(filterBtn).toHaveClass(/active/);
    await expect(filterBtn).toHaveText('顯示全部');
    // 再點回來
    await filterBtn.click();
    await expect(filterBtn).not.toHaveClass(/active/);
    await expect(filterBtn).toHaveText('只看書籤');
  });
});

/* ===== 深度檢查新增測試 ===== */
test.describe('深度檢查修復驗證', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB%E8%80%83%E5%8F%A4%E9%A1%8C%E7%B8%BD%E8%A6%BD.html');
    await page.waitForLoadState('domcontentloaded');
  });

  /* 3.1 Hash 導航自動展開 */
  test('Hash 導航：帶 hash 開啟時卡片自動展開', async ({ page }) => {
    // 先取得第一張卡片的 id
    const firstCardId = await page.locator('#yearView .subject-card[id]').first().getAttribute('id');
    // 導航到帶 hash 的 URL
    await page.goto('/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB/%E8%A1%8C%E6%94%BF%E8%AD%A6%E5%AF%9F%E5%AD%B8%E7%B3%BB%E8%80%83%E5%8F%A4%E9%A1%8C%E7%B8%BD%E8%A6%BD.html#' + firstCardId);
    await page.waitForLoadState('domcontentloaded');
    // 等待 handleHash 的 rAF 完成
    await page.waitForTimeout(500);
    // 卡片應自動展開
    const card = page.locator('[id="' + firstCardId + '"]');
    await expect(card).toHaveClass(/open/);
  });

  /* 3.2 鍵盤 `/` 聚焦搜尋 */
  test('鍵盤快捷鍵：按 / 聚焦搜尋框', async ({ page }) => {
    // 先確認搜尋框未聚焦
    const searchInput = page.locator('#searchInput');
    await expect(searchInput).not.toBeFocused();
    // 按 `/` 鍵
    await page.keyboard.press('/');
    // 搜尋框應被聚焦
    await expect(searchInput).toBeFocused();
  });

  /* 3.3 鍵盤 Escape 清空 */
  test('鍵盤快捷鍵：搜尋框中按 Escape 清空並失焦', async ({ page }) => {
    const searchInput = page.locator('#searchInput');
    // 先輸入文字
    await searchInput.fill('憲法');
    await page.waitForTimeout(400);
    await searchInput.focus();
    // 按 Escape
    await page.keyboard.press('Escape');
    // 搜尋框應清空
    await expect(searchInput).toHaveValue('');
    // 搜尋框應失焦
    await expect(searchInput).not.toBeFocused();
  });

  /* 3.4 錯誤監控 UI */
  test('錯誤監控：觸發錯誤後顯示報告按鈕和面板', async ({ page }) => {
    // 注入一個 JS 錯誤到 onerror
    await page.evaluate(() => {
      window.onerror('Test error message', 'test.js', 1, 1, new Error('test'));
    });
    await page.waitForTimeout(300);
    // 錯誤報告按鈕應出現
    const errorBtn = page.locator('#errorReportBtn');
    await expect(errorBtn).toBeVisible();
    // 點擊開啟面板
    await errorBtn.click();
    await page.waitForTimeout(300);
    const overlay = page.locator('#errorReportOverlay');
    await expect(overlay).toBeVisible();
    // 面板中應包含錯誤訊息
    const errorMsg = page.locator('.error-msg');
    expect(await errorMsg.count()).toBeGreaterThan(0);
    // 清理：清除錯誤日誌
    await page.evaluate(() => { window._clearErrorLog(); });
  });

  /* 3.5 搜尋跳轉按鈕 */
  test('搜尋跳轉：多匹配時出現 ◀▶ 按鈕', async ({ page }) => {
    const searchInput = page.locator('#searchInput');
    // 輸入常見詞讓多張卡片匹配
    await searchInput.fill('法');
    await page.waitForTimeout(500);
    // 確認有多個 highlight
    const highlights = page.locator('.highlight');
    const highlightCount = await highlights.count();
    if (highlightCount > 1) {
      // 跳轉按鈕應出現
      const jumpBtns = page.locator('.search-jump button');
      await expect(jumpBtns).toHaveCount(2); // ◀ 和 ▶
      // 點擊 ▶ 應更新計數器
      await jumpBtns.nth(1).click();
      const counter = page.locator('#hitCounter');
      await expect(counter).toContainText('/');
    }
  });

  /* 3.6 科目篩選 */
  test('科目篩選：選擇科目後只顯示匹配卡片', async ({ page }) => {
    const subjectFilter = page.locator('#subjectFilter');
    // 取得第一個非空選項
    const options = subjectFilter.locator('option');
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThan(1); // 至少有「全部」和一個科目
    // 選擇第二個選項（第一個科目）
    const firstSubjectValue = await options.nth(1).getAttribute('value');
    await subjectFilter.selectOption(firstSubjectValue);
    // 等待篩選
    await page.waitForTimeout(300);
    // 顯示的卡片標題都應包含該科目名
    const visibleCards = page.locator('#yearView .subject-card:not([style*="display: none"])');
    const count = await visibleCards.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const title = await visibleCards.nth(i).locator('.subject-header h3').textContent();
      expect(title).toContain(firstSubjectValue);
    }
  });

  /* 3.7 匯出全選/取消 */
  test('匯出面板：全選與取消功能', async ({ page }) => {
    // 開啟匯出面板
    await page.locator('#exportBtn').click();
    await expect(page.locator('#exportPanel')).toBeVisible();

    // 找到年度的「全選」按鈕（可能文字是「全選」或「取消全選」）
    const yearToggle = page.locator('.export-group').first().locator('.export-toggle-all');
    const yearChecks = page.locator('#exportSelectors input[data-export-year]');
    const totalYears = await yearChecks.count();

    // 初始應該全部勾選
    for (let i = 0; i < totalYears; i++) {
      await expect(yearChecks.nth(i)).toBeChecked();
    }

    // 點擊全選按鈕（因為已全選，應變成全取消）
    await yearToggle.click();
    for (let i = 0; i < totalYears; i++) {
      await expect(yearChecks.nth(i)).not.toBeChecked();
    }

    // 再點一次應全選
    await yearToggle.click();
    for (let i = 0; i < totalYears; i++) {
      await expect(yearChecks.nth(i)).toBeChecked();
    }
  });

  /* 3.8 reduced-motion */
  test('reduced-motion：動畫持續時間應趨近 0', async ({ page }) => {
    // 模擬 reduced-motion
    await page.emulateMedia({ reducedMotion: 'reduce' });
    // 重新載入讓 CSS 生效
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    // 檢查任意有動畫的元素，其動畫時長應為 0.01ms
    const duration = await page.evaluate(() => {
      const el = document.querySelector('.subject-card') || document.querySelector('.toolbar-btn');
      if (!el) return null;
      const style = window.getComputedStyle(el);
      return style.transitionDuration;
    });
    // 在 reduced-motion 下，transition-duration 應為 0.01ms 或 0s
    if (duration) {
      const ms = parseFloat(duration);
      expect(ms).toBeLessThanOrEqual(0.02);
    }
  });
});
