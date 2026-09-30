const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const site = path.join(__dirname, '..');
const origin = 'https://exam.example.test';
const html = readFileSync(path.join(site, 'analytics.html'), 'utf8');
const worker = readFileSync(path.join(site, 'sw.js'), 'utf8');

function normalizedSource(file) {
  return readFileSync(path.join(site, file), 'utf8')
    .replace(/\r\n/g, '\n')
    .replace(/\n+$/, '') + '\n';
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
    URL,
    Request,
    Response,
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
  const fetchResource = async pathname => {
    const resourceRequest = new Request(`${origin}${pathname}`);
    let response;
    listeners.get('fetch')({
      request: resourceRequest,
      respondWith: promise => { response = promise; },
    });
    assert.ok(response, 'service worker must own the Analytics pair request');
    return response;
  };
  return {
    calls,
    seed: async body => cache.put(request, new Response(body, {
      headers: { 'content-type': 'text/javascript' },
    })),
    fetchResource,
    fetchBundle: () => fetchResource('/analytics-chart-bundle.js'),
  };
}

async function executedPair(response) {
  assert.equal(response.ok, true);
  const page = { window: {} };
  vm.runInNewContext(await response.text(), page);
  return JSON.parse(JSON.stringify(page.window.__analyticsPair));
}

test('Analytics loads code and data through one reproducible bundle', () => {
  const scripts = [...html.matchAll(/<script\s+src="([^"]+)"/g)]
    .map(match => match[1])
    .filter(src => src.includes('analytics-chart'));
  assert.deepEqual(scripts, ['analytics-chart-bundle.js']);

  assert.ok(existsSync(path.join(site, 'analytics-chart-bundle.js')));
  const bundle = readFileSync(path.join(site, 'analytics-chart-bundle.js'), 'utf8')
    .replace(/\r\n/g, '\n');
  const marker = /^\/\* Generated Analytics code\/data pair SHA-256: ([a-f0-9]{64}) \*\/\n/;
  const match = marker.exec(bundle);
  assert.ok(match, 'generated pair digest is missing');
  const pair = normalizedSource('analytics-chart-data.js') + normalizedSource('analytics-chart.js');
  assert.equal(bundle.slice(match[0].length), pair);
  assert.equal(match[1], createHash('sha256').update(pair).digest('hex'));
});

for (const failed of ['data', 'code']) {
  test(`a ${failed} source failure falls back to the complete cached pair`, async () => {
    const bundleUrl = `${origin}/analytics-chart-bundle.js`;
    const workerFixture = makeWorker(request => {
      assert.equal(request.url, bundleUrl);
      return Promise.reject(new Error(`${failed} source failed`));
    });
    await workerFixture.seed(makePair('old'));

    assert.deepEqual(await executedPair(await workerFixture.fetchBundle()), {
      data: 'old',
      code: 'old',
    });
    assert.deepEqual(workerFixture.calls, [bundleUrl]);
  });
}

test('legacy independent resources fail closed instead of forming a partial pair', async () => {
  const workerFixture = makeWorker(() => new Response(makePair('new')));
  for (const resource of ['/analytics-chart.js', '/analytics-chart-data.js']) {
    const response = await workerFixture.fetchResource(resource);
    assert.equal(response.ok, false);
  }
  assert.deepEqual(workerFixture.calls, []);
});

test('a complete new pair replaces the old cached pair atomically', async () => {
  let online = true;
  const workerFixture = makeWorker(() => online
    ? new Response(makePair('new'), { headers: { 'content-type': 'text/javascript' } })
    : Promise.reject(new Error('offline')));
  await workerFixture.seed(makePair('old'));

  assert.deepEqual(await executedPair(await workerFixture.fetchBundle()), {
    data: 'new',
    code: 'new',
  });
  online = false;
  assert.deepEqual(await executedPair(await workerFixture.fetchBundle()), {
    data: 'new',
    code: 'new',
  });
});

test('without a known pair, a failed request fails closed', async () => {
  const workerFixture = makeWorker(() => Promise.reject(new Error('offline')));
  const response = await workerFixture.fetchBundle();
  assert.equal(response.ok, false);
});
