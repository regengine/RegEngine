
import { useEffect, useState } from 'react';
import { markScanSynced, markPhotoSynced, getPendingUploads, cleanupSyncedRecords } from '@/lib/db';
import { useIngestFile } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/use-toast';
import { getServiceURL } from '@/lib/api-config';

export function useSync() {
    const [isOnline, setIsOnline] = useState(true);
    const [isSyncing, setIsSyncing] = useState(false);
    const { apiKey, tenantId } = useAuth();
    const { toast } = useToast();

    const ingestFileMutation = useIngestFile();

    const sync = async () => {
        if (!apiKey || isSyncing || !navigator.onLine) return;

        setIsSyncing(true);
        try {
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
                        const response = await fetch(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                            method: 'POST',
                            credentials: 'include', // Send HTTP-only cookies
                            headers: {
                                'Content-Type': 'application/json',
                                ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
                            },
                            body: scan.payload,
                        });
                        if (!response.ok) throw new Error(`Ingest failed: ${response.status}`);
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
                        const response = await fetch(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                            method: 'POST',
                            credentials: 'include', // Send HTTP-only cookies
                            headers: {
                                'Content-Type': 'application/json',
                                ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
                            },
                            body: JSON.stringify(payload),
                        });
                        if (!response.ok) throw new Error(`Ingest failed: ${response.status}`);
                    }
                    if (scan.id) await markScanSynced(scan.id);
                } catch (e) {
                    if (process.env.NODE_ENV !== 'production') { console.error("Failed to sync scan", scan, e); }
                }
            }

            // Sync Photos
            for (const photo of photos) {
                try {
                    const file = new File([photo.blob], `offline_capture_${photo.timestamp}.jpg`, { type: 'image/jpeg' });
                    await ingestFileMutation.mutateAsync({
                        apiKey,
                        file,
                        sourceSystem: "mobile_capture_pwa_offline"
                    });
                    if (photo.id) await markPhotoSynced(photo.id);
                } catch (e) {
                    if (process.env.NODE_ENV !== 'production') { console.error("Failed to sync photo", photo, e); }
                }
            }

            toast({
                title: "Sync Complete",
                description: "All offline data has been uploaded.",
                variant: "default"
            });

            // Cleanup old synced records to prevent IndexedDB bloat
            try {
                await cleanupSyncedRecords();
            } catch {
                // cleanup is best-effort
            }

        } catch (err) {
            if (process.env.NODE_ENV !== 'production') { console.error("Sync error", err); }
        } finally {
            setIsSyncing(false);
        }
    };

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [apiKey, tenantId]); // Re-run if API key or tenant changes

    return { isOnline, isSyncing, manualSync: sync };
}
