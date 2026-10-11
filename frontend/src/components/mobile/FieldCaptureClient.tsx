'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Camera, Loader2, Package, Scan, Wifi, WifiOff } from 'lucide-react';

import dynamic from 'next/dynamic';

const BarcodeScanner = dynamic(
  () => import('@/components/mobile/BarcodeScanner').then(mod => ({ default: mod.BarcodeScanner })),
  {
    ssr: false,
    loading: () => (
      <div className="relative aspect-square w-full max-w-sm">
        <Skeleton className="h-full w-full rounded-lg" />
        <span className="absolute inset-0 flex items-center justify-center text-small text-re-text-tertiary">
          Loading scanner...
        </span>
      </div>
    ),
  }
);
import { ImageCapture } from '@/components/mobile/ImageCapture';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { useToast } from '@/components/ui/use-toast';
import { useIngestFile } from '@/hooks/use-api';
import { useSync } from '@/hooks/use-sync';
import { useAuth } from '@/lib/auth-context';
import { getServiceURL } from '@/lib/api-config';
import { newScanIdempotencyKey, savePhoto, saveScan } from '@/lib/db';
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

    const { tenantId } = useAuth();
    const { toast } = useToast();
    const { isOnline, isSyncing } = useSync();
    const ingestFileMutation = useIngestFile();
    // The session tenant is the only accepted tenant. A ?tenant_id= URL hint
    // is never trusted: it is caller-controlled and would attribute scans to
    // a tenant the signed-in user may not belong to.
    const effectiveTenantId = tenantId || undefined;

    useEffect(() => {
        const loadCatalog = async () => {
            if (!effectiveTenantId) return;
            try {
                const response = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/products/${effectiveTenantId}`, {
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
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
    }, [effectiveTenantId]);

    const cteLabel = useMemo(
        () => CTE_OPTIONS.find((option) => option.value === selectedCTEType)?.label || selectedCTEType,
        [selectedCTEType],
    );

    const postEventPayload = useCallback(
        async (eventPayload: Record<string, unknown>, idempotencyKey: string) => {
            const response = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    // Same key on the live attempt and every offline replay,
                    // with byte-identical bodies, so a retry replays the first
                    // response instead of recording the scan twice.
                    'Idempotency-Key': idempotencyKey,
                },
                body: JSON.stringify(eventPayload),
            });

            if (!response.ok) {
                const detail = await response.text();
                throw new Error(detail || `Ingest failed with status ${response.status}`);
            }
        },
        [],
    );

    const handleScan = async (rawScan: string) => {
        // Refuse scans until the session carries a tenant. URL hints are
        // ignored, so there is no tenant to attribute the scan to yet.
        if (!tenantId) {
            toast({
                title: 'Tenant required',
                description: 'Sign in with a tenant before capturing scans.',
                variant: 'destructive',
            });
            return;
        }

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

        // Build the ingest payload once so the live attempt and any offline
        // replay send byte-identical bodies under one idempotency key.
        const traceabilityLotCode =
            parsedState.traceabilityLotCode ||
            parsedState.serial ||
            parsedState.gtin ||
            `SCAN-${Date.now()}`;

        const idempotencyKey = newScanIdempotencyKey();
        const eventPayload = {
            source: 'mobile_scanner_pwa',
            tenant_id: tenantId,
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
            await saveScan(rawScan, eventPayload, parsedState.cteType, idempotencyKey);
            toast({
                title: 'Saved Offline',
                description: 'Scan saved locally. Will sync when online.',
            });
            return;
        }

        try {
            await postEventPayload(eventPayload, idempotencyKey);
            toast({
                title: 'Scan Ingested',
                description: parsedState.traceabilityLotCode || parsedState.gtin || parsedState.raw,
            });
        } catch {
            await saveScan(rawScan, eventPayload, parsedState.cteType, idempotencyKey);
            toast({
                title: 'Upload Failed - Saved Offline',
                description: 'Connection error. Scan saved locally.',
                variant: 'destructive',
            });
        }
    };

    const handleCapture = async (imageData: string) => {
        setCapturedImages((prev) => [imageData, ...prev]);

        const res = await fetchWithCsrf(imageData);
        const blob = await res.blob();

        // No session tenant means the vision event cannot be attributed, so
        // keep the photo in the offline queue instead of ingesting it.
        if (!tenantId) {
            await savePhoto(blob);
            toast({
                title: 'Tenant required',
                description: 'Photo saved locally. Sign in with a tenant to sync it.',
                variant: 'destructive',
            });
            return;
        }

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

            const visionRes = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/vision/analyze-label`, {
                method: 'POST',
                credentials: 'include',
                body: formData,
            });

            if (visionRes.ok) {
                const visionData = await visionRes.json();
                const productName = visionData.product_name || 'Photo capture';
                const lotCode = visionData.lot_code || visionData.gtin || `PHOTO-${Date.now()}`;

                const payload = {
                    source: 'mobile_capture_pwa_vision',
                    tenant_id: tenantId,
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
                const ingestRes = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'Idempotency-Key': newScanIdempotencyKey(),
                    },
                    body: JSON.stringify(payload),
                });
                if (!ingestRes.ok) {
                    const detail = await ingestRes.text().catch(() => '');
                    throw new Error(detail || `Event persistence failed with status ${ingestRes.status}`);
                }

                toast({
                    title: 'Label Analyzed & Ingested',
                    description: `${productName} — ${visionData.fsma_kdes?.length || 0} KDEs extracted`,
                });
            } else {
                // Vision failed — fall back to raw file upload
                await ingestFileMutation.mutateAsync({ file, sourceSystem: 'mobile_capture_pwa' });
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
        <div className="min-h-screen bg-re-surface-base pb-20">
            <div className="sticky top-0 z-50 w-full border-b border-re-border-subtle bg-re-surface-base/95 backdrop-blur">
                <div className="flex h-14 items-center justify-between px-4">
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="icon" className="h-11 w-11" aria-label="Field Capture" asChild>
                            <Link href="/">
                                <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <span className="text-subheading text-re-text-primary">Field Capture</span>
                    </div>

                    <div className="flex items-center gap-2">
                        {isSyncing ? (
                            <Badge tone="info" size="sm">
                                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
                                Syncing
                            </Badge>
                        ) : isOnline ? (
                            <Badge tone="success" size="sm">
                                <Wifi className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                Online
                            </Badge>
                        ) : (
                            <Badge tone="warning" size="sm">
                                <WifiOff className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                Offline
                            </Badge>
                        )}
                    </div>
                </div>
            </div>

            <div className="p-4 max-w-md mx-auto space-y-4">
                {!tenantId && (
                    <Card role="alert">
                        <CardContent>
                            <p className="text-small text-re-text-secondary">
                                Tenant required. Sign in with a tenant before capturing scans.
                                URL tenant hints are ignored.
                            </p>
                        </CardContent>
                    </Card>
                )}
                <Card>
                    <CardHeader>
                        <CardTitle>CTE Type</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <label htmlFor="cte-type" className="sr-only">CTE Type</label>
                        <select
                            id="cte-type"
                            value={selectedCTEType}
                            onChange={(event) => setSelectedCTEType(event.target.value as CaptureCTEType)}
                            className={cn(fieldControlClasses, 'h-11')}
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
                    <TabsList className="flex w-full gap-6">
                        <TabsTrigger value="scan" className="h-11">
                            <Scan className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            Barcode
                        </TabsTrigger>
                        <TabsTrigger value="photo" className="h-11">
                            <Camera className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            Photo
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="scan">
                        <Card>
                            <CardHeader>
                                <CardTitle>Scan Item</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <BarcodeScanner onScan={handleScan} />

                                {/* Manual entry fallback */}
                                <div className="mt-4">
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        aria-expanded={showManualEntry}
                                        onClick={() => setShowManualEntry(!showManualEntry)}
                                    >
                                        <Keyboard className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                        {showManualEntry ? 'Hide manual entry' : 'Camera not working? Enter manually'}
                                    </Button>
                                    {showManualEntry && (
                                        <div className="mt-2 space-y-2 rounded-md border border-re-border bg-re-surface-inset p-3">
                                            <label htmlFor="manual-gtin" className="sr-only">
                                                GTIN
                                            </label>
                                            <Input
                                                id="manual-gtin"
                                                size="lg"
                                                mono
                                                type="text"
                                                placeholder="GTIN (e.g. 00012345678905)"
                                                value={manualGtin}
                                                onChange={(e) => setManualGtin(e.target.value)}
                                            />
                                            <label htmlFor="manual-lot" className="sr-only">
                                                Lot / Batch Code
                                            </label>
                                            <Input
                                                id="manual-lot"
                                                size="lg"
                                                mono
                                                type="text"
                                                placeholder="Lot / Batch Code"
                                                value={manualLot}
                                                onChange={(e) => setManualLot(e.target.value)}
                                            />
                                            <Button
                                                size="lg"
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
                                    <div className="mt-4 space-y-1 rounded-md border border-re-border bg-re-surface-card p-3 text-small text-re-text-secondary">
                                        <div><span className="font-medium text-re-text-primary">CTE:</span> {cteLabel}</div>
                                        <div><span className="font-medium text-re-text-primary">GTIN:</span> <span className="font-mono">{lastParsedScan.gtin || '-'}</span></div>
                                        <div><span className="font-medium text-re-text-primary">TLC:</span> <span className="font-mono">{lastParsedScan.traceabilityLotCode || '-'}</span></div>
                                        <div><span className="font-medium text-re-text-primary">Serial:</span> <span className="font-mono">{lastParsedScan.serial || '-'}</span></div>
                                        <div><span className="font-medium text-re-text-primary">Expiry:</span> <span className="font-mono">{lastParsedScan.expiryDate || '-'}</span></div>
                                        <div><span className="font-medium text-re-text-primary">Pack Date:</span> <span className="font-mono">{lastParsedScan.packDate || '-'}</span></div>
                                        <div><span className="font-medium text-re-text-primary">Product:</span> {lastParsedScan.productDescription}</div>
                                    </div>
                                )}

                                <div className="mt-6 space-y-2">
                                    <h3 className="mb-2 text-label text-re-text-muted">Session Log</h3>
                                    {scannedData.length === 0 ? (
                                        <EmptyState bare size="sm" title="No items scanned yet" />
                                    ) : (
                                        <div className="max-h-40 space-y-2 overflow-y-auto">
                                            {scannedData.map((item, index) => (
                                                <div
                                                    key={index}
                                                    className="flex items-center gap-2 rounded-md border border-re-border bg-re-surface-inset p-2 text-ui"
                                                >
                                                    <Package className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                    <span className="truncate font-mono text-[0.8125rem] text-re-text-secondary">{item}</span>
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
                            <CardHeader>
                                <CardTitle>Evidence Capture</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ImageCapture onCapture={handleCapture} />

                                {capturedImages.length > 0 && (
                                    <div className="mt-6">
                                        <h3 className="mb-2 text-label text-re-text-muted">
                                            Captured Photos ({capturedImages.length})
                                        </h3>
                                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                                            {capturedImages.map((src, index) => (
                                                <div key={index} className="aspect-square overflow-hidden rounded-md border border-re-border">
                                                    <img src={src} alt="Evidence" className="h-full w-full object-cover" />
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
