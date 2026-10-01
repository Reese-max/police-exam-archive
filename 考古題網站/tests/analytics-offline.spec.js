const { test, expect } = require('@playwright/test');
const http = require('node:http');
const path = require('node:path');
const serveHandler = require('serve-handler');

// Issue #75: Analytics is precached as a core offline page, so its Chart.js
// dependency must also be a controlled core asset. This spec reproduces the
// reported scenario with a fresh browser profile: visit only the homepage
// online (installing the service worker and the precache), then lose the
// origin entirely and open Analytics for the first time offline.
test('first offline Analytics visit renders charts after only visiting the homepage online', async ({ browser }) => {
  test.setTimeout(90000);

  let disconnected = false;
  const server = http.createServer((request, response) => {
    if (disconnected) {
      request.socket.destroy();
      return;
    }
    serveHandler(request, response, {
      public: path.join(__dirname, '..'),
      cleanUrls: false,
    }).catch(error => {
      response.statusCode = 500;
      response.end(String(error));
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;

  // Fresh context = fresh profile: no storage, no caches, no prior visits.
  const context = await browser.newContext({ serviceWorkers: 'allow' });
  const page = await context.newPage();

  try {
    // CDN/font requests must not make the offline phase hang.
    await context.route(url => url.origin !== origin, route => route.abort());

    await page.goto(`${origin}/index.html`);
    // The SW installs, precaches CORE_ASSETS, then claims the page.
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    expect(await page.evaluate(
      () => caches.match('./vendor/chart.js-4.4.1/chart.umd.js').then(Boolean)
    )).toBe(true);

    // Analytics was never visited online; drop the whole origin now.
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    disconnected = true;

    await page.goto(`${origin}/analytics.html`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    await expect(page).toHaveTitle(/出題趨勢分析/);

    // The page must carry no remote script dependency.
    expect(await page.evaluate(() => [...document.scripts]
      .filter(script => script.src && new URL(script.src).origin !== location.origin)
      .map(script => script.src))).toEqual([]);

    // The Chart global exists and every chart canvas gets a live instance.
    await expect.poll(() => page.evaluate(() =>
      typeof Chart === 'function' &&
      ['yearChart', 'donutChart', 'catChart', 'trendChart'].every(id =>
        Boolean(Chart.getChart(document.getElementById(id)))
      )
    )).toBe(true);
    expect(pageErrors).toEqual([]);
  } finally {
    await context.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
