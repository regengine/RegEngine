import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
    markScanSynced,
    markPhotoSynced,
    markScanSyncFailed,
    markPhotoSyncFailed,
    getPendingUploads,
    cleanupOfflineRecords,
} from '@/lib/db';
import { useIngestFile } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/use-toast';
import { getServiceURL } from '@/lib/api-config';

export function useSync() {
    const [isOnline, setIsOnline] = useState(true);
    const [isSyncing, setIsSyncing] = useState(false);
    const isSyncingRef = useRef(false);
    const { apiKey, tenantId } = useAuth();
    const { toast } = useToast();

    const { mutateAsync: ingestFile } = useIngestFile();

    const syncEndpoint = useCallback(async (payload: string) => {
        const response = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
            method: 'POST',
            credentials: 'include', // Send HTTP-only cookies
            headers: {
                'Content-Type': 'application/json',
                ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
            },
            body: payload,
        });
        if (!response.ok) throw new Error(`Ingest failed: ${response.status}`);
    }, [tenantId]);

    const sync = useCallback(async () => {
        if (!apiKey || isSyncingRef.current || !navigator.onLine) return;

        isSyncingRef.current = true;
        setIsSyncing(true);
        let failedUploads = 0;
        let successfulUploads = 0;
        try {
            try {
                await cleanupOfflineRecords();
            } catch {
                // cleanup is best-effort
            }

            const { scans, photos } = await getPendingUploads();

            if (scans.length === 0 && photos.length === 0) {
                setIsSyncing(false);
                return;
            }

            toast({
                title: "Syncing Offline Data...",
                description: `Uploading ${scans.length} scans and ${photos.length} photos.`,
            });

            // Sync Scans — replay the stored ingest payload via webhook endpoint
            for (const scan of scans) {
                try {
                    if (scan.payload) {
                        // Structured payload saved by FieldCaptureClient — replay directly
                        await syncEndpoint(scan.payload);
                    } else {
                        // Legacy record with only raw barcode string — build minimal event
                        const payload = {
                            source: 'mobile_scanner_pwa_offline',
                            tenant_id: tenantId || undefined,
                            events: [{
                                cte_type: scan.cteType || 'receiving',
                                traceability_lot_code: scan.content,
                                product_description: `Offline scan ${scan.content}`,
                                quantity: 1,
                                unit_of_measure: 'cases',
                                timestamp: new Date(scan.timestamp).toISOString(),
                                location_name: 'Field Capture Mobile (Offline)',
                                kdes: { raw_scan: scan.content },
                            }],
                        };
                        await syncEndpoint(JSON.stringify(payload));
                    }
                    if (typeof scan.id === 'number') {
                        await markScanSynced(scan.id);
                    }
                    successfulUploads += 1;
                } catch (e) {
                    failedUploads += 1;
                    if (typeof scan.id === 'number') {
                        await markScanSyncFailed(scan.id, e);
                    }
                    if (process.env.NODE_ENV !== 'production') {
                        console.error("Failed to sync scan", {
                            id: scan.id,
                            timestamp: scan.timestamp,
                            cteType: scan.cteType,
                        }, e);
                    }
                }
            }

            // Sync Photos
            for (const photo of photos) {
                try {
                    const file = new File([photo.blob], `offline_capture_${photo.timestamp}.jpg`, { type: 'image/jpeg' });
                    await ingestFile({
                        apiKey,
                        file,
                        sourceSystem: "mobile_capture_pwa_offline"
                    });
                    if (typeof photo.id === 'number') {
                        await markPhotoSynced(photo.id);
                    }
                    successfulUploads += 1;
                } catch (e) {
                    failedUploads += 1;
                    if (typeof photo.id === 'number') {
                        await markPhotoSyncFailed(photo.id, e);
                    }
                    if (process.env.NODE_ENV !== 'production') {
                        console.error("Failed to sync photo", {
                            id: photo.id,
                            timestamp: photo.timestamp,
                        }, e);
                    }
                }
            }

            if (failedUploads > 0) {
                toast({
                    title: "Sync Partially Complete",
                    description: `${successfulUploads} uploaded. ${failedUploads} item${failedUploads === 1 ? '' : 's'} remain queued for retry.`,
                    variant: "destructive",
                });
            } else {
                toast({
                    title: "Sync Complete",
                    description: "All offline data has been uploaded.",
                    variant: "default"
                });
            }

            // Cleanup records created during this sync attempt.
            try {
                await cleanupOfflineRecords();
            } catch {
                // cleanup is best-effort
            }

        } catch (err) {
            if (process.env.NODE_ENV !== 'production') { console.error("Sync error", err); }
        } finally {
            isSyncingRef.current = false;
            setIsSyncing(false);
        }
    }, [apiKey, ingestFile, syncEndpoint, tenantId, toast]);

    useEffect(() => {
        // Initial check
        setIsOnline(navigator.onLine);

        const handleOnline = () => {
            setIsOnline(true);
            sync();
        };

        const handleOffline = () => {
            setIsOnline(false);
        };

        window.addEventListener('online', handleOnline);
        window.addEventListener('offline', handleOffline);

        // Try verifying connection periodically or on mount
        if (navigator.onLine) {
            sync();
        }

        return () => {
            window.removeEventListener('online', handleOnline);
            window.removeEventListener('offline', handleOffline);
        };
    }, [sync]);

    useEffect(() => {
        if (!('serviceWorker' in navigator)) return;

        const handleServiceWorkerMessage = (event: MessageEvent) => {
            if (event.data?.type === 'REGENGINE_SYNC_OFFLINE_QUEUE') {
                sync();
            }
        };

        navigator.serviceWorker.addEventListener('message', handleServiceWorkerMessage);
        return () => {
            navigator.serviceWorker.removeEventListener('message', handleServiceWorkerMessage);
        };
    }, [sync]);

    return { isOnline, isSyncing, manualSync: sync };
}
