import { describe, expect, it } from 'vitest';

import { newScanIdempotencyKey, scanIdempotencyKey } from '@/lib/db';

describe('scan idempotency keys', () => {
    it('mints unique non-empty keys', () => {
        const first = newScanIdempotencyKey();
        const second = newScanIdempotencyKey();
        expect(first.length).toBeGreaterThan(0);
        expect(second.length).toBeGreaterThan(0);
        expect(first).not.toBe(second);
    });

    it('prefers the stored key', () => {
        expect(
            scanIdempotencyKey({
                id: 4,
                timestamp: 1_700_000_000_000,
                content: 'LOT-1',
                idempotencyKey: 'scan-key-from-capture',
            }),
        ).toBe('scan-key-from-capture');
    });

    it('derives a stable key for legacy records with no stored key', () => {
        const record = {
            id: 7,
            timestamp: 1_700_000_000_000,
            content: 'LOT-1',
        };
        expect(scanIdempotencyKey(record)).toBe('offline-scan-7-1700000000000');
        // Stable across retries: same record, same key.
        expect(scanIdempotencyKey(record)).toBe(scanIdempotencyKey(record));
    });

    it('derives distinct keys for distinct legacy records', () => {
        const base = { timestamp: 1_700_000_000_000, content: 'LOT-1' };
        expect(scanIdempotencyKey({ ...base, id: 7 })).not.toBe(
            scanIdempotencyKey({ ...base, id: 8 }),
        );
    });
});
