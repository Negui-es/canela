'use strict';
const OFFLINE_CACHE = '{{ cache_name|escapejs }}';
const LANGUAGES = {{ languages|safe }};
const offlinePath = language => '/offline/' + language + '/';

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(OFFLINE_CACHE);
    // These are the only documents stored: generic pages with no account data.
    await cache.addAll(LANGUAGES.map(language => new Request(offlinePath(language), {
      credentials:'omit', cache:'reload', redirect:'error'
    })));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('canela-offline-') && key !== OFFLINE_CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

function languageFor(url) {
  const prefix = url.pathname.split('/')[1];
  if (LANGUAGES.includes(prefix)) return prefix;
  for (const preference of self.navigator.languages || []) {
    const code = preference.toLowerCase().split('-')[0];
    if (LANGUAGES.includes(code)) return code;
  }
  return 'en';
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  // No caching or replay of forms, photos, API responses, or private pages.
  if (request.method !== 'GET' || request.mode !== 'navigate' || url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      // Preserve application errors and Cloudflare's Spanish offline response.
      return await fetch(request, {signal:controller.signal, cache:'no-store'});
    } catch {
      const cache = await caches.open(OFFLINE_CACHE);
      const page = await cache.match(offlinePath(languageFor(url)));
      return new Response(page ? await page.text() : 'Canela is offline. Please try again later.', {
        status:503,
        headers:{'Content-Type':page ? 'text/html; charset=utf-8' : 'text/plain; charset=utf-8',
          'Cache-Control':'no-store', 'Retry-After':'60', 'X-Content-Type-Options':'nosniff'}
      });
    } finally {
      clearTimeout(timeout);
    }
  })());
});
