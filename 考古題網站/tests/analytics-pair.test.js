// Regression for the Analytics code/data version-mix bug (issue #74).
//
// The page must load chart code and generated data as ONE versioned unit.
// If the pair is fetched independently, a half-failed refresh (one network
// request succeeds while the other falls back to an older cache entry) can
// execute "new code + old data" or "old code + new data". These tests drive
// the real sw.js in a vm sandbox and fail if any path can serve a mixed pair.
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

const BUNDLE_PATH = '/analytics-chart-bundle.js';
const LEGACY_PATHS = ['/analytics-chart.js', '/analytics-chart-data.js'];

function normalizedSource(file) {
  return readFileSync(path.join(site, file), 'utf8')
    .replace(/\r\n/g, '\n')
    .replace(/\n+$/, '') + '\n';
}

// A fake "pair" whose two halves carry version labels, so the sandbox can
// detect a mixed pair the way the real page would execute one.
function makePair(version) {
  return `const TEST_DATA_VERSION = ${JSON.stringify(version)};\n` +
    `window.__analyticsPair = { data: TEST_DATA_VERSION, code: ${JSON.stringify(version)} };\n`;
}

function makeWorker(network) {
  const entries = new Map();
  const cache = {
    put: async (request, response) => {
      entries.set(request.url, response.clone());
    },
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
  const fetchResource = async pathname => {
    const resourceRequest = new Request(`${origin}${pathname}`);
    let response;
    listeners.get('fetch')({
      request: resourceRequest,
      respondWith: promise => { response = promise; },
    });
    assert.ok(response, `service worker must answer ${pathname}`);
    return response;
  };
  return {
    calls,
    seed: (pathname, body) => cache.put(
      new Request(`${origin}${pathname}`),
      new Response(body, { headers: { 'content-type': 'text/javascript' } }),
    ),
    fetchResource,
    fetchBundle: () => fetchResource(BUNDLE_PATH),
  };
}

// Executing the served response the way the page would run the script tags.
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

  const bundlePath = path.join(site, 'analytics-chart-bundle.js');
  assert.ok(existsSync(bundlePath), 'analytics-chart-bundle.js must exist');
  const bundle = readFileSync(bundlePath, 'utf8').replace(/\r\n/g, '\n');
  const marker = /^\/\* Generated Analytics code\/data pair SHA-256: ([a-f0-9]{64}) \*\/\n/;
  const match = marker.exec(bundle);
  assert.ok(match, 'generated pair digest marker is missing');
  const pair = normalizedSource('analytics-chart-data.js') +
    normalizedSource('analytics-chart.js');
  assert.equal(bundle.slice(match[0].length), pair);
  assert.equal(match[1], createHash('sha256').update(pair).digest('hex'));
});

// Issue scenario, both directions: with a stale pair in cache, one source
// fetch succeeding while the other fails must not produce a mixed pair.
// The worker owns the pair as a single bundle request, so either half
// failing resolves to the complete cached pair.
for (const failed of ['data', 'code']) {
  test(`${failed} fetch failure falls back to the complete cached pair`, async () => {
    const bundleUrl = `${origin}${BUNDLE_PATH}`;
    const fixture = makeWorker(request => {
      assert.equal(request.url, bundleUrl);
      return Promise.reject(new Error(`${failed} source failed`));
    });
    await fixture.seed(BUNDLE_PATH, makePair('old'));

    assert.deepEqual(await executedPair(await fixture.fetchBundle()), {
      data: 'old',
      code: 'old',
    });
    assert.deepEqual(fixture.calls, [bundleUrl]);
  });
}

test('legacy split code/data requests fail closed even with a stale cached pair', async () => {
  // Old cached pages still request the two files independently. Fulfilling
  // either request (from network or cache) could pair mismatched versions,
  // so the worker must fail both closed without hitting the network.
  const fixture = makeWorker(() => new Response(makePair('new')));
  await fixture.seed(LEGACY_PATHS[0], makePair('stale'));
  await fixture.seed(LEGACY_PATHS[1], makePair('stale'));
  for (const resource of LEGACY_PATHS) {
    const response = await fixture.fetchResource(resource);
    assert.equal(response.ok, false, `${resource} must fail closed`);
  }
  assert.deepEqual(fixture.calls, []);
});

test('asymmetric split-fetch results never reach the page as a mixed pair', async () => {
  for (const succeeding of LEGACY_PATHS) {
    const fixture = makeWorker(request => request.url.endsWith(succeeding)
      ? new Response(makePair('new'))
      : Promise.reject(new Error('offline')));
    const responses = [];
    for (const resource of LEGACY_PATHS) {
      responses.push(await fixture.fetchResource(resource));
    }
    // Either both halves fail closed (no pair runs) or — never — a pair of
    // different versions may be served.
    assert.ok(responses.every(r => !r.ok),
      `mixed pair reachable when only ${succeeding} succeeds`);
  }
});

test('a complete new pair replaces the old cached pair atomically', async () => {
  let online = true;
  const fixture = makeWorker(() => online
    ? new Response(makePair('new'), { headers: { 'content-type': 'text/javascript' } })
    : Promise.reject(new Error('offline')));
  await fixture.seed(BUNDLE_PATH, makePair('old'));

  assert.deepEqual(await executedPair(await fixture.fetchBundle()), {
    data: 'new',
    code: 'new',
  });
  online = false;
  assert.deepEqual(await executedPair(await fixture.fetchBundle()), {
    data: 'new',
    code: 'new',
  });
});

test('without a cached pair a failed request fails closed', async () => {
  const fixture = makeWorker(() => Promise.reject(new Error('offline')));
  const response = await fixture.fetchBundle();
  assert.equal(response.ok, false);
});

test('a non-ok bundle response does not evict the cached pair', async () => {
  const fixture = makeWorker(() => new Response('server error', { status: 503 }));
  await fixture.seed(BUNDLE_PATH, makePair('old'));
  assert.deepEqual(await executedPair(await fixture.fetchBundle()), {
    data: 'old',
    code: 'old',
  });
});
