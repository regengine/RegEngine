import { describe, expect, it } from 'vitest';

import { cleanupOfflineRecords, cleanupSyncedRecords, OFFLINE_SYNC_RETENTION } from '@/lib/db';

type FakeRecord = {
    id: number;
    timestamp: number;
    synced: number;
};

type FakeScanRecord = FakeRecord & {
    content: string;
    payload?: string;
    cteType?: string;
};

type FakePhotoRecord = FakeRecord & {
    blob: Blob;
};

function createTable<T extends FakeRecord>(initialRecords: T[]) {
    const table = {
        records: [...initialRecords],
        where() {
            return {
                equals: (synced: number) => ({
                    filter: (predicate: (record: T) => boolean) => ({
                        delete: async () => {
                            const before = table.records.length;
                            table.records = table.records.filter(
                                (record) => record.synced !== synced || !predicate(record)
                            );
                            return before - table.records.length;
                        },
                    }),
                }),
            };
        },
    };
    return table;
}

describe('offline IndexedDB retention', () => {
    it('removes stale synced and stale unsynced records with separate retention windows', async () => {
        const now = 1_000_000;
        const database = {
            scans: createTable<FakeScanRecord>([
                { id: 1, timestamp: now - OFFLINE_SYNC_RETENTION.syncedMaxAgeMs - 1, synced: 1, content: 'old synced' },
                { id: 2, timestamp: now - OFFLINE_SYNC_RETENTION.syncedMaxAgeMs + 1, synced: 1, content: 'fresh synced' },
                { id: 3, timestamp: now - OFFLINE_SYNC_RETENTION.unsyncedMaxAgeMs - 1, synced: 0, content: 'stale unsynced' },
                { id: 4, timestamp: now - OFFLINE_SYNC_RETENTION.unsyncedMaxAgeMs + 1, synced: 0, content: 'fresh unsynced' },
            ]),
            photos: createTable<FakePhotoRecord>([
                { id: 5, timestamp: now - OFFLINE_SYNC_RETENTION.syncedMaxAgeMs - 1, synced: 1, blob: new Blob() },
                { id: 6, timestamp: now - OFFLINE_SYNC_RETENTION.unsyncedMaxAgeMs - 1, synced: 0, blob: new Blob() },
                { id: 7, timestamp: now - OFFLINE_SYNC_RETENTION.unsyncedMaxAgeMs + 1, synced: 0, blob: new Blob() },
            ]),
        };

        const result = await cleanupOfflineRecords({ now }, database);

        expect(result).toEqual({
            deletedSyncedScans: 1,
            deletedSyncedPhotos: 1,
            deletedStaleUnsyncedScans: 1,
            deletedStaleUnsyncedPhotos: 1,
        });
        expect(database.scans.records.map((record) => record.id)).toEqual([2, 4]);
        expect(database.photos.records.map((record) => record.id)).toEqual([7]);
    });

    it('preserves unsynced records when running the legacy synced-only cleanup', async () => {
        const now = 1_000_000;
        const database = {
            scans: createTable<FakeScanRecord>([
                { id: 1, timestamp: now - 101, synced: 1, content: 'old synced' },
                { id: 2, timestamp: now - 101, synced: 0, content: 'old unsynced' },
            ]),
            photos: createTable<FakePhotoRecord>([
                { id: 3, timestamp: now - 101, synced: 1, blob: new Blob() },
                { id: 4, timestamp: now - 101, synced: 0, blob: new Blob() },
            ]),
        };

        const result = await cleanupSyncedRecords(100, database, now);

        expect(result).toEqual({ deletedScans: 1, deletedPhotos: 1 });
        expect(database.scans.records.map((record) => record.id)).toEqual([2]);
        expect(database.photos.records.map((record) => record.id)).toEqual([4]);
    });
});
