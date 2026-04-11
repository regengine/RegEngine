'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Camera, Loader2, Package, Scan, Wifi, WifiOff } from 'lucide-react';

import dynamic from 'next/dynamic';

const BarcodeScanner = dynamic(
  () => import('@/components/mobile/BarcodeScanner').then(mod => ({ default: mod.BarcodeScanner })),
  {
    ssr: false,
    loading: () => (
      <div className="w-full max-w-sm aspect-square bg-muted rounded-lg animate-pulse flex items-center justify-center">
        <span className="text-xs text-muted-foreground">Loading scanner...</span>
      </div>
    ),
  }
);
import { ImageCapture } from '@/components/mobile/ImageCapture';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { useIngestFile } from '@/hooks/use-api';
import { useSync } from '@/hooks/use-sync';
import { useAuth } from '@/lib/auth-context';
import { getServiceURL } from '@/lib/api-config';
import { savePhoto, saveScan } from '@/lib/db';
import { parseGS1 } from '@/lib/gs1-parser';
import { Keyboard } from 'lucide-react';

type CaptureCTEType = 'shipping' | 'receiving' | 'transformation';

interface ProductRecord {
    name?: string;
    gtin?: string;
    description?: string;
}

interface ProductCatalogResponse {
    products?: ProductRecord[];
}

interface ParsedScanState {
    cteType: CaptureCTEType;
    raw: string;
    gtin?: string;
    traceabilityLotCode?: string;
    serial?: string;
    expiryDate?: string;
    packDate?: string;
    productDescription: string;
    validGTIN?: boolean;
}

const CTE_OPTIONS: Array<{ value: CaptureCTEType; label: string }> = [
    { value: 'shipping', label: 'Shipping' },
    { value: 'receiving', label: 'Receiving' },
    { value: 'transformation', label: 'Transformation' },
];

function resolveProductDescription(
    parsed: ReturnType<typeof parseGS1>,
    catalogByGtin: Record<string, string>,
): string {
    if (parsed.gtin && catalogByGtin[parsed.gtin]) {
        return catalogByGtin[parsed.gtin];
    }
    if (parsed.tlc) {
        return `Scanned lot ${parsed.tlc}`;
    }
    if (parsed.gtin) {
        return `Scanned GTIN ${parsed.gtin}`;
    }
    return 'Scanned product';
}

export function FieldCaptureClient() {
    const [activeTab, setActiveTab] = useState('scan');
    const [selectedCTEType, setSelectedCTEType] = useState<CaptureCTEType>('shipping');
    const [scannedData, setScannedData] = useState<string[]>([]);
    const [capturedImages, setCapturedImages] = useState<string[]>([]);
    const [lastParsedScan, setLastParsedScan] = useState<ParsedScanState | null>(null);
    const [catalogByGtin, setCatalogByGtin] = useState<Record<string, string>>({});
    const [showManualEntry, setShowManualEntry] = useState(false);
    const [manualGtin, setManualGtin] = useState('');
    const [manualLot, setManualLot] = useState('');

    const { apiKey, tenantId } = useAuth();
    const { toast } = useToast();
    const { isOnline, isSyncing } = useSync();
    const ingestFileMutation = useIngestFile();

    useEffect(() => {
        const loadCatalog = async () => {
            if (!apiKey || !tenantId) return;
            try {
                const response = await fetch(`${getServiceURL('ingestion')}/api/v1/products/${tenantId}`, {
                    headers: {
                        'Content-Type': 'application/json',
                        'X-RegEngine-API-Key': apiKey,
                    },
                });
                if (!response.ok) return;

                const payload = (await response.json()) as ProductCatalogResponse;
                const byGtin: Record<string, string> = {};
                for (const product of payload.products || []) {
                    if (!product.gtin) continue;
                    byGtin[product.gtin] = product.description || product.name || 'Catalog product';
                }
                setCatalogByGtin(byGtin);
            } catch {
                // Product lookup is best-effort. Capture flow still works without it.
            }
        };

        void loadCatalog();
    }, [apiKey, tenantId]);

    const cteLabel = useMemo(
        () => CTE_OPTIONS.find((option) => option.value === selectedCTEType)?.label || selectedCTEType,
        [selectedCTEType],
    );

    const ingestScannedEvent = useCallback(
        async (scanState: ParsedScanState) => {
            if (!apiKey) throw new Error('Missing API key');

            const traceabilityLotCode =
                scanState.traceabilityLotCode ||
                scanState.serial ||
                scanState.gtin ||
                `SCAN-${Date.now()}`;

            const eventPayload = {
                source: 'mobile_scanner_pwa',
                tenant_id: tenantId || undefined,
                events: [
                    {
                        cte_type: scanState.cteType,
                        traceability_lot_code: traceabilityLotCode,
                        product_description: scanState.productDescription,
                        quantity: 1,
                        unit_of_measure: 'cases',
                        timestamp: new Date().toISOString(),
                        location_name: 'Field Capture Mobile',
                        kdes: {
                            gtin: scanState.gtin,
                            serial: scanState.serial,
                            expiry_date: scanState.expiryDate,
                            pack_date: scanState.packDate,
                            raw_scan: scanState.raw,
                        },
                    },
                ],
            };

            const response = await fetch(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-RegEngine-API-Key': apiKey,
                    ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
                },
                body: JSON.stringify(eventPayload),
            });

            if (!response.ok) {
                const detail = await response.text();
                throw new Error(detail || `Ingest failed with status ${response.status}`);
            }
        },
        [apiKey, tenantId],
    );

    const handleScan = async (rawScan: string) => {
        const parsed = parseGS1(rawScan);
        const productDescription = resolveProductDescription(parsed, catalogByGtin);

        const parsedState: ParsedScanState = {
            cteType: selectedCTEType,
            raw: rawScan,
            gtin: parsed.gtin,
            traceabilityLotCode: parsed.tlc,
            serial: parsed.serial,
            expiryDate: parsed.expiryDate,
            packDate: parsed.packDate,
            productDescription,
            validGTIN: parsed.isValidGTIN,
        };
        setLastParsedScan(parsedState);

        const timestamp = new Date().toLocaleTimeString();
        setScannedData((prev) => [`[${timestamp}] ${cteLabel}: ${rawScan}`, ...prev]);

        // Build the ingest payload so we can replay it offline
        const traceabilityLotCode =
            parsedState.traceabilityLotCode ||
            parsedState.serial ||
            parsedState.gtin ||
            `SCAN-${Date.now()}`;

        const offlinePayload = {
            source: 'mobile_scanner_pwa',
            tenant_id: tenantId || undefined,
            events: [
                {
                    cte_type: parsedState.cteType,
                    traceability_lot_code: traceabilityLotCode,
                    product_description: parsedState.productDescription,
                    quantity: 1,
                    unit_of_measure: 'cases',
                    timestamp: new Date().toISOString(),
                    location_name: 'Field Capture Mobile',
                    kdes: {
                        gtin: parsedState.gtin,
                        serial: parsedState.serial,
                        expiry_date: parsedState.expiryDate,
                        pack_date: parsedState.packDate,
                        raw_scan: parsedState.raw,
                    },
                },
            ],
        };

        if (!isOnline) {
            await saveScan(rawScan, offlinePayload, parsedState.cteType);
            toast({
                title: 'Saved Offline',
                description: 'Scan saved locally. Will sync when online.',
            });
            return;
        }

        if (!apiKey) {
            await saveScan(rawScan, offlinePayload, parsedState.cteType);
            toast({
                title: 'API Key Missing',
                description: 'Scan saved locally. Set your API key to sync.',
                variant: 'destructive',
            });
            return;
        }

        try {
            await ingestScannedEvent(parsedState);
            toast({
                title: 'Scan Ingested',
                description: parsedState.traceabilityLotCode || parsedState.gtin || parsedState.raw,
            });
        } catch {
            await saveScan(rawScan, offlinePayload, parsedState.cteType);
            toast({
                title: 'Upload Failed - Saved Offline',
                description: 'Connection error. Scan saved locally.',
                variant: 'destructive',
            });
        }
    };

    const handleCapture = async (imageData: string) => {
        setCapturedImages((prev) => [imageData, ...prev]);

        const res = await fetch(imageData);
        const blob = await res.blob();

        if (!isOnline) {
            await savePhoto(blob);
            toast({
                title: 'Photo Saved Offline',
                description: 'Image saved locally. Will sync when online.',
            });
            return;
        }

        // Send through label vision endpoint for AI extraction
        const filename = `mobile_capture_${Date.now()}.jpg`;
        const file = new File([blob], filename, { type: 'image/jpeg' });

        try {
            const formData = new FormData();
            formData.append('file', file);

            toast({ title: 'Analyzing Label...', description: 'Running computer vision extraction.' });

            const visionRes = await fetch(`${getServiceURL('ingestion')}/api/v1/vision/analyze-label`, {
                method: 'POST',
                body: formData,
            });

            if (visionRes.ok) {
                const visionData = await visionRes.json();
                const productName = visionData.product_name || 'Photo capture';
                const lotCode = visionData.lot_code || visionData.gtin || `PHOTO-${Date.now()}`;

                // Auto-ingest the extracted data if authenticated
                if (apiKey) {
                    const payload = {
                        source: 'mobile_capture_pwa_vision',
                        tenant_id: tenantId || undefined,
                        events: [{
                            cte_type: selectedCTEType,
                            traceability_lot_code: lotCode,
                            product_description: productName,
                            quantity: 1,
                            unit_of_measure: 'cases',
                            timestamp: new Date().toISOString(),
                            location_name: 'Field Capture Mobile (Photo)',
                            kdes: {
                                gtin: visionData.gtin || undefined,
                                lot_code: visionData.lot_code || undefined,
                                expiry_date: visionData.expiry_date || undefined,
                                pack_date: visionData.pack_date || undefined,
                                brand: visionData.brand || undefined,
                                facility_name: visionData.facility_name || undefined,
                            },
                        }],
                    };
                    const ingestRes = await fetch(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-RegEngine-API-Key': apiKey,
                            ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
                        },
                        body: JSON.stringify(payload),
                    });
                    if (!ingestRes.ok) {
                        const detail = await ingestRes.text().catch(() => '');
                        throw new Error(detail || `Event persistence failed with status ${ingestRes.status}`);
                    }
                }

                toast({
                    title: 'Label Analyzed & Ingested',
                    description: `${productName} — ${visionData.fsma_kdes?.length || 0} KDEs extracted`,
                });
            } else {
                // Vision failed — fall back to raw file upload
                if (apiKey) {
                    await ingestFileMutation.mutateAsync({ apiKey, file, sourceSystem: 'mobile_capture_pwa' });
                }
                toast({ title: 'Photo Uploaded', description: 'Vision analysis unavailable — raw image stored.' });
            }
        } catch {
            await savePhoto(blob);
            toast({
                title: 'Upload Failed - Saved Offline',
                description: 'Saved locally for later sync.',
                variant: 'destructive',
            });
        }
    };

    return (
        <div className="min-h-screen bg-background pb-20">
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

                    <div className="flex items-center gap-2">
                        {isSyncing ? (
                            <div className="flex items-center text-xs text-re-info animate-pulse">
                                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                Syncing
                            </div>
                        ) : isOnline ? (
                            <div className="flex items-center text-xs text-re-success bg-re-success-muted dark:bg-re-success/30 px-2 py-1 rounded-full">
                                <Wifi className="h-3 w-3 mr-1" />
                                Online
                            </div>
                        ) : (
                            <div className="flex items-center text-xs text-re-warning bg-re-warning-muted dark:bg-re-warning/30 px-2 py-1 rounded-full">
                                <WifiOff className="h-3 w-3 mr-1" />
                                Offline
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="p-4 max-w-md mx-auto space-y-4">
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base">CTE Type</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0">
                        <select
                            value={selectedCTEType}
                            onChange={(event) => setSelectedCTEType(event.target.value as CaptureCTEType)}
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        >
                            {CTE_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>
                                    {option.label}
                                </option>
                            ))}
                        </select>
                    </CardContent>
                </Card>

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

                                {/* Manual entry fallback */}
                                <div className="mt-4">
                                    <button
                                        type="button"
                                        onClick={() => setShowManualEntry(!showManualEntry)}
                                        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors"
                                    >
                                        <Keyboard className="h-3 w-3" />
                                        {showManualEntry ? 'Hide manual entry' : 'Camera not working? Enter manually'}
                                    </button>
                                    {showManualEntry && (
                                        <div className="mt-2 space-y-2 p-3 rounded-md border bg-muted/30">
                                            <input
                                                type="text"
                                                placeholder="GTIN (e.g. 00012345678905)"
                                                value={manualGtin}
                                                onChange={(e) => setManualGtin(e.target.value)}
                                                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                                            />
                                            <input
                                                type="text"
                                                placeholder="Lot / Batch Code"
                                                value={manualLot}
                                                onChange={(e) => setManualLot(e.target.value)}
                                                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                                            />
                                            <Button
                                                size="sm"
                                                className="w-full"
                                                disabled={!manualGtin && !manualLot}
                                                onClick={() => {
                                                    const raw = manualGtin || manualLot;
                                                    handleScan(raw);
                                                    setManualGtin('');
                                                    setManualLot('');
                                                }}
                                            >
                                                Submit Manual Entry
                                            </Button>
                                        </div>
                                    )}
                                </div>

                                {lastParsedScan && (
                                    <div className="mt-4 rounded-md border p-3 text-xs space-y-1">
                                        <div><span className="font-semibold">CTE:</span> {cteLabel}</div>
                                        <div><span className="font-semibold">GTIN:</span> {lastParsedScan.gtin || '-'}</div>
                                        <div><span className="font-semibold">TLC:</span> {lastParsedScan.traceabilityLotCode || '-'}</div>
                                        <div><span className="font-semibold">Serial:</span> {lastParsedScan.serial || '-'}</div>
                                        <div><span className="font-semibold">Expiry:</span> {lastParsedScan.expiryDate || '-'}</div>
                                        <div><span className="font-semibold">Pack Date:</span> {lastParsedScan.packDate || '-'}</div>
                                        <div><span className="font-semibold">Product:</span> {lastParsedScan.productDescription}</div>
                                    </div>
                                )}

                                <div className="mt-6 space-y-2">
                                    <h3 className="text-sm font-medium text-muted-foreground mb-2">Session Log</h3>
                                    {scannedData.length === 0 ? (
                                        <p className="text-xs text-muted-foreground italic text-center py-4">
                                            No items scanned yet
                                        </p>
                                    ) : (
                                        <div className="max-h-40 overflow-y-auto space-y-2">
                                            {scannedData.map((item, index) => (
                                                <div
                                                    key={index}
                                                    className="text-sm p-2 bg-muted rounded border flex items-center gap-2"
                                                >
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

                                {capturedImages.length > 0 && (
                                    <div className="mt-6">
                                        <h3 className="text-sm font-medium text-muted-foreground mb-2">
                                            Captured Photos ({capturedImages.length})
                                        </h3>
                                        <div className="grid grid-cols-3 gap-2">
                                            {capturedImages.map((src, index) => (
                                                <div key={index} className="aspect-square rounded overflow-hidden border">
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
