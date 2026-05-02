import Dexie, { Table } from 'dexie';

const DAY_MS = 24 * 60 * 60 * 1000;

export const OFFLINE_SYNC_RETENTION = {
    syncedMaxAgeMs: 7 * DAY_MS,
    unsyncedMaxAgeMs: 30 * DAY_MS,
} as const;

export interface ScanRecord {
    id?: number;
    content: string;
    /** Structured payload for offline replay — mirrors the webhook ingest body */
    payload?: string; // JSON-serialized ingest event
    cteType?: string;
    timestamp: number;
    synced: number; // 0 = false, 1 = true
}

export interface PhotoRecord {
    id?: number;
    blob: Blob;
    timestamp: number;
    synced: number;
}

interface OfflineRecord {
    timestamp: number;
    synced: number;
}

interface OfflineRecordTable<T extends OfflineRecord> {
    where(index: string): {
        equals(value: number): {
            filter(predicate: (record: T) => boolean): {
                delete(): Promise<number>;
            };
        };
    };
}

interface OfflineDatabase {
    scans: OfflineRecordTable<ScanRecord>;
    photos: OfflineRecordTable<PhotoRecord>;
}

export interface OfflineRetentionOptions {
    now?: number;
    syncedMaxAgeMs?: number;
    unsyncedMaxAgeMs?: number;
}

export class MobileDatabase extends Dexie {
    scans!: Table<ScanRecord>;
    photos!: Table<PhotoRecord>;

    constructor() {
        super('RegEngineMobileDB');
        this.version(1).stores({
            scans: '++id, timestamp, synced', // Primary key and indexed props
            photos: '++id, timestamp, synced'
        });
    }
}

export const db = new MobileDatabase();

export async function saveScan(content: string, payload?: Record<string, unknown>, cteType?: string) {
    await db.scans.add({
        content,
        payload: payload ? JSON.stringify(payload) : undefined,
        cteType,
        timestamp: Date.now(),
        synced: 0
    });
}

export async function savePhoto(blob: Blob) {
    await db.photos.add({
        blob,
        timestamp: Date.now(),
        synced: 0
    });
}

export async function getPendingUploads() {
    const scans = await db.scans.where('synced').equals(0).toArray();
    const photos = await db.photos.where('synced').equals(0).toArray();
    return { scans, photos };
}

export async function markScanSynced(id: number) {
    await db.scans.update(id, { synced: 1 });
}

export async function markPhotoSynced(id: number) {
    await db.photos.update(id, { synced: 1 });
}

async function deleteBySyncedAndCutoff<T extends OfflineRecord>(
    table: OfflineRecordTable<T>,
    synced: number,
    cutoff: number
) {
    if (!Number.isFinite(cutoff)) return 0;
    return table
        .where('synced').equals(synced)
        .filter((record) => record.timestamp < cutoff)
        .delete();
}

/**
 * Enforce client-side retention for offline field capture data.
 *
 * Synced records are short lived cache. Unsynced records stay longer so a
 * temporarily offline operator can recover, but they should not persist
 * indefinitely in browser storage.
 */
export async function cleanupOfflineRecords(
    options: OfflineRetentionOptions = {},
    database: OfflineDatabase = db
) {
    const now = options.now ?? Date.now();
    const syncedMaxAgeMs = options.syncedMaxAgeMs ?? OFFLINE_SYNC_RETENTION.syncedMaxAgeMs;
    const unsyncedMaxAgeMs = options.unsyncedMaxAgeMs ?? OFFLINE_SYNC_RETENTION.unsyncedMaxAgeMs;
    const syncedCutoff = now - syncedMaxAgeMs;
    const unsyncedCutoff = now - unsyncedMaxAgeMs;

    const [
        deletedSyncedScans,
        deletedSyncedPhotos,
        deletedStaleUnsyncedScans,
        deletedStaleUnsyncedPhotos,
    ] = await Promise.all([
        deleteBySyncedAndCutoff(database.scans, 1, syncedCutoff),
        deleteBySyncedAndCutoff(database.photos, 1, syncedCutoff),
        deleteBySyncedAndCutoff(database.scans, 0, unsyncedCutoff),
        deleteBySyncedAndCutoff(database.photos, 0, unsyncedCutoff),
    ]);

    return {
        deletedSyncedScans,
        deletedSyncedPhotos,
        deletedStaleUnsyncedScans,
        deletedStaleUnsyncedPhotos,
    };
}

/**
 * Remove synced records older than `maxAgeMs` (default 7 days).
 * Prevents IndexedDB from growing indefinitely on mobile devices.
 */
export async function cleanupSyncedRecords(
    maxAgeMs: number = OFFLINE_SYNC_RETENTION.syncedMaxAgeMs,
    database: OfflineDatabase = db,
    now: number = Date.now()
) {
    const { deletedSyncedScans, deletedSyncedPhotos } = await cleanupOfflineRecords({
        now,
        syncedMaxAgeMs: maxAgeMs,
        unsyncedMaxAgeMs: Number.POSITIVE_INFINITY,
    }, database);
    return { deletedScans: deletedSyncedScans, deletedPhotos: deletedSyncedPhotos };
}
