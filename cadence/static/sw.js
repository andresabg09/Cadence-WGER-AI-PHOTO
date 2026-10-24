// App-shell cache. Pages and assets open INSTANTLY from the cache and are refreshed in the background
// (stale-while-revalidate); API calls are never cached here. __BUILD__ changes with every deploy
// (the server stamps it), so a new deploy installs a fresh copy of everything and the page offers a reload.
const CACHE_NAME = 'cadence-shell-__BUILD__';
const SHELL_FILES = [
  './',
  'index.html',
  'scan.html',
  'confirm.html',
  'search.html',
  'login.html',
  'onboarding.html',
  'profile.html',
  'settings.html',
  'goals.html',
  'progress.html',
  'history.html',
  'reminders.html',
  'voice.html',
  'static/css/pulse.css',
  'static/js/api.js',
  'static/js/bits.js',
  'static/js/meal-detail.js',
  'static/js/workouts.js',
  'static/js/theme.js',
  'static/js/shell.js',
  'static/js/install.js',
  'static/js/datepicker.js',
  'static/js/food-sheet.js',
  'static/js/sfx.js',
  'static/js/register-menu.js',
  'static/js/constellation.js',
  'static/js/barcode.js',
  'static/icons/icon-192.png',
  'static/manifest.json',
  'static/icons/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      // One missing file must not stop the whole update: add them one by one, skipping the HTTP cache.
      .then((cache) => Promise.allSettled(SHELL_FILES.map((f) => cache.add(new Request(f, { cache: 'reload' })))))
      .then(() => self.skipWaiting())
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
  if (url.pathname.endsWith('/sw.js')) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    // ?date=... and similar only change what the page asks the API for, not the page itself.
    const cached = await cache.match(request, { ignoreSearch: true });
    const refresh = fetch(request, { cache: 'no-cache' }).then((response) => {
      if (response.ok && response.type === 'basic' && !response.redirected) cache.put(request.mode === 'navigate' ? new Request(url.origin + url.pathname) : request, response.clone());
      return response;
    });
    if (cached) {
      event.waitUntil(refresh.catch(() => {}));
      return cached;
    }
    try { return await refresh; } catch { return (await cache.match(request, { ignoreSearch: true })) || Response.error(); }
  })());
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
