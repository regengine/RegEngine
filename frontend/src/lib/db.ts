import Dexie, { Table } from 'dexie';

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

/**
 * Remove synced records older than `maxAgeMs` (default 7 days).
 * Prevents IndexedDB from growing indefinitely on mobile devices.
 */
export async function cleanupSyncedRecords(maxAgeMs: number = 7 * 24 * 60 * 60 * 1000) {
    const cutoff = Date.now() - maxAgeMs;
    const deletedScans = await db.scans
        .where('synced').equals(1)
        .filter((s) => s.timestamp < cutoff)
        .delete();
    const deletedPhotos = await db.photos
        .where('synced').equals(1)
        .filter((p) => p.timestamp < cutoff)
        .delete();
    return { deletedScans, deletedPhotos };
}
