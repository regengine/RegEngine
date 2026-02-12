import Dexie, { Table } from 'dexie';

export interface ScanRecord {
    id?: number;
    content: string;
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

export async function saveScan(content: string) {
    await db.scans.add({
        content,
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
