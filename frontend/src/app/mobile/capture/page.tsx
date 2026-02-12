'use client';

import { useState, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarcodeScanner } from '@/components/mobile/BarcodeScanner';
import { ImageCapture } from '@/components/mobile/ImageCapture';
import { Scan, Camera, Package, ArrowLeft, UploadCloud, CheckCircle, AlertCircle, Loader2, Wifi, WifiOff } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { useIngestFile, useIngestURL } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/use-toast';
import { saveScan, savePhoto } from '@/lib/db';
import { useSync } from '@/hooks/use-sync';

export default function MobileCapturePage() {
    const [activeTab, setActiveTab] = useState('scan');
    const [scannedData, setScannedData] = useState<string[]>([]);
    const [capturedImages, setCapturedImages] = useState<string[]>([]);
    const { apiKey } = useAuth();
    const { toast } = useToast();

    const ingestFileMutation = useIngestFile();
    const ingestUrlMutation = useIngestURL();
    const { isOnline, isSyncing, manualSync } = useSync();

    const handleScan = async (data: string) => {
        const timestamp = new Date().toLocaleTimeString();
        setScannedData(prev => [`[${timestamp}] ${data}`, ...prev]);

        if (!isOnline) {
            await saveScan(data);
            toast({
                title: "Saved Offline",
                description: "Scan saved locally. Will sync when online.",
            });
            return;
        }

        if (!apiKey) return;

        // Online path
        try {
            await ingestUrlMutation.mutateAsync({
                apiKey,
                url: `scan://${data}`,
                sourceSystem: "mobile_scanner_pwa"
            });
            toast({
                title: "Scan Uploaded",
                description: data,
            });
        } catch (e) {
            // Fallback to offline save if request fails
            await saveScan(data);
            toast({
                title: "Upload Failed - Saved Offline",
                description: "Connection error. Saved locally.",
            });
        }
    };

    const handleCapture = async (imageData: string) => {
        setCapturedImages(prev => [imageData, ...prev]);

        // Create Blob/File
        const res = await fetch(imageData);
        const blob = await res.blob();

        if (!isOnline) {
            await savePhoto(blob);
            toast({
                title: "Photo Saved Offline",
                description: "Image saved locally. Will sync when online.",
            });
            return;
        }

        if (!apiKey) {
            toast({
                title: "API Key Missing",
                description: "Please log in or set your API key to upload.",
                variant: "destructive"
            });
            return;
        }

        try {
            const filename = `mobile_capture_${Date.now()}.jpg`;
            const file = new File([blob], filename, { type: 'image/jpeg' });

            toast({
                title: "Uploading Image...",
                description: "Sending to ingestion service.",
            });

            await ingestFileMutation.mutateAsync({
                apiKey,
                file,
                sourceSystem: 'mobile_capture_pwa'
            });

            toast({
                title: "Upload Complete",
                description: "Image successfully sent for analysis.",
                variant: "default"
            });

        } catch (error) {
            console.error("Upload failed", error);
            // Fallback save
            await savePhoto(blob);
            toast({
                title: "Upload Failed - Saved Offline",
                description: "Saved locally for later sync.",
                variant: "destructive"
            });
        }
    };

    return (
        <div className="min-h-screen bg-background pb-20">
            {/* Mobile Header */}
            <div className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="flex h-14 items-center justify-between px-4">
                    <div className="flex items-center gap-4">
                        <Link href="/">
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                                <ArrowLeft className="h-4 w-4" />
                            </Button>
                        </Link>
                        <span className="font-semibold">Field Capture</span>
                    </div>

                    {/* Connectivity Badge */}
                    <div className="flex items-center gap-2">
                        {isSyncing ? (
                            <div className="flex items-center text-xs text-blue-500 animate-pulse">
                                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                Syncing
                            </div>
                        ) : isOnline ? (
                            <div className="flex items-center text-xs text-green-600 bg-green-100 dark:bg-green-900/30 px-2 py-1 rounded-full">
                                <Wifi className="h-3 w-3 mr-1" />
                                Online
                            </div>
                        ) : (
                            <div className="flex items-center text-xs text-amber-600 bg-amber-100 dark:bg-amber-900/30 px-2 py-1 rounded-full">
                                <WifiOff className="h-3 w-3 mr-1" />
                                Offline
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="p-4 max-w-md mx-auto space-y-4">
                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsList className="grid w-full grid-cols-2 mb-8">
                        <TabsTrigger value="scan" className="flex items-center gap-2">
                            <Scan className="h-4 w-4" />
                            Barcode
                        </TabsTrigger>
                        <TabsTrigger value="photo" className="flex items-center gap-2">
                            <Camera className="h-4 w-4" />
                            Photo
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="scan">
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-lg">Scan Item</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <BarcodeScanner onScan={handleScan} />

                                {/* Recent Scans Log */}
                                <div className="mt-6 space-y-2">
                                    <h3 className="text-sm font-medium text-muted-foreground mb-2">Session Log</h3>
                                    {scannedData.length === 0 ? (
                                        <p className="text-xs text-muted-foreground italic text-center py-4">
                                            No items scanned yet
                                        </p>
                                    ) : (
                                        <div className="max-h-40 overflow-y-auto space-y-2">
                                            {scannedData.map((item, i) => (
                                                <div key={i} className="text-sm p-2 bg-muted rounded border flex items-center gap-2">
                                                    <Package className="h-3 w-3 text-primary" />
                                                    <span className="font-mono truncate">{item}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    <TabsContent value="photo">
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-lg">Evidence Capture</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ImageCapture onCapture={handleCapture} />

                                {/* Recent Photos Grid */}
                                {capturedImages.length > 0 && (
                                    <div className="mt-6">
                                        <h3 className="text-sm font-medium text-muted-foreground mb-2">Captured Photos ({capturedImages.length})</h3>
                                        <div className="grid grid-cols-3 gap-2">
                                            {capturedImages.map((src, i) => (
                                                <div key={i} className="aspect-square rounded overflow-hidden border">
                                                    <img src={src} alt="Evidence" className="w-full h-full object-cover" />
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    );
}
