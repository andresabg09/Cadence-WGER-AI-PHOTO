// Minimal app-shell cache. Network-first so a deploy is visible on the next
// load (no manual cache bump needed); the cache is only the offline fallback.
// v2: v1 could hold HTML saved under css/js URLs (see nginx /cadence/ fix).
const CACHE_NAME = 'cadence-shell-v19';
const SHELL_FILES = [
  'index.html',
  'scan.html',
  'confirm.html',
  'search.html',
  'login.html',
  'onboarding.html',
  'profile.html',
  'goals.html',
  'progress.html',
  'history.html',
  'reminders.html',
  'voice.html',
  'static/css/pulse.css',
  'static/js/api.js',
  'static/js/theme.js',
  'static/js/shell.js',
  'static/js/install.js',
  'static/js/food-sheet.js',
  'static/js/barcode.js',
  'static/icons/icon-192.png',
  'static/manifest.json',
  'static/icons/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never cache API calls - nutrition data must always be fresh.
  if (url.pathname.includes('/api/')) return;

  event.respondWith(
    fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
      }
      return response;
    }).catch(() => caches.match(request))
  );
});

// ---- Push notifications (reminders) ----
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'cadence', {
    body: data.body || '',
    icon: new URL('static/icons/icon-192.png', self.registration.scope).href,
    badge: new URL('static/icons/icon-192.png', self.registration.scope).href,
    tag: data.tag || undefined,
    data: { url: data.url || 'index.html' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || 'index.html', self.registration.scope).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const client of list) {
      if (client.url.startsWith(self.registration.scope) && 'navigate' in client) {
        return client.navigate(target).then((c) => (c || client).focus());
      }
    }
    return self.clients.openWindow(target);
  }));
});
