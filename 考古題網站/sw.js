var CACHE_VERSION = 'v2.0.0';
var CORE_CACHE = 'core-' + CACHE_VERSION;
var FONT_CACHE = 'fonts-' + CACHE_VERSION;
var CDN_CACHE = 'cdn-' + CACHE_VERSION;
var DYNAMIC_CACHE = 'dynamic-' + CACHE_VERSION;

var CORE_ASSETS = [
  './',
  './index.html',
  './practice.html',
  './quiz.html',
  './search.html',
  './analytics.html',
  './analytics-chart.js',
  './analytics-chart-data.js',
  './data/home-stats.json',
  './css/style.css',
  './js/app.js',
  './js/answer-utils.js',
  './js/search-engine.js',
  './js/quiz-engine.js',
  './js/pdf-export.js',
  './manifest.json',
  './icons/icon-192.svg',
  './icons/icon-512.svg'
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CORE_CACHE)
      .then(function(cache) { return cache.addAll(CORE_ASSETS); })
      .then(function() { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function(event) {
  var validCaches = [CORE_CACHE, FONT_CACHE, CDN_CACHE, DYNAMIC_CACHE];
  event.waitUntil(
    caches.keys()
      .then(function(keys) {
        return Promise.all(keys.filter(function(key) {
          return validCaches.indexOf(key) === -1;
        }).map(function(key) { return caches.delete(key); }));
      })
      .then(function() { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') return;
  var url = new URL(event.request.url);

  if (url.origin === self.location.origin &&
      (url.pathname.endsWith('/data/search-index.json') ||
       url.pathname.endsWith('/data/home-stats.json') ||
       url.pathname.endsWith('/analytics-chart.js') ||
       url.pathname.endsWith('/analytics-chart-data.js'))) {
    event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
    return;
  }

  if (url.pathname.indexOf('/fonts/') !== -1 ||
      url.hostname === 'fonts.googleapis.com' ||
      url.hostname === 'fonts.gstatic.com') {
    event.respondWith(cacheFirst(event.request, FONT_CACHE));
    return;
  }

  if (url.hostname === 'cdn.jsdelivr.net') {
    event.respondWith(staleWhileRevalidate(event.request, CDN_CACHE));
    return;
  }

  if (url.origin === self.location.origin &&
      (url.pathname.endsWith('.css') || url.pathname.endsWith('.js'))) {
    event.respondWith(staleWhileRevalidate(event.request, CORE_CACHE));
    return;
  }

  if (event.request.headers.get('accept') &&
      event.request.headers.get('accept').indexOf('text/html') !== -1) {
    event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
    return;
  }

  event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
});

function cacheFirst(request, cacheName) {
  return caches.match(request).then(function(cached) {
    if (cached) return cached;
    return fetch(request).then(function(response) {
      if (response && response.ok) {
        caches.open(cacheName).then(function(cache) { cache.put(request, response.clone()); });
      }
      return response;
    });
  });
}

function networkFirst(request, cacheName) {
  return fetch(request).then(function(response) {
    if (response && response.ok) {
      caches.open(cacheName).then(function(cache) { cache.put(request, response.clone()); });
    }
    return response;
  }).catch(function() {
    return caches.match(request).then(function(cached) {
      if (cached) return cached;
      if (request.headers.get('accept') &&
          request.headers.get('accept').indexOf('text/html') !== -1) {
        return caches.match('./index.html');
      }
      return Response.error();
    });
  });
}

function staleWhileRevalidate(request, cacheName) {
  return caches.open(cacheName).then(function(cache) {
    return cache.match(request).then(function(cached) {
      var fresh = fetch(request).then(function(response) {
        if (response && response.ok) cache.put(request, response.clone());
        return response;
      }).catch(function() { return cached || Response.error(); });
      return cached || fresh;
    });
  });
}
