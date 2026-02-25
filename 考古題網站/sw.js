var CACHE_VERSION = 'v1.2.0';
var CORE_CACHE = 'core-' + CACHE_VERSION;
var FONT_CACHE = 'fonts-' + CACHE_VERSION;
var CDN_CACHE = 'cdn-' + CACHE_VERSION;
var DYNAMIC_CACHE = 'dynamic-' + CACHE_VERSION;

var CORE_ASSETS = [
  './',
  './index.html',
  './css/style.css',
  './js/app.js',
  './js/pdf-export.js',
  './manifest.json',
  './icons/icon-192.svg',
  './icons/icon-512.svg'
];

/* install: pre-cache core assets */
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CORE_CACHE).then(function(cache) {
      return cache.addAll(CORE_ASSETS);
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

/* activate: clean old caches */
self.addEventListener('activate', function(event) {
  var validCaches = [CORE_CACHE, FONT_CACHE, CDN_CACHE, DYNAMIC_CACHE];
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) {
          return validCaches.indexOf(k) === -1;
        }).map(function(k) {
          return caches.delete(k);
        })
      );
    }).then(function() {
      return self.clients.claim();
    })
  );
});

/* fetch: strategy per resource type */
self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);

  /* Only handle GET requests */
  if (event.request.method !== 'GET') return;

  /* fonts/* -> Cache-First */
  if (url.pathname.indexOf('/fonts/') !== -1 ||
      url.hostname === 'fonts.googleapis.com' ||
      url.hostname === 'fonts.gstatic.com') {
    event.respondWith(cacheFirst(event.request, FONT_CACHE));
    return;
  }

  /* CDN (jsdelivr) -> Stale-While-Revalidate */
  if (url.hostname === 'cdn.jsdelivr.net') {
    event.respondWith(staleWhileRevalidate(event.request, CDN_CACHE));
    return;
  }

  /* Same-origin CSS/JS -> Stale-While-Revalidate */
  if (url.origin === self.location.origin &&
      (url.pathname.endsWith('.css') || url.pathname.endsWith('.js'))) {
    event.respondWith(staleWhileRevalidate(event.request, CORE_CACHE));
    return;
  }

  /* HTML -> Network-First */
  if (event.request.headers.get('accept') &&
      event.request.headers.get('accept').indexOf('text/html') !== -1) {
    event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
    return;
  }

  /* Everything else -> Network-First */
  event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
});

/* === Strategies === */

function cacheFirst(request, cacheName) {
  return caches.match(request).then(function(cached) {
    if (cached) return cached;
    return fetch(request).then(function(response) {
      if (response && response.ok) {
        var clone = response.clone();
        caches.open(cacheName).then(function(cache) {
          cache.put(request, clone);
        });
      }
      return response;
    });
  }).catch(function() {
    return caches.match(request);
  });
}

function networkFirst(request, cacheName) {
  return fetch(request).then(function(response) {
    if (response && response.ok) {
      var clone = response.clone();
      caches.open(cacheName).then(function(cache) {
        cache.put(request, clone);
      });
    }
    return response;
  }).catch(function() {
    return caches.match(request).then(function(cached) {
      if (cached) return cached;
      /* Offline fallback for HTML */
      if (request.headers.get('accept') &&
          request.headers.get('accept').indexOf('text/html') !== -1) {
        return caches.match('./index.html');
      }
    });
  });
}

function staleWhileRevalidate(request, cacheName) {
  return caches.open(cacheName).then(function(cache) {
    return cache.match(request).then(function(cached) {
      var fetchPromise = fetch(request).then(function(response) {
        if (response && response.ok) {
          cache.put(request, response.clone());
        }
        return response;
      }).catch(function() {
        return cached;
      });
      return cached || fetchPromise;
    });
  });
}
