/**
 * Service Worker Registration
 * 
 * Registers the service worker for offline support and caching
 */

export function registerServiceWorker() {
    if (typeof window === 'undefined') {
        return; // Skip on server-side
    }

    if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
        window.addEventListener('load', async () => {
            try {
                const registration = await navigator.serviceWorker.register('/sw.js');

                // Check for updates
                registration.addEventListener('updatefound', () => {
                    const newWorker = registration.installing;

                    if (newWorker) {
                        newWorker.addEventListener('statechange', () => {
                            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                // New service worker available, prompt user to reload
                                // Optional: Show update notification
                                if (window.confirm('A new version is available. Reload to update?')) {
                                    window.location.reload();
                                }
                            }
                        });
                    }
                });

            } catch (error) {
                console.error('Service Worker registration failed:', error);
            }
        });
    }
}

export function unregisterServiceWorker() {
    if (typeof window === 'undefined') {
        return;
    }

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.ready
            .then((registration) => {
                registration.unregister();
            })
            .catch((error) => {
                console.error('Service Worker unregistration failed:', error);
            });
    }
}

// Check if running in standalone mode (PWA)
export function isStandalone() {
    if (typeof window === 'undefined') {
        return false;
    }

    return (
        window.matchMedia('(display-mode: standalone)').matches ||
        (window.navigator as any).standalone === true
    );
}

// Request persistent storage (prevents cache eviction)
export async function requestPersistentStorage() {
    if (typeof navigator === 'undefined' || !navigator.storage?.persist) {
        return false;
    }

    try {
        const isPersisted = await navigator.storage.persist();
        return isPersisted;
    } catch (error) {
        console.error('Failed to request persistent storage:', error);
        return false;
    }
}
