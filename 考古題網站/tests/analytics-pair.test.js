// Regression for the Analytics chart code/data version-mix bug (issue #74).
//
// The service worker used to fetch analytics-chart.js and
// analytics-chart-data.js with two independent networkFirst() calls, so one
// half-failed refresh could execute "new code + old data" (or the reverse).
// The pair must now travel as one generated, hash-marked bundle: the worker
// serves a complete fresh pair or a complete cached pair, and never a mix.
//
// The tests drive the real sw.js inside a vm sandbox with fake cache storage
// and a scriptable network, so every case is deterministic and offline.
'use strict';

const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const SITE = path.join(__dirname, '..');
const ORIGIN = 'https://police-exam-archive.test';
const BUNDLE_PATH = '/analytics-chart-bundle.js';
const LEGACY_PATHS = ['/analytics-chart.js', '/analytics-chart-data.js'];
const JS_HEADERS = { 'content-type': 'text/javascript' };

const html = readFileSync(path.join(SITE, 'analytics.html'), 'utf8');
const workerSource = readFileSync(path.join(SITE, 'sw.js'), 'utf8');

function sourceText(file) {
  return readFileSync(path.join(SITE, file), 'utf8')
    .replace(/\r\n/g, '\n')
    .replace(/\n+$/, '') + '\n';
}

// Stand-in pair whose two halves carry the same version label, so executing
// what the worker served tells a complete pair apart from a mixed one.
function pairWithVersion(version) {
  return 'const TEST_PAIR_VERSION = ' + JSON.stringify(version) + ';\n' +
    'window.__executedPair = { data: TEST_PAIR_VERSION, code: ' +
    JSON.stringify(version) + ' };\n';
}

async function executedPair(response) {
  assert.equal(response.ok, true, 'pair response must be usable');
  const page = { window: {} };
  vm.runInNewContext(await response.text(), page);
  // Copy out of the sandbox realm so comparisons stay plain-object strict.
  return JSON.parse(JSON.stringify(page.window.__executedPair));
}

function startWorker(network) {
  const stores = new Map();
  const networkCalls = [];
  const precached = [];
  const openedCaches = [];

  const storeFor = name => {
    if (!stores.has(name)) stores.set(name, new Map());
    return stores.get(name);
  };
  const lookup = (store, request) => {
    const hit = store.get(new URL(request.url).href);
    return hit ? hit.clone() : undefined;
  };

  const listeners = new Map();
  const sandbox = {
    URL,
    Request,
    Response,
    console,
    self: {
      location: { origin: ORIGIN },
      clients: { claim: async () => undefined },
      skipWaiting: async () => undefined,
      addEventListener: (type, handler) => listeners.set(type, handler)
    },
    caches: {
      async open(name) {
        openedCaches.push(name);
        const store = storeFor(name);
        return {
          async put(request, response) {
            store.set(new URL(request.url).href, response.clone());
          },
          async match(request) {
            return lookup(store, request);
          },
          async addAll(urls) {
            precached.push(...urls);
          }
        };
      },
      async match(request, options) {
        const names = options && options.cacheName
          ? [options.cacheName]
          : [...stores.keys()];
        for (const name of names) {
          const store = stores.get(name);
          const hit = store ? lookup(store, request) : undefined;
          if (hit) return hit;
        }
        return undefined;
      },
      async keys() {
        return [...stores.keys()];
      },
      async delete(name) {
        return stores.delete(name);
      }
    },
    fetch: async request => {
      const url = String(request.url === undefined ? request : request.url);
      networkCalls.push(url);
      return network(url);
    }
  };
  vm.runInNewContext(workerSource, sandbox, { filename: 'sw.js' });

  const respond = async pathname => {
    let answered;
    listeners.get('fetch')({
      request: new Request(ORIGIN + pathname),
      respondWith(value) { answered = value; }
    });
    assert.ok(answered, 'the service worker must answer ' + pathname);
    return await answered;
  };

  return {
    networkCalls,
    openedCaches,
    async install() {
      let waited;
      listeners.get('install')({ waitUntil(value) { waited = value; } });
      assert.ok(waited, 'install handler must waitUntil()');
      await waited;
      return precached.filter(asset => asset.includes('analytics-chart'));
    },
    coreCache() {
      assert.ok(openedCaches.length > 0, 'the worker must open a cache first');
      return openedCaches[0];
    },
    async seed(cacheName, pathname, body) {
      storeFor(cacheName).set(
        ORIGIN + pathname,
        new Response(body, { headers: JS_HEADERS })
      );
    },
    bundle() {
      return respond(BUNDLE_PATH);
    },
    legacy(pathname) {
      return respond(pathname);
    }
  };
}

test('the Analytics page requests the code/data pair as one script', () => {
  const pairScripts = [...html.matchAll(/<script[^>]*\ssrc="([^"]+)"/g)]
    .map(match => match[1])
    .filter(src => src.includes('analytics-chart'));
  assert.deepEqual(pairScripts, ['analytics-chart-bundle.js']);
});

test('the generated bundle is exactly the current code and data, marked with their digest', () => {
  const bundlePath = path.join(SITE, 'analytics-chart-bundle.js');
  assert.ok(existsSync(bundlePath), 'analytics-chart-bundle.js must be generated');
  const bundle = readFileSync(bundlePath, 'utf8').replace(/\r\n/g, '\n');
  const marker = /^\/\* Generated Analytics code\/data pair SHA-256: ([0-9a-f]{64}) \*\/\n/;
  const marked = marker.exec(bundle);
  assert.ok(marked, 'the bundle must carry the pair digest marker');
  const pair = sourceText('analytics-chart-data.js') + sourceText('analytics-chart.js');
  assert.equal(bundle.slice(marked[0].length), pair,
    'the bundle must be data + chart code, byte for byte');
  assert.equal(marked[1], createHash('sha256').update(pair).digest('hex'));
});

test('install precaches the pair as a single asset', async () => {
  const worker = startWorker(() => Promise.reject(new Error('install must not fetch')));
  const pairAssets = await worker.install();
  assert.deepEqual(pairAssets, ['./analytics-chart-bundle.js']);
});

// The issue scenario, both directions: a stale complete pair is already
// cached and the refresh cannot complete. Whatever the page executes must be
// one known-consistent version, and the pair must move in a single request.
for (const unavailable of ['data', 'code']) {
  test(`a half-failed refresh (${unavailable} unavailable) serves the complete cached pair`, async () => {
    const worker = startWorker(() => Promise.reject(new Error(`${unavailable} unavailable`)));
    await worker.install();
    assert.match(worker.coreCache(), /^core-/);
    await worker.seed(worker.coreCache(), BUNDLE_PATH, pairWithVersion('cached'));

    assert.deepEqual(await executedPair(await worker.bundle()), {
      data: 'cached',
      code: 'cached'
    });
    assert.deepEqual(worker.networkCalls, [ORIGIN + BUNDLE_PATH],
      'the pair must move in exactly one network request');
  });
}

test('a fresh complete pair replaces the cached pair in one step', async () => {
  let online = true;
  const worker = startWorker(() => online
    ? new Response(pairWithVersion('fresh'), { headers: JS_HEADERS })
    : Promise.reject(new Error('offline')));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, pairWithVersion('cached'));

  // Online the page must not start from the cached copy.
  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'fresh',
    code: 'fresh'
  });
  online = false;
  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'fresh',
    code: 'fresh'
  });
});

test('an error response never replaces the cached pair', async () => {
  const worker = startWorker(() => new Response('upstream error', { status: 503 }));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, pairWithVersion('cached'));

  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'cached',
    code: 'cached'
  });
});

test('with no cached pair a failed refresh fails closed', async () => {
  const worker = startWorker(() => Promise.reject(new Error('offline')));
  await worker.install();

  assert.equal((await worker.bundle()).ok, false);
});

test('the offline fallback trusts only the versioned core cache', async () => {
  const worker = startWorker(() => Promise.reject(new Error('offline')));
  await worker.install();
  await worker.seed('dynamic-not-a-pair-store', BUNDLE_PATH, pairWithVersion('stray'));

  assert.equal((await worker.bundle()).ok, false);
});

// Cached pages still ask for the two halves separately. Answering either one
// from network or cache could pair mismatched versions, so both must fail
// closed without touching the network.
test('legacy split requests fail closed even with a stale pair cached', async () => {
  const worker = startWorker(() => new Response(pairWithVersion('fresh'), { headers: JS_HEADERS }));
  await worker.install();
  for (const legacy of LEGACY_PATHS) {
    await worker.seed(worker.coreCache(), legacy, pairWithVersion('stale'));
  }

  for (const legacy of LEGACY_PATHS) {
    assert.equal((await worker.legacy(legacy)).ok, false,
      legacy + ' must fail closed');
  }
  assert.deepEqual(worker.networkCalls, []);
});

test('one legacy half succeeding cannot compose a pair', async () => {
  for (const succeeding of LEGACY_PATHS) {
    const worker = startWorker(url => url.endsWith(succeeding)
      ? new Response(pairWithVersion('fresh'), { headers: JS_HEADERS })
      : Promise.reject(new Error('offline')));
    await worker.install();
    for (const legacy of LEGACY_PATHS) {
      await worker.seed(worker.coreCache(), legacy, pairWithVersion('stale'));
    }

    const served = [];
    for (const legacy of LEGACY_PATHS) served.push(await worker.legacy(legacy));
    assert.ok(served.every(response => !response.ok),
      `a mixed pair is reachable when only ${succeeding} succeeds`);
  }
});