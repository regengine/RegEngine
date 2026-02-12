
import { useEffect, useState } from 'react';
import { db, markScanSynced, markPhotoSynced, getPendingUploads } from '@/lib/db';
import { useIngestURL, useIngestFile } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/use-toast';

export function useSync() {
    const [isOnline, setIsOnline] = useState(true);
    const [isSyncing, setIsSyncing] = useState(false);
    const { apiKey } = useAuth();
    const { toast } = useToast();

    const ingestUrlMutation = useIngestURL();
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

            // Sync Scans
            for (const scan of scans) {
                try {
                    // Treating scan content as a URL source for now, or we could add a new endpoint
                    // For MVP, we log it via the ingestURL endpoint with a special flag/system
                    await ingestUrlMutation.mutateAsync({
                        apiKey,
                        url: `scan://${scan.content}`, // Pseudo-protocol to log scan
                        sourceSystem: "mobile_scanner_pwa"
                    });
                    if (scan.id) await markScanSynced(scan.id);
                } catch (e) {
                    console.error("Failed to sync scan", scan, e);
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
                    console.error("Failed to sync photo", photo, e);
                }
            }

            toast({
                title: "Sync Complete",
                description: "All offline data has been uploaded.",
                variant: "default"
            });

        } catch (err) {
            console.error("Sync error", err);
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
    }, [apiKey]); // Re-run if API key changes (user logs in)

    return { isOnline, isSyncing, manualSync: sync };
}
