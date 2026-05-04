/**
 * RegEngine Service Worker — offline support for field data capture.
 *
 * Strategy:
 *  - Static assets (CSS, JS, images): cache-first with network fallback
 *  - Field capture pages: network-first with cache fallback (offline support)
 *  - API calls: network-only (queue failed POSTs for retry when online)
 *  - Everything else: network-first
 */

const CACHE_NAME = 'regengine-v1';
const OFFLINE_EVENT_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

const PRECACHE_URLS = [
  '/fsma/field-capture',
  '/tools/scan',
  '/tools/label-scanner',
  '/manifest.json',
  '/icon.png',
];

// Install: precache field capture pages
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: strategy-based routing
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests (POST to APIs should not be cached)
  if (event.request.method !== 'GET') return;

  // Static assets: cache-first
  if (
    url.pathname.startsWith('/_next/static/') ||
    url.pathname.startsWith('/icon') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.svg')
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) =>
        cached || fetch(event.request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
      )
    );
    return;
  }

  // Field capture pages + tools: network-first with cache fallback
  if (
    url.pathname.startsWith('/fsma/field-capture') ||
    url.pathname.startsWith('/tools/scan') ||
    url.pathname.startsWith('/tools/label-scanner')
  ) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Everything else: network-first, no caching
});

// Background sync: retry failed API calls when back online
self.addEventListener('sync', (event) => {
  if (event.tag === 'regengine-offline-queue') {
    event.waitUntil(Promise.all([
      notifyClientsToSync(),
      processOfflineQueue(),
    ]));
  }
});

async function processOfflineQueue() {
  // Field capture now uses RegEngineMobileDB as the durable queue owner.
  // This handler drains legacy service-worker-owned records without deleting
  // them until the backend acknowledges the replay with a 2xx response.
  try {
    const db = await openDB();
    const tx = db.transaction('offline-events', 'readonly');
    const store = tx.objectStore('offline-events');
    const events = await getAllFromStore(store);

    for (const event of events) {
      const retryEvent = normalizeOfflineEvent(event);
      const queuedAt = getOfflineEventQueuedAt(retryEvent);
      const retentionExceeded = queuedAt && Date.now() - queuedAt > OFFLINE_EVENT_MAX_AGE_MS;

      try {
        const response = await fetch(retryEvent.url, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            ...(retryEvent.headers || {}),
          },
          body: typeof retryEvent.body === 'string' ? retryEvent.body : JSON.stringify(retryEvent.body),
        });
        if (!response.ok) {
          throw new Error(`Replay failed: ${response.status}`);
        }
        await deleteOfflineEvent(db, retryEvent.id);
      } catch (error) {
        await putOfflineEvent(db, markOfflineEventFailure(retryEvent, error, retentionExceeded));
        break;
      }
    }
  } catch {
    // IndexedDB not available or empty — nothing to sync
  }
}

async function notifyClientsToSync() {
  if (!self.clients?.matchAll) return;
  const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of clients) {
    client.postMessage({ type: 'REGENGINE_SYNC_OFFLINE_QUEUE' });
  }
}

function normalizeOfflineEvent(event) {
  return {
    ...event,
    createdAt: getOfflineEventQueuedAt(event) || Date.now(),
  };
}

function markOfflineEventFailure(event, error, retentionExceeded) {
  const attempts = Number.isFinite(event.syncAttempts) ? event.syncAttempts + 1 : 1;
  return {
    ...event,
    syncAttempts: attempts,
    lastSyncAttemptAt: Date.now(),
    syncError: error instanceof Error ? error.message : String(error || 'Replay failed'),
    ...(retentionExceeded && !event.retentionExceededAt ? { retentionExceededAt: Date.now() } : {}),
  };
}

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('regengine-offline', 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('offline-events', { keyPath: 'id', autoIncrement: true });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function getOfflineEventQueuedAt(event) {
  const value = event.createdAt || event.timestamp || event.queuedAt;
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

function getAllFromStore(store) {
  return new Promise((resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function putOfflineEvent(db, event) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction('offline-events', 'readwrite');
    const request = tx.objectStore('offline-events').put(event);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

function deleteOfflineEvent(db, id) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction('offline-events', 'readwrite');
    const request = tx.objectStore('offline-events').delete(id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}
