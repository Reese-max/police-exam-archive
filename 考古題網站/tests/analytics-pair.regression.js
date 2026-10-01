// Regression for the Analytics chart code/data version-mix bug (issue #74).
//
// The service worker used to fetch analytics-chart.js and
// analytics-chart-data.js with two independent networkFirst() calls, so one
// half-failed refresh could execute "new code + old data" (or the reverse).
// The pair must now travel as one generated, hash-marked bundle: the worker
// serves a complete fresh pair or a complete cached pair, and never a mix.
//
// The tests drive the real sw.js inside a vm sandbox with fake cache storage
// and a scriptable network, so every case is deterministic and offline. The
// pair bodies below label their two halves independently, so a response that
// mixed a network half with a cached half would show up as two different
// labels — that is the defect this file guards against.
//
// Residual exposure, by design: a client still running the pre-fix worker
// keeps the old split behaviour until its own update check replaces sw.js.
// The CACHE_VERSION bump plus skipWaiting/clients.claim are the standard
// mitigation for that window; the repo cannot force it from here.
'use strict';

const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { existsSync, readFileSync, readdirSync, statSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const SITE = path.join(__dirname, '..');
const ORIGIN = 'https://police-exam-archive.test';
const BUNDLE_PATH = '/analytics-chart-bundle.js';
const BUNDLE_ASSET = './analytics-chart-bundle.js';
const BUNDLE_URL = ORIGIN + BUNDLE_PATH;
const LEGACY_PATHS = ['/analytics-chart.js', '/analytics-chart-data.js'];
const LEGACY_SOURCES = LEGACY_PATHS.map(legacy => legacy.slice(1));
const JS_HEADERS = { 'content-type': 'text/javascript' };

const html = readFileSync(path.join(SITE, 'analytics.html'), 'utf8');
const workerSource = readFileSync(path.join(SITE, 'sw.js'), 'utf8');

function sourceText(file) {
  return readFileSync(path.join(SITE, file), 'utf8')
    .replace(/\r\n/g, '\n')
    .replace(/\n+$/, '') + '\n';
}

// A pair body whose two halves are labelled separately, so "data from the
// network, code from the cache" stays detectable.
function pairBody(dataLabel, codeLabel) {
  return 'const TEST_DATA_LABEL = ' + JSON.stringify(dataLabel) + ';\n' +
    'const TEST_CODE_LABEL = ' + JSON.stringify(codeLabel) + ';\n' +
    'window.__executedPair = { data: TEST_DATA_LABEL, code: TEST_CODE_LABEL };\n';
}

const NETWORK_PAIR = pairBody('network-data', 'network-code');
const INSTALLED_PAIR = pairBody('installed-data', 'installed-code');
const CACHED_PAIR = pairBody('cached-data', 'cached-code');

async function executedPair(response) {
  assert.equal(response.ok, true, 'pair response must be usable');
  const page = { window: {} };
  vm.runInNewContext(await response.text(), page);
  // Copy out of the sandbox realm so comparisons stay plain-object strict.
  return JSON.parse(JSON.stringify(page.window.__executedPair));
}

// Offline unless flipped: every core asset 200s while online.
function onlineNetwork(online) {
  return url => {
    if (!online()) return Promise.reject(new Error('offline'));
    if (url === BUNDLE_URL) return new Response(NETWORK_PAIR, { headers: JS_HEADERS });
    return new Response('/* asset */\n', { headers: JS_HEADERS });
  };
}

function siteFiles(extension) {
  const found = [];
  const walk = dir => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry === 'test-results') continue;
      const full = path.join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith(extension)) found.push(full);
    }
  };
  walk(SITE);
  return found;
}

function startWorker(network) {
  // CacheStorage stores bytes, so entries are kept as bodies and rebuilt into
  // a fresh Response on every read — a cache hit must be readable repeatedly.
  const stores = new Map();
  const networkCalls = [];
  const precached = [];
  const openedCaches = [];
  let precachedSet = new Set();
  let putBehaviour = () => Promise.resolve();
  let lookupBehaviour = () => Promise.resolve();
  let precache = url => Promise.resolve(url === BUNDLE_URL
    ? new Response(INSTALLED_PAIR, { headers: JS_HEADERS })
    : new Response('/* asset */\n', { headers: JS_HEADERS }));

  const urlOf = request =>
    new URL(String(request.url === undefined ? request : request.url)).href;
  const storeFor = name => {
    if (!stores.has(name)) stores.set(name, new Map());
    return stores.get(name);
  };
  const read = (store, request) => {
    const body = store.get(urlOf(request));
    return body === undefined ? undefined : new Response(body, { headers: JS_HEADERS });
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
            await putBehaviour();
            store.set(urlOf(request), await response.text());
          },
          async match(request) {
            return read(store, request);
          },
          async addAll(urls) {
            // Real Cache.addAll fetches every asset first and rejects the whole
            // install when any single response is not ok, so a failed
            // pre-cache must not leave a half-populated cache behind. Install
            // happened while the client was online, hence its own fetches.
            const fetched = [];
            for (const url of urls) {
              const response = await precache(new URL(url, ORIGIN + '/').href);
              if (!response || !response.ok) throw new Error('pre-cache failed: ' + url);
              fetched.push([new URL(url, ORIGIN + '/').href, await response.text()]);
            }
            for (const [href, body] of fetched) store.set(href, body);
            precached.push(...urls);
            precachedSet = new Set(urls);
          }
        };
      },
      async match(request, options) {
        await lookupBehaviour();
        const names = options && options.cacheName
          ? [options.cacheName]
          : [...stores.keys()];
        for (const name of names) {
          const store = stores.get(name);
          const hit = store ? read(store, request) : undefined;
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
    fetch: async (request, init) => {
      const url = urlOf(request);
      networkCalls.push({ url, init });
      return network(url, init);
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
    get lastPrecached() {
      return precachedSet;
    },
    /* Runs install() so the pre-cache model is exercised, then forgets the
       install-time network traffic for the per-request assertions. */
    async install() {
      let waited;
      listeners.get('install')({ waitUntil(value) { waited = value; } });
      assert.ok(waited, 'install handler must waitUntil()');
      await waited;
      const pairAssets = precached.filter(asset => asset.includes('analytics-chart'));
      networkCalls.length = 0;
      return pairAssets;
    },
    coreCache() {
      assert.ok(openedCaches.length > 0, 'the worker must open a cache first');
      return openedCaches[0];
    },
    /* Runs activate(): stale cache names must go, the current ones must stay. */
    async activate() {
      let waited;
      listeners.get('activate')({ waitUntil(value) { waited = value; } });
      assert.ok(waited, 'activate handler must waitUntil()');
      await waited;
      return [...stores.keys()];
    },
    /* CacheStorage failure modes a real browser can hit (quota, eviction). */
    failCacheWrites(error) {
      putBehaviour = () => Promise.reject(error);
    },
    holdCacheWrites() {
      let release;
      putBehaviour = () => new Promise(resolve => { release = resolve; });
      return () => release();
    },
    failCacheLookups(error) {
      lookupBehaviour = () => Promise.reject(error);
    },
    /* What a first deploy looks like when an asset is missing or 5xx. */
    failPrecache() {
      precache = () => Promise.resolve(new Response('unavailable', { status: 503 }));
    },
    seed(cacheName, pathname, body) {
      storeFor(cacheName).set(ORIGIN + pathname, body);
    },
    cachedBodies() {
      const bodies = {};
      for (const store of stores.values()) {
        for (const [href, body] of store) bodies[href] = body;
      }
      return bodies;
    },
    bodiesIn(cacheName) {
      return Object.fromEntries(stores.get(cacheName) || []);
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
  assert.deepEqual(pairScripts, [BUNDLE_ASSET.slice(2)]);
});

test('no page loads either half of the pair on its own', () => {
  const offenders = siteFiles('.html')
    .filter(file => LEGACY_SOURCES.some(legacy => readFileSync(file, 'utf8').includes(legacy)))
    .map(file => path.relative(SITE, file));
  assert.deepEqual(offenders, []);
});

test('the generated bundle is exactly the current code and data, marked with their digest', () => {
  const bundlePath = path.join(SITE, 'analytics-chart-bundle.js');
  assert.ok(existsSync(bundlePath), 'analytics-chart-bundle.js must be generated');
  const bundle = readFileSync(bundlePath, 'utf8').replace(/\r\n/g, '\n');
  const marker = /^\/\* Generated Analytics code\/data pair（自動產生，勿手改）SHA-256: ([0-9a-f]{64}) \*\/\n/;
  const marked = marker.exec(bundle);
  assert.ok(marked, 'the bundle must carry the pair digest marker');
  const pair = sourceText('analytics-chart-data.js') + sourceText('analytics-chart.js');
  assert.equal(bundle.slice(marked[0].length), pair,
    'the bundle must be data + chart code, byte for byte');
  assert.equal(marked[1], createHash('sha256').update(pair).digest('hex'));
});

test('the bundle parses as one script, so a future redeclaration cannot brick Analytics', () => {
  const bundle = readFileSync(path.join(SITE, 'analytics-chart-bundle.js'), 'utf8');
  assert.doesNotThrow(() => new vm.Script(bundle, { filename: 'analytics-chart-bundle.js' }),
    'data + chart code share one lexical scope and must not redeclare a binding');
});

test('install precaches the Analytics page and the pair, never a half', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  const precached = await worker.install();
  assert.deepEqual(precached, [BUNDLE_ASSET]);
  assert.equal(
    worker.lastPrecached.has('./analytics.html'), true,
    'the page that loads the pair must itself be pre-cached for offline use'
  );
  for (const legacy of LEGACY_SOURCES) {
    assert.equal(worker.lastPrecached.has(legacy), false,
      legacy + ' must not be pre-cached: a cached half can pair with a network half');
  }
});

test('activate drops the caches of older revisions and keeps the current one', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  await worker.install();
  const revision = worker.coreCache().replace(/^core-/, '');
  worker.seed('core-' + revision, '/index.html', '/* current revision */');
  worker.seed('dynamic-' + revision, '/index.html', '/* current revision */');
  worker.seed('core-v1.6.0', BUNDLE_PATH, CACHED_PAIR);
  worker.seed('dynamic-v1.6.0', '/index.html', '/* old revision */');

  // Evicting the previous revision is what removes its cached chart halves.
  assert.deepEqual((await worker.activate()).sort(),
    ['core-' + revision, 'dynamic-' + revision].sort());
  assert.deepEqual(worker.bodiesIn('core-v1.6.0'), {},
    'a previous revision must not keep serving the chart pair after the update');
  assert.deepEqual(worker.bodiesIn('dynamic-v1.6.0'), {});
  assert.equal(worker.bodiesIn('dynamic-' + revision)[ORIGIN + '/index.html'],
    '/* current revision */');
});

test('install rejects instead of half-populating the cache when pre-caching fails', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  worker.failPrecache();

  await assert.rejects(worker.install(), /pre-cache failed/);
  assert.deepEqual(await worker.cachedBodies(), {});
});

test('the pair pre-cached by install alone satisfies the offline fallback', async () => {
  const worker = startWorker(() => Promise.reject(new Error('offline')));
  await worker.install();

  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'installed-data',
    code: 'installed-code'
  });
});

// The pair is a single request now, so "one half fetched, one half cached" is
// no longer representable: the fallback below returns the whole cached pair,
// and the legacy-route tests below keep proving the split request closed.
test('a failed refresh serves the complete cached pair and leaves the cache alone', async () => {
  const worker = startWorker(() => Promise.reject(new Error('network unavailable')));
  await worker.install();
  assert.match(worker.coreCache(), /^core-/);
  await worker.seed(worker.coreCache(), BUNDLE_PATH, CACHED_PAIR);
  const before = await worker.cachedBodies();

  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'cached-data',
    code: 'cached-code'
  });
  assert.deepEqual(worker.networkCalls.map(call => call.url), [BUNDLE_URL],
    'the pair must move in exactly one network request');
  assert.deepEqual(await worker.cachedBodies(), before,
    'a failed refresh must leave the cached pair untouched');
});

test('the pair refresh bypasses the HTTP cache so the newest pair wins', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  await worker.install();
  await worker.bundle();

  const pairCalls = worker.networkCalls.filter(call => call.url === BUNDLE_URL);
  assert.equal(pairCalls.length, 1);
  assert.equal(pairCalls[0].init && pairCalls[0].init.cache, 'no-store');
});

test('a fresh complete pair replaces the cached pair in one step', async () => {
  let online = true;
  const worker = startWorker(onlineNetwork(() => online));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, CACHED_PAIR);

  // Online the page must not start from the cached copy.
  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'network-data',
    code: 'network-code'
  });
  online = false;
  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'network-data',
    code: 'network-code'
  });
});

test('the fresh pair is only served after its cache write settles', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  await worker.install();
  const release = worker.holdCacheWrites();

  const served = worker.bundle();
  let settled = false;
  served.then(() => { settled = true; });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(settled, false,
    'the response must wait for the cache write, or a crash could keep an older pair');

  release();
  assert.deepEqual(await executedPair(await served), {
    data: 'network-data',
    code: 'network-code'
  });
});

test('a cache write failure still serves the fresh pair and keeps the cached pair', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, CACHED_PAIR);
  worker.failCacheWrites(new Error('quota exceeded'));

  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'network-data',
    code: 'network-code'
  });
  assert.equal((await worker.cachedBodies())[BUNDLE_URL], CACHED_PAIR);
});

test('a 200 that is not JavaScript never becomes the cached pair', async () => {
  const worker = startWorker(() => new Response('<!doctype html><h1>Not found</h1>', {
    status: 200,
    headers: { 'content-type': 'text/html' }
  }));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, CACHED_PAIR);

  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'cached-data',
    code: 'cached-code'
  });
  assert.equal((await worker.cachedBodies())[BUNDLE_URL], CACHED_PAIR,
    'an error page must not overwrite the known complete pair');
});

test('an error response never replaces the cached pair', async () => {
  const worker = startWorker(() => new Response('upstream error', { status: 503 }));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, CACHED_PAIR);

  assert.deepEqual(await executedPair(await worker.bundle()), {
    data: 'cached-data',
    code: 'cached-code'
  });
});

test('with no cached pair a failed refresh fails closed', async () => {
  // No install(): the client never pre-cached the pair, so nothing is known
  // to be a consistent code/data version.
  const worker = startWorker(() => Promise.reject(new Error('offline')));

  assert.equal((await worker.bundle()).ok, false);
});

test('the offline fallback trusts only the versioned core cache', async () => {
  const worker = startWorker(() => Promise.reject(new Error('offline')));
  worker.seed('dynamic-not-a-pair-store', BUNDLE_PATH, CACHED_PAIR);

  assert.equal((await worker.bundle()).ok, false);
});

test('a cache lookup failure fails closed instead of answering a broken pair', async () => {
  const worker = startWorker(() => Promise.reject(new Error('offline')));
  await worker.install();
  await worker.seed(worker.coreCache(), BUNDLE_PATH, CACHED_PAIR);
  worker.failCacheLookups(new Error('cache storage unavailable'));

  assert.equal((await worker.bundle()).ok, false);
});

// Cached pages may still ask for the two halves separately, and the legacy
// routes are where a mixed pair could come back: one half answered from the
// network while the other comes from an older cache entry.
test('legacy split requests fail closed even with a stale pair cached', async () => {
  const worker = startWorker(onlineNetwork(() => true));
  await worker.install();
  for (const legacy of LEGACY_PATHS) {
    await worker.seed(worker.coreCache(), legacy, CACHED_PAIR);
  }

  for (const legacy of LEGACY_PATHS) {
    assert.equal((await worker.legacy(legacy)).ok, false, legacy + ' must fail closed');
  }
  assert.deepEqual(worker.networkCalls, []);
});

test('one legacy half succeeding cannot compose a pair', async () => {
  for (const succeeding of LEGACY_PATHS) {
    const worker = startWorker(url => url.endsWith(succeeding)
      ? new Response(NETWORK_PAIR, { headers: JS_HEADERS })
      : Promise.reject(new Error('offline')));
    await worker.install();
    for (const legacy of LEGACY_PATHS) {
      await worker.seed(worker.coreCache(), legacy, CACHED_PAIR);
    }

    const served = [];
    for (const legacy of LEGACY_PATHS) served.push(await worker.legacy(legacy));
    assert.ok(served.every(response => !response.ok),
      `a mixed pair is reachable when only ${succeeding} succeeds`);
  }
});
