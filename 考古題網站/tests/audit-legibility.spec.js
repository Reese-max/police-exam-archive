const { test, expect } = require('@playwright/test');
const { readFileSync, writeFileSync } = require('node:fs');
const path = require('node:path');

// Small owned data/dependency fixtures isolate real DOM/CSS and native local
// save/reload behavior. They are not a corpus, MiniSearch or provider-quality test.
async function ownedQuiz(page) {
  const questions = [
    { cat: 'Owned', cats: ['Owned'], yr: 113, sub: 'Owned law', no: '1', type: 'choice', passage: '', stem: 'Owned question one', optA: 'First', optB: 'Second', optC: 'Third', optD: 'Fourth', ans: 'A' },
    { cat: 'Other', cats: ['Other'], yr: 114, sub: 'Other law', no: '2', type: 'choice', passage: '', stem: 'Owned question two', optA: 'First', optB: 'Second', optC: 'Third', optD: 'Fourth', ans: 'B' },
  ];
  await page.route('**/minisearch@*/**', route => route.fulfill({
    contentType: 'application/javascript', body: 'window.MiniSearch = class { addAll() {} };',
  }));
  await page.route('**/data/search-index.json', route => route.fulfill({ json: {
    v: 2, datasetVersion: 'owned-style-contract-v1', stats: { total: 2 },
    facets: { categories: ['Owned', 'Other'], years: [113, 114], subjects: ['Owned law', 'Other law'] },
    columns: Object.fromEntries(Object.keys(questions[0]).map(key => [key, questions.map(q => q[key])])),
  } }));
}

async function settledTheme(page, theme) {
  if (await page.locator('html').getAttribute('data-theme') !== theme) {
    await page.locator('#themeToggle').click();
  }
  const expected = await page.evaluate(() => {
    const hex = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
    return 'rgb(' + [1, 3, 5].map(n => parseInt(hex.slice(n, n + 2), 16)).join(', ') + ')';
  });
  await page.waitForFunction(value => getComputedStyle(document.body).backgroundColor === value, expected);
}

async function contrast(locator) {
  await locator.scrollIntoViewIfNeeded();
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number)
      .map(value => { value /= 255; return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4; })
      .reduce((sum, value, i) => sum + value * [0.2126, 0.7152, 0.0722][i], 0);
    const foreground = luminance(style.color), background = luminance(style.backgroundColor);
    return { color: style.color, background: style.backgroundColor,
      ratio: (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05),
      disabled: element.matches(':disabled') };
  });
}

test.describe('核心控制主題字色', () => {
  test.use({ serviceWorkers: 'block', viewport: { width: 390, height: 844 } });

  for (const theme of ['light', 'dark']) {
    test(`${theme} 主操作、hover 與已選狀態保持可讀`, async ({ page }, info) => {
      await ownedQuiz(page);
      page.on('dialog', dialog => dialog.accept());
      await page.goto('/quiz.html');
      await expect(page.locator('#matchCount')).toHaveText('2 題');
      await settledTheme(page, theme);
      const observations = [];
      async function readable(selector, label, state = 'normal') {
        const locator = page.locator(selector).first();
        await locator.scrollIntoViewIfNeeded();
        await page.mouse.move(0, 0);
        if (state === 'hover') await locator.hover();
        if (state === 'focus') await locator.focus();
        await locator.evaluate(el => Promise.all(el.getAnimations().map(animation => animation.finished)));
        const value = await contrast(locator);
        observations.push({ label, ...value });
        expect.soft(value.disabled, label).toBe(false);
        expect.soft(value.ratio, label).toBeGreaterThanOrEqual(4.5);
      }
      await readable('#startBtn', 'start-normal');
      await readable('#startBtn', 'start-hover', 'hover');
      await readable('#segCount button.on', 'selected-count');
      await readable('#segCount button.on', 'selected-count-focus', 'focus');
      await readable('#segTime button.on', 'selected-time');
      await readable('#segTime button.on', 'selected-time-focus', 'focus');
      await page.locator('#startBtn').click();
      await expect(page.locator('#examView')).toBeVisible();
      await readable('#qNum', 'question-number');
      const wrong = await page.evaluate(() => [0, 1, 2, 3].find(index => !questions[cur].accepted.includes(index)));
      await page.locator('.choice[data-i="' + wrong + '"]').click();
      await page.waitForFunction(index => !checkpointBusy && answers[0] === index, wrong);
      await readable('.choice.sel .clbl', 'selected-choice');
      await readable('.mini.done', 'answered-navigation');
      await readable('.mini.done', 'answered-navigation-focus', 'focus');
      await readable('#submitBtn', 'submit-normal');
      await readable('#submitBtn', 'submit-focus', 'focus');
      await page.reload();
      await expect(page.locator('#resumeBanner')).toBeVisible();
      await readable('#resumeBtn', 'resume-normal');
      await readable('#resumeBtn', 'resume-hover', 'hover');
      await readable('#resumeBtn', 'resume-focus', 'focus');
      await page.locator('#resumeBtn').click();
      await page.locator('#submitBtn').click();
      await expect(page.locator('#resultView')).toBeVisible();
      await readable('#retryBtn', 'retry-primary');
      await readable('#retryBtn', 'retry-focus', 'focus');
      await readable('.rv-opt.correct .rl2', 'correct-review-label');
      await readable('.rv-opt.wrong .rl2', 'wrong-review-label');
      await page.goto('/search.html');
      await settledTheme(page, theme);
      await readable('#searchBtn', 'search-normal');
      await readable('#searchBtn', 'search-hover', 'hover');
      await info.attach('actual-contrast.json', { body: Buffer.from(JSON.stringify(observations)), contentType: 'application/json' });
    });
  }

  test('字色修補不改變無匹配題目時的原生停用語意', async ({ page }) => {
    await ownedQuiz(page);
    await page.goto('/quiz.html');
    await expect(page.locator('#matchCount')).toHaveText('2 題');
    await page.locator('#fCat').selectOption('Owned');
    await page.locator('#fYear').selectOption('114');
    await expect(page.locator('#matchCount')).toHaveText('0 題');
    await expect(page.locator('#startBtn')).toBeDisabled();
    await expect(page.locator('#examView')).toBeHidden();
    await page.locator('#fYear').selectOption('');
    await expect(page.locator('#matchCount')).toHaveText('1 題');
    await expect(page.locator('#startBtn')).toBeEnabled();
  });
});

test.describe('正式來源主操作驗收（#109）', () => {
  // One build, then ordinary Chromium navigation: no replaced responses or data.
  test.describe.configure({ mode: 'serial' });

  for (const width of [390, 1280]) {
    for (const theme of ['light', 'dark']) {
      test(`${width}px ${theme} 的 normal、hover、focus 及開始／搜尋`, async ({ page }, info) => {
        test.setTimeout(60000);
        await page.setViewportSize({ width, height: 900 });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const observations = [];
        async function openSource(file) {
          const response = await page.goto('/' + file);
          expect(response.ok()).toBe(true);
          expect(await response.body()).toEqual(readFileSync(path.resolve(__dirname, '..', file)));
          await settledTheme(page, theme);
        }
        async function readableAction(selector, previous) {
          const button = page.locator(selector);
          await expect(button).toBeEnabled();
          for (const state of ['normal', 'hover', 'focus']) {
            await button.scrollIntoViewIfNeeded();
            await page.mouse.move(0, 0);
            await page.locator(previous).focus();
            if (state === 'hover') await button.hover();
            if (state === 'focus') {
              await page.keyboard.press('Tab');
              await expect(button).toBeFocused();
              expect(await button.evaluate(el => el.matches(':focus-visible'))).toBe(true);
            }
            await button.evaluate(el => Promise.all(el.getAnimations().map(animation => animation.finished)));
            const value = await contrast(button);
            observations.push({ selector, state, ...value });
            expect(value.disabled).toBe(false);
            expect(value.ratio, `${selector} ${state}`).toBeGreaterThanOrEqual(4.5);
          }
          const screenshot = info.outputPath(selector.slice(1) + '.png');
          await page.screenshot({ path: screenshot });
          await info.attach(selector.slice(1), { path: screenshot, contentType: 'image/png' });
        }
        await openSource('quiz.html');
        await expect(page.locator('#startBtn')).toBeEnabled({ timeout: 20000 });
        await readableAction('#startBtn', '#segTime button:last-child');
        await page.keyboard.press('Enter');
        await expect(page.locator('#examView')).toBeVisible();
        await expect(page.locator('#totalNum')).toHaveText('20');
        await expect(page.locator('.mini')).toHaveCount(20);
        await expect(page.locator('#qStem')).not.toBeEmpty();
        await openSource('search.html');
        await expect(page.locator('#statTotal')).not.toHaveText('—', { timeout: 20000 });
        await page.locator('#q').fill('憲法');
        await readableAction('#searchBtn', '#q');
        await page.keyboard.press('Enter');
        await expect(page.locator('#results .result').first()).toBeVisible();
        await expect(page.locator('#results .hl').first()).toHaveText('憲法');
        for (const selector of ['.opt.correct .lbl', '.ans-pill']) {
          const value = await contrast(page.locator(selector).first());
          observations.push({ selector, state: 'normal', ...value });
          expect(value.ratio, selector).toBeGreaterThanOrEqual(4.5);
        }
        expect(errors).toEqual([]);
        const receipt = info.outputPath('actual-source-contrast.json');
        writeFileSync(receipt, JSON.stringify({ width, theme, observations }, null, 2));
        await info.attach('actual-source-contrast.json', {
          path: receipt, contentType: 'application/json',
        });
      });
    }
  }
});

test.describe('今日複習設定重排及持久化', () => {
  test.use({ serviceWorkers: 'block' });

  for (const width of [320, 390, 1280]) {
    test(`${width}px 的設定值可讀且原生編輯、blur、reload 不變`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 });
      await ownedQuiz(page);
      await page.goto('/quiz.html');
      await expect(page.locator('#matchCount')).toHaveText('2 題');
      await page.locator('.deadline-grid').scrollIntoViewIfNeeded();
      const layout = await page.evaluate(() => {
        const grid = document.querySelector('.deadline-grid');
        return { columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
          client: grid.clientWidth, scroll: grid.scrollWidth,
          inputs: ['dailyQuestionLimit', 'dailyMinutes', 'planningMinutesPerQuestion'].map(id => {
            const input = document.getElementById(id), style = getComputedStyle(input);
            const canvas = document.createElement('canvas'), context = canvas.getContext('2d');
            context.font = style.font;
            return { id, client: input.clientWidth,
              content: input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
              measured: context.measureText(input.value).width };
          }) };
      });
      await info.attach('actual-layout.json', { body: Buffer.from(JSON.stringify(layout)), contentType: 'application/json' });
      expect(layout.scroll).toBeLessThanOrEqual(layout.client);
      expect(layout.columns).toBe(width <= 560 ? 1 : 4);
      for (const input of layout.inputs) {
        expect(input.content, input.id).toBeGreaterThanOrEqual(input.measured + 16); // reserve native number spinner
      }
      await page.locator('#deadlineEnabled').focus();
      for (let i = 0; i < 16 && await page.evaluate(() => document.activeElement.id !== 'dailyQuestionLimit'); i++) {
        await page.keyboard.press('Tab');
      }
      expect(await page.evaluate(() => document.activeElement.id)).toBe('dailyQuestionLimit');
      const value = width === 320 ? '37' : width === 390 ? '42' : '53';
      await page.keyboard.press('Control+A');
      await page.keyboard.type(value);
      await page.keyboard.press('Tab');
      await page.waitForFunction(value => AttemptLedger.getSettings().dailyQuestionLimit === Number(value), value);
      await page.reload();
      await expect(page.locator('#dailyQuestionLimit')).toHaveValue(value);
      expect(await page.evaluate(() => AttemptLedger.getSettings().dailyQuestionLimit)).toBe(Number(value));
      await expect(page.locator('#dailyQuestionLimit')).toHaveAttribute('max', '200');
      await expect(page.locator('#dailyMinutes')).toHaveAttribute('max', '1440');
      await expect(page.locator('#planningMinutesPerQuestion')).toHaveAttribute('max', '120');
    });
  }
});
