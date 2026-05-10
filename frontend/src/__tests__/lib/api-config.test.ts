import { afterEach, describe, expect, it, vi } from 'vitest';

const ORIGINAL_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
const ORIGINAL_ADMIN_SERVICE_URL = process.env.ADMIN_SERVICE_URL;

afterEach(() => {
    vi.resetModules();

    if (ORIGINAL_API_BASE_URL === undefined) {
        delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
        process.env.NEXT_PUBLIC_API_BASE_URL = ORIGINAL_API_BASE_URL;
    }

    if (ORIGINAL_ADMIN_SERVICE_URL === undefined) {
        delete process.env.ADMIN_SERVICE_URL;
    } else {
        process.env.ADMIN_SERVICE_URL = ORIGINAL_ADMIN_SERVICE_URL;
    }
});

describe('getServiceURL', () => {
    it('keeps browser admin traffic on the same-origin proxy even when a public API base exists', async () => {
        process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.com';

        const { getServiceURL } = await import('@/lib/api-config');

        expect(getServiceURL('admin')).toBe('/api/admin');
        expect(getServiceURL('ingestion')).toBe('/api/ingestion');
        expect(getServiceURL('graph')).toBe('/api/graph');
    });

    it('still resolves server-side admin traffic from env when window is unavailable', async () => {
        process.env.ADMIN_SERVICE_URL = 'https://admin.internal.example.com';
        const originalWindow = globalThis.window;

        try {
            Reflect.deleteProperty(globalThis, 'window');
            vi.resetModules();
            const { getServiceURL } = await import('@/lib/api-config');

            expect(getServiceURL('admin')).toBe('https://admin.internal.example.com');
        } finally {
            if (originalWindow === undefined) {
                Reflect.deleteProperty(globalThis, 'window');
            } else {
                globalThis.window = originalWindow;
            }
        }
    });
});
