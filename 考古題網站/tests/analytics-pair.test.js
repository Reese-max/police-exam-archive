const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const site = path.join(__dirname, '..');
const origin = 'https://exam.example.test';
const html = readFileSync(path.join(site, 'analytics.html'), 'utf8');
const worker = readFileSync(path.join(site, 'sw.js'), 'utf8');
const bundle = readFileSync(path.join(site, 'analytics-chart-bundle.js'), 'utf8').replace(/\r\n/g, '\n');

function normalizedSource(file) {
  return readFileSync(path.join(site, file), 'utf8').replace(/\r\n/g, '\n').replace(/\n+$/, '') + '\n';
}

function makePair(version) {
  return `const TEST_DATA_VERSION = ${JSON.stringify(version)};\n` +
    `window.__analyticsPair = { data: TEST_DATA_VERSION, code: ${JSON.stringify(version)} };\n`;
}

function makeWorker(network) {
  const entries = new Map();
  const cache = {
    put: async (request, response) => { entries.set(request.url, response.clone()); },
    match: async request => entries.get(request.url)?.clone(),
  };
  const listeners = new Map();
  const calls = [];
  const sandbox = {
    URL, Response,
    self: {
      location: { origin },
      addEventListener: (name, handler) => listeners.set(name, handler),
    },
    caches: {
      open: async () => cache,
      match: async request => cache.match(request),
    },
    fetch: async request => {
      calls.push(request.url);
      return network(request);
    },
  };
  vm.runInNewContext(worker, sandbox, { filename: 'sw.js' });
  const request = new Request(`${origin}/analytics-chart-bundle.js`);
  async function dispatch(request) {
    let response;
    listeners.get('fetch')({ request, respondWith: promise => { response = promise; } });
    assert.ok(response, 'service worker must own the Analytics asset request');
    return response;
  }
  return {
    calls,
    seed: async (body, url = request.url) => cache.put(new Request(url),
      new Response(body, { headers: { 'content-type': 'text/javascript' } })),
    fetchAsset: pathname => dispatch(new Request(`${origin}${pathname}`)),
    fetchBundle: () => dispatch(request),
  };
}

async function executedPair(response) {
  assert.equal(response.ok, true);
  const page = { window: {} };
  vm.runInNewContext(await response.text(), page);
  return page.window.__analyticsPair;
}

test('the generated single response has a reproducible code/data identity', () => {
  const scripts = [...html.matchAll(/<script\s+src="([^"]+)"/g)]
    .map(match => match[1]).filter(src => src.includes('analytics-chart'));
  assert.deepEqual(scripts, ['analytics-chart-bundle.js']);
  const marker = /^\/\* Generated Analytics code\/data pair SHA-256: ([a-f0-9]{64}) \*\/\n/;
  const match = marker.exec(bundle);
  assert.ok(match, 'generated pair digest is missing');
  const pair = normalizedSource('analytics-chart-data.js') + normalizedSource('analytics-chart.js');
  assert.equal(bundle.slice(match[0].length), pair);
  assert.equal(match[1], createHash('sha256').update(pair).digest('hex'));
});

for (const failed of ['data', 'code']) {
  test(`an old complete pair survives when the ${failed} endpoint fails during a split rollout`, async () => {
    const bundleUrl = `${origin}/analytics-chart-bundle.js`;
    const failedUrl = `${origin}/${failed === 'data' ? 'analytics-chart-data.js' : 'analytics-chart.js'}`;
    const succeededUrl = `${origin}/${failed === 'data' ? 'analytics-chart.js' : 'analytics-chart-data.js'}`;
    const network = request => {
      if (request.url === bundleUrl) {
        return failed === 'data'
          ? Promise.reject(new Error('partial network failure'))
          : new Response('unavailable', { status: 503 });
      }
      if (request.url === failedUrl) throw new Error('individual asset failed');
      return new Response(makePair('new'));
    };
    assert.equal((await network(new Request(succeededUrl))).ok, true);
    assert.throws(() => network(new Request(failedUrl)), /individual asset failed/);
    const workerFixture = makeWorker(network);
    await workerFixture.seed(makePair('old'));
    assert.equal(JSON.stringify(await executedPair(await workerFixture.fetchBundle())),
      JSON.stringify({ data: 'old', code: 'old' }));
    assert.deepEqual(workerFixture.calls, [bundleUrl]);
  });
}

test('a complete new pair replaces the old cached pair as one response', async () => {
  let online = true;
  const workerFixture = makeWorker(() => online
    ? new Response(makePair('new'), { headers: { 'content-type': 'text/javascript' } })
    : Promise.reject(new Error('offline')));
  await workerFixture.seed(makePair('old'));
  assert.equal(JSON.stringify(await executedPair(await workerFixture.fetchBundle())),
    JSON.stringify({ data: 'new', code: 'new' }));
  online = false;
  assert.equal(JSON.stringify(await executedPair(await workerFixture.fetchBundle())),
    JSON.stringify({ data: 'new', code: 'new' }));
});

for (const legacyPath of ['/analytics-chart.js', '/analytics-chart-data.js']) {
  test(`legacy standalone asset ${legacyPath} fails closed even when cached`, async () => {
    const workerFixture = makeWorker(() => {
      throw new Error('legacy asset must not reach the network');
    });
    await workerFixture.seed(makePair('stale'), `${origin}${legacyPath}`);
    const response = await workerFixture.fetchAsset(legacyPath);
    assert.equal(response.type, 'error');
    assert.deepEqual(workerFixture.calls, []);
  });
}

test('without a known pair, a failed bundle request cannot execute either half', async () => {
  const workerFixture = makeWorker(() => Promise.reject(new Error('offline')));
  const response = await workerFixture.fetchBundle();
  assert.equal(response.ok, false);
});
