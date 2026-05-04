import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';

import { describe, expect, it, vi } from 'vitest';

type OfflineEvent = {
    id: number;
    url: string;
    body: Record<string, unknown>;
    createdAt?: number;
    timestamp?: number | string;
    queuedAt?: number | string;
};

function loadServiceWorker(records: OfflineEvent[], fetchImpl = vi.fn().mockResolvedValue({ ok: true })) {
    const putCalls: OfflineEvent[] = [];
    const deleteCalls: number[] = [];
    const source = readFileSync(join(process.cwd(), 'public/sw.js'), 'utf-8');

    const request = <T>(result: T) => {
        const req: { result?: T; onsuccess?: () => void; onerror?: () => void; error?: Error } = {};
        setTimeout(() => {
            req.result = result;
            req.onsuccess?.();
        }, 0);
        return req;
    };

    const db = {
        transaction: () => ({
            objectStore: () => ({
                getAll: () => request([...records]),
                put: (event: OfflineEvent) => {
                    putCalls.push(event);
                    const index = records.findIndex((record) => record.id === event.id);
                    if (index >= 0) records[index] = event;
                    return request(undefined);
                },
                delete: (id: number) => {
                    deleteCalls.push(id);
                    const index = records.findIndex((record) => record.id === id);
                    if (index >= 0) records.splice(index, 1);
                    return request(undefined);
                },
            }),
        }),
    };

    const context = {
        self: {
            addEventListener: vi.fn(),
            skipWaiting: vi.fn(),
            clients: {
                claim: vi.fn(),
                matchAll: vi.fn().mockResolvedValue([]),
            },
        },
        caches: {
            open: vi.fn(),
            keys: vi.fn(),
            match: vi.fn(),
            delete: vi.fn(),
        },
        fetch: fetchImpl,
        indexedDB: {
            open: () => request(db),
        },
        Date,
        Number,
        Promise,
        URL,
        setTimeout,
    };

    vm.createContext(context);
    vm.runInContext(source, context);
    return {
        context: context as typeof context & { processOfflineQueue: () => Promise<void> },
        putCalls,
        deleteCalls,
        fetchImpl,
        records,
    };
}

describe('service worker offline queue retention', () => {
    it('only deletes queued events after a successful backend acknowledgement', async () => {
        const now = Date.now();
        const oldEvent = {
            id: 1,
            url: '/expired',
            body: { traceability_lot_code: 'old' },
            createdAt: now - 31 * 24 * 60 * 60 * 1000,
        };
        const freshEvent = {
            id: 2,
            url: '/fresh',
            body: { traceability_lot_code: 'fresh' },
            createdAt: now,
        };
        const { context, deleteCalls, fetchImpl } = loadServiceWorker([oldEvent, freshEvent]);

        await context.processOfflineQueue();

        expect(deleteCalls).toEqual([1, 2]);
        expect(fetchImpl).toHaveBeenCalledTimes(2);
        expect(fetchImpl).toHaveBeenCalledWith('/expired', expect.objectContaining({
            method: 'POST',
            credentials: 'include',
            body: JSON.stringify(oldEvent.body),
        }));
        expect(fetchImpl).toHaveBeenCalledWith('/fresh', expect.objectContaining({
            method: 'POST',
            credentials: 'include',
            body: JSON.stringify(freshEvent.body),
        }));
    });

    it('keeps expired events queued when replay fails', async () => {
        const event = {
            id: 1,
            url: '/expired',
            body: { traceability_lot_code: 'expired' },
            createdAt: Date.now() - 31 * 24 * 60 * 60 * 1000,
        };
        const { context, putCalls, deleteCalls, records } = loadServiceWorker(
            [event],
            vi.fn().mockResolvedValue({ ok: false, status: 500 })
        );

        await context.processOfflineQueue();

        expect(deleteCalls).toEqual([]);
        expect(putCalls).toHaveLength(1);
        expect(records).toHaveLength(1);
        expect(records[0]).toEqual(expect.objectContaining({
            id: 1,
            syncAttempts: 1,
            syncError: 'Replay failed: 500',
            retentionExceededAt: expect.any(Number),
        }));
    });

    it('hydrates legacy events with retry metadata when replay fails', async () => {
        const event = {
            id: 1,
            url: '/legacy',
            body: { traceability_lot_code: 'legacy' },
        };
        const { context, putCalls, records } = loadServiceWorker(
            [event],
            vi.fn().mockRejectedValue(new Error('offline'))
        );

        await context.processOfflineQueue();

        expect(putCalls).toHaveLength(1);
        expect(putCalls[0]).toEqual(expect.objectContaining({
            id: 1,
            createdAt: expect.any(Number),
            syncAttempts: 1,
            lastSyncAttemptAt: expect.any(Number),
        }));
        expect(records).toHaveLength(1);
        expect(records[0].createdAt).toEqual(expect.any(Number));
    });
});
