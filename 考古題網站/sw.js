var CACHE_VERSION = 'v1.6.5';
var CORE_CACHE = 'core-' + CACHE_VERSION;
var FONT_CACHE = 'fonts-' + CACHE_VERSION;
var CDN_CACHE = 'cdn-' + CACHE_VERSION;
var DYNAMIC_CACHE = 'dynamic-' + CACHE_VERSION;

var CORE_ASSETS = [
  './',
  './index.html',
  './category.html',
  './analytics.html',
  './analytics-chart-bundle.js',
  './vendor/chart.js-4.4.1/chart.umd.js',
  './data/home-stats.json',
  './css/style.css',
  './js/app.js',
  './js/answer-utils.js',
  './js/pdf-export.js',
  './水上警察學系/images/q2-option-A.png',
  './水上警察學系/images/q2-option-B.png',
  './水上警察學系/images/q2-option-C.png',
  './水上警察學系/images/q2-option-D.png',
  './消防學系/images/q20-option-A.png',
  './消防學系/images/q20-option-B.png',
  './消防學系/images/q20-option-C.png',
  './消防學系/images/q20-option-D.png',
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

/* activate: clean old caches, including the temporary simplified category pages */
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

  /* Generated homepage stats: always prefer fresh data, keep offline fallback */
  if (url.origin === self.location.origin &&
      url.pathname.endsWith('/data/home-stats.json')) {
    event.respondWith(networkFirst(event.request, CORE_CACHE));
    return;
  }

  /* One bundle response contains both Analytics code and its generated data. */
  if (url.origin === self.location.origin &&
      url.pathname.endsWith('/analytics-chart-bundle.js')) {
    event.respondWith(analyticsBundle(event.request));
    return;
  }

  /* Old pages may request code and data separately; never let cache strategies split the pair. */
  if (url.origin === self.location.origin &&
      (url.pathname.endsWith('/analytics-chart.js') ||
       url.pathname.endsWith('/analytics-chart-data.js'))) {
    event.respondWith(Promise.resolve(Response.error()));
    return;
  }

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

function analyticsBundle(request) {
  /* no-store keeps this route honest about freshness: an HTTP-cached copy is
     always a whole pair, but it may be an older one, and the point here is to
     promote the newest complete pair the server has. */
  return fetch(request, { cache: 'no-store' }).then(function(response) {
    if (!isAnalyticsPair(response)) {
      /* A 200 that is not JavaScript (a soft 404, an error page) must not be
         cached as the pair: fall through to the known complete pair instead. */
      throw new Error('Analytics pair unavailable');
    }
    var fresh = response.clone();
    return caches.open(CORE_CACHE).then(function(cache) {
      return cache.put(request, fresh);
    }).catch(function() {
      /* A fresh complete pair is still safe when cache storage fails. */
    }).then(function() {
      return response;
    });
  }).catch(function() {
    /* Only the versioned core cache holds a pair this worker wrote, and only a
       JavaScript entry can be one; anything else fails closed. */
    return caches.open(CORE_CACHE).then(function(cache) {
      return cache.match(request);
    }).then(function(cached) {
      return cached && isAnalyticsPair(cached) ? cached : Response.error();
    }).catch(function() {
      /* Cache storage itself failed: fail closed instead of guessing a pair. */
      return Response.error();
    });
  });
}

/* The pair is always served as JavaScript, so an HTML error page can never be
   mistaken for a code/data pair. */
function isAnalyticsPair(response) {
  if (!response || !response.ok || !response.headers) return false;
  return /javascript|ecmascript/i.test(response.headers.get('content-type') || '');
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
