/**
 * Service Worker for RegEngine
 * 
 * Provides:
 * - Offline functionality
 * - Asset caching
 * - Faster repeat visits
 * - Background sync
 */

const CACHE_NAME = 'regengine-v1.0.0';
const STATIC_CACHE = 'regengine-static-v1';
const DYNAMIC_CACHE = 'regengine-dynamic-v1';

// Static assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/login',
    '/dashboard',
    '/offline.html',
    '/manifest.json',
];

// API endpoints to cache (with network-first strategy)
const API_PATTERNS = [
    /\/api\//,
    /\/health$/,
    /\/v1\//,
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');

    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[Service Worker] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');

    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => {
                            return name !== STATIC_CACHE && name !== DYNAMIC_CACHE;
                        })
                        .map((name) => {
                            console.log('[Service Worker] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => self.clients.claim())
    );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip non-GET requests
    if (request.method !== 'GET') {
        return;
    }

    // Skip chrome extensions
    if (url.protocol === 'chrome-extension:') {
        return;
    }

    // API requests - Network first, cache fallback
    if (API_PATTERNS.some(pattern => pattern.test(url.pathname))) {
        event.respondWith(networkFirstStrategy(request));
        return;
    }

    // Static assets - Cache first, network fallback
    event.respondWith(cacheFirstStrategy(request));
});

// Cache-first strategy (for static assets)
async function cacheFirstStrategy(request) {
    const cache = await caches.open(STATIC_CACHE);
    const cached = await cache.match(request);

    if (cached) {
        console.log('[Service Worker] Serving from cache:', request.url);
        return cached;
    }

    try {
        const response = await fetch(request);

        // Cache successful responses
        if (response.status === 200) {
            const responseClone = response.clone();
            cache.put(request, responseClone);
        }

        return response;
    } catch (error) {
        console.error('[Service Worker] Fetch failed:', error);

        // Return offline page for navigation requests
        if (request.mode === 'navigate') {
            return cache.match('/offline.html');
        }

        throw error;
    }
}

// Network-first strategy (for API requests)
async function networkFirstStrategy(request) {
    const cache = await caches.open(DYNAMIC_CACHE);

    try {
        const response = await fetch(request);

        // Cache successful API responses
        if (response.status === 200) {
            const responseClone = response.clone();
            cache.put(request, responseClone);
        }

        return response;
    } catch (error) {
        console.error('[Service Worker] Network failed, trying cache:', error);

        const cached = await cache.match(request);

        if (cached) {
            console.log('[Service Worker] Serving API from cache:', request.url);
            return cached;
        }

        throw error;
    }
}

// Background sync for offline actions
self.addEventListener('sync', (event) => {
    console.log('[Service Worker] Background sync:', event.tag);

    if (event.tag === 'sync-data') {
        event.waitUntil(syncData());
    }
});

async function syncData() {
    // Sync any pending data when back online
    console.log('[Service Worker] Syncing data...');

    // Implementation would depend on your offline data strategy
    // For example, sending queued API requests
}

// Push notifications (future enhancement)
self.addEventListener('push', (event) => {
    console.log('[Service Worker] Push received:', event);

    const data = event.data ? event.data.json() : {};
    const title = data.title || 'RegEngine Notification';
    const options = {
        body: data.body || 'You have a new notification',
        icon: '/icon-192x192.png',
        badge: '/badge-72x72.png',
        data: data.url,
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
    console.log('[Service Worker] Notification clicked');

    event.notification.close();

    if (event.notification.data) {
        event.waitUntil(
            clients.openWindow(event.notification.data)
        );
    }
});
