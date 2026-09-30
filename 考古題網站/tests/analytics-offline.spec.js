const { test, expect } = require('@playwright/test');
const http = require('node:http');
const path = require('node:path');
const serveHandler = require('serve-handler');

test('first offline Analytics visit renders charts after only visiting the homepage online', async ({ browser }) => {
  test.setTimeout(60000);
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
  const context = await browser.newContext({ serviceWorkers: 'allow' });
  const page = await context.newPage();

  try {
    await context.route(url => url.origin !== origin, route => route.abort());
    await page.goto(`${origin}/index.html`);
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    expect(await page.evaluate(async () => Boolean(
      await caches.match('./vendor/chart.js-4.4.1/chart.umd.js')
    ))).toBe(true);

    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    disconnected = true;
    await page.goto(`${origin}/analytics.html`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    await expect(page).toHaveTitle(/出題趨勢分析/);
    expect(await page.evaluate(() => [...document.scripts]
      .filter(script => script.src && new URL(script.src).origin !== location.origin)
      .map(script => script.src))).toEqual([]);
    await expect.poll(() => page.evaluate(() =>
      typeof Chart === 'function' &&
      ['yearChart', 'donutChart', 'catChart', 'trendChart'].every(id =>
        Boolean(Chart.getChart(document.getElementById(id)))
      )
    )).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    await context.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
