/* PDF 匯出 smoke test
 * 跑法：node tests/pdf-export-smoke.js
 * 前置：先起 npx serve . -l 8799
 */
const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8799';
const TARGET = BASE + '/' + encodeURIComponent('行政管理學系') + '/' +
               encodeURIComponent('行政管理學系考古題總覽') + '.html';

const OUT_DIR = path.join(__dirname, '..', 'test-results', 'pdf-smoke');
fs.mkdirSync(OUT_DIR, { recursive: true });

function attachConsoleSpy(page) {
  const errors = [];
  page.on('pageerror', e => errors.push('[pageerror] ' + e.message));
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push('[console.error] ' + msg.text());
  });
  return () => errors;
}

async function testDesktop(browser) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errs = attachConsoleSpy(page);

  await page.addInitScript(() => {
    window.__printCalled = 0;
    window.print = function () { window.__printCalled++; };
  });

  await page.goto(TARGET, { waitUntil: 'networkidle' });
  await page.locator('#exportBtn').click();
  await page.locator('#exportPanel').waitFor({ state: 'visible' });
  await page.locator('button.export-option').nth(1).click();   // 不含答案
  await page.waitForFunction(() => window.__printCalled > 0, null, { timeout: 5000 });

  const printCount = await page.evaluate(() => window.__printCalled);
  const errors = errs();
  await ctx.close();

  return {
    label: 'desktop',
    pass: printCount === 1 && errors.length === 0,
    printCount,
    errors,
  };
}

async function testMobile(browser) {
  const ctx = await browser.newContext({ ...devices['iPhone 13'], acceptDownloads: true });
  const page = await ctx.newPage();
  const errs = attachConsoleSpy(page);

  // 攔截 PdfExport 賦值，把 deliverPdf 換成把 bytes 寫到 window
  // 同時：把 woff2 字型請求重導到 otf（驗證 fontkit woff2 bug 假設）
  await page.addInitScript(() => {
    let _holder;
    Object.defineProperty(window, 'PdfExport', {
      configurable: true,
      get() { return _holder; },
      set(v) {
        const origDeliver = v.deliverPdf;
        v.deliverPdf = function (bytes /*, filename*/) {
          window.__pdfBytes = Array.from(new Uint8Array(bytes));
          window.__pdfFilename = arguments[1];
          return Promise.resolve();
        };
        _holder = v;
      },
    });

    // 觀察點：fontkit fallback 走了沒（記錄載入過的字型 URL）
    window.__loadedFonts = [];
    const origFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      const url = typeof input === 'string' ? input : input.url;
      if (url && /NotoSansTC.*\.(woff2|otf)$/.test(url)) {
        window.__loadedFonts.push(url);
      }
      return origFetch(input, init);
    };
  });

  await page.goto(TARGET, { waitUntil: 'networkidle' });
  const isMobile = await page.evaluate(() => isMobileDevice());

  await page.locator('#exportBtn').click();
  await page.locator('#exportPanel').waitFor({ state: 'visible' });

  // 只保留第一個年度 + 第一個科目（縮小範圍加速）
  await page.evaluate(() => {
    document.querySelectorAll('input[name="exportYear"]').forEach((cb, i) => { cb.checked = i === 0; });
    document.querySelectorAll('input[name="exportSubject"]').forEach((cb, i) => { cb.checked = i === 0; });
    if (typeof updateExportPreview === 'function') updateExportPreview();
  });

  await page.locator('button.export-option').nth(1).click();   // 不含答案

  let bytes;
  try {
    const handle = await page.waitForFunction(() => window.__pdfBytes, null, { timeout: 90000 });
    bytes = await handle.jsonValue();
  } catch (e) {
    const errors = errs();
    await ctx.close();
    return { label: 'mobile', pass: false, isMobile, errors, reason: 'PDF bytes timeout' };
  }

  const filename = await page.evaluate(() => window.__pdfFilename);
  const loadedFonts = await page.evaluate(() => window.__loadedFonts || []);
  const headOk = bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46 && bytes[4] === 0x2D;
  const outPath = path.join(OUT_DIR, filename || 'mobile-export.pdf');
  fs.writeFileSync(outPath, Buffer.from(bytes));

  const errors = errs();
  await ctx.close();

  return { label: 'mobile', pass: headOk && errors.length === 0, isMobile, filename, size: bytes.length, headOk, loadedFonts: loadedFonts.map(u => u.split('/').pop()), outPath, errors };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  try {
    console.log('TARGET =', TARGET);
    console.log('\n--- Desktop path ---');
    const d = await testDesktop(browser);
    console.log(JSON.stringify(d, null, 2));
    results.push(d);

    console.log('\n--- Mobile path ---');
    const m = await testMobile(browser);
    console.log(JSON.stringify(m, null, 2));
    results.push(m);
  } finally {
    await browser.close();
  }
  const fail = results.filter(r => !r.pass);
  console.log(`\n=== SUMMARY: ${results.length - fail.length}/${results.length} pass ===`);
  process.exit(fail.length ? 1 : 0);
})();
