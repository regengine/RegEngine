'use client';

import React, { useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import {
    Upload,
    FileSpreadsheet,
    Thermometer,
    Code2,
    Download,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Copy,
    ArrowRight,
    Loader2,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import type { IngestCSVResponse } from '@/types/api';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { toast } from '@/components/ui/use-toast';
import { ColumnSuggestionList } from '@/components/fsma/ColumnSuggestionList';
import { CteSuggestionPrompt } from '@/components/fsma/CteSuggestionPrompt';
import {
    columnSuggestions,
    columnSuggestionsFromUploadError,
    type ColumnSuggestion,
} from '@/lib/column-suggestions';
import { cteSuggestionFromUploadError, type ActionableCteSuggestion } from '@/lib/cte-suggestion';
import { trackToolRunStarted, trackToolRunCompleted } from '@/lib/conversion-events';
import { usePostHog } from '@/lib/posthog-provider';

const CTE_TYPES = [
    { id: 'harvesting', label: 'Harvesting', description: 'Farm harvest events' },
    { id: 'cooling', label: 'Cooling', description: 'Cold storage/cooling events' },
    { id: 'initial_packing', label: 'Initial Packing', description: 'Packing line events' },
    { id: 'first_land_based_receiving', label: 'First Land-Based Receiving', description: 'Seafood landing events' },
    { id: 'shipping', label: 'Shipping', description: 'Outbound shipment events' },
    { id: 'receiving', label: 'Receiving', description: 'Inbound receipt events' },
    { id: 'transformation', label: 'Transformation', description: 'Processing/mixing events' },
];

const EXAMPLE_CURL = `curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "Content-Type: application/json" \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "Idempotency-Key: <unique-request-id>" \\
  -d '{
    "source": "erp",
    "events": [
      {
        "cte_type": "shipping",
        "traceability_lot_code": "<traceability-lot-code>",
        "product_description": "<product-description>",
        "quantity": <quantity-number>,
        "unit_of_measure": "<unit-of-measure>",
        "location_gln": "<your-13-digit-gln>",
        "location_name": "<your-location-name>",
        "timestamp": "<iso-8601-timestamp>",
        "kdes": {
          "ship_date": "<yyyy-mm-dd>",
          "ship_from_location": "<ship-from-location>",
          "ship_to_location": "<ship-to-location>",
          "reference_document": "<bol-or-invoice-number>",
          "tlc_source_reference": "<tlc-source-location-or-gln>"
        }
      }
    ]
  }'`;

type TabId = 'csv' | 'iot' | 'api';
type UploadState = 'idle' | 'uploading' | 'success' | 'partial' | 'error';

export function DataImportClient() {
    const { apiKey } = useAuth();
    const posthog = usePostHog();
    const [activeTab, setActiveTab] = useState<TabId>('csv');
    const [copied, setCopied] = useState(false);

    // Real file upload state
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [uploadState, setUploadState] = useState<UploadState>('idle');
    const [uploadResult, setUploadResult] = useState<{
        data?: IngestCSVResponse;
        error?: string;
        cteSuggestion?: ActionableCteSuggestion | null;
        columnSuggestions?: ColumnSuggestion[];
    } | null>(null);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isDragging, setIsDragging] = useState(false);

    const handleCopy = useCallback(() => {
        navigator.clipboard.writeText(EXAMPLE_CURL);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, []);

    const handleFileChange = useCallback((file: File | null) => {
        if (!file) return;

        const VALID_EXTENSIONS = ['.csv'];
        const MAX_SIZE_MB = 5;
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();

        if (!VALID_EXTENSIONS.includes(ext)) {
            toast({
                variant: 'destructive',
                title: 'Invalid file type',
                description: `Only CSV files are supported. You selected a ${ext} file.`,
            });
            return;
        }

        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
            toast({
                variant: 'destructive',
                title: 'File too large',
                description: `Maximum file size is ${MAX_SIZE_MB} MB. Your file is ${(file.size / (1024 * 1024)).toFixed(1)} MB.`,
            });
            return;
        }

        setSelectedFile(file);
        setUploadState('idle');
        setUploadResult(null);
    }, []);

    // One upload at a time. The result panel animates out, so its buttons stay
    // mounted and clickable for a moment after a click: state alone cannot stop
    // a second click from storing the same file twice.
    const uploadInFlightRef = useRef(false);

    // ``cteType`` is set only by the "Import as <CTE>" prompt: the uploader
    // confirming the CTE Jev suggested for a file the server rejected.
    const handleUpload = useCallback(async (cteType?: string) => {
        if (!selectedFile || uploadInFlightRef.current) return;
        uploadInFlightRef.current = true;
        trackToolRunStarted('data-import');
        posthog?.capture('tool_started', { tool_id: 'data-import' });
        setUploadState('uploading');
        setUploadResult(null);
        try {
            const effectiveKey = apiKey || '';
            const result = await apiClient.ingestFile(effectiveKey, selectedFile, 'data_import_hub', cteType);
            setUploadResult({ data: result });
            setUploadState(result.accepted === 0 ? 'error' : result.rejected > 0 ? 'partial' : 'success');
            trackToolRunCompleted('data-import', result.accepted === 0 ? 'error' : 'success');
        } catch (err: unknown) {
            setUploadResult({
                error: err instanceof Error ? err.message : 'Upload failed',
                // A declared CTE is never second-guessed.
                cteSuggestion: cteType ? null : cteSuggestionFromUploadError(err),
                columnSuggestions: columnSuggestionsFromUploadError(err),
            });
            setUploadState('error');
            trackToolRunCompleted('data-import', 'error');
        } finally {
            uploadInFlightRef.current = false;
        }
    }, [selectedFile, apiKey, posthog]);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFileChange(file);
    }, [handleFileChange]);

    const tabs: { id: TabId; label: string; icon: React.ElementType }[] = [
        { id: 'csv', label: 'CSV Upload', icon: FileSpreadsheet },
        { id: 'iot', label: 'IoT Import', icon: Thermometer },
        { id: 'api', label: 'API Guide', icon: Code2 },
    ];

    return (
        <FreeToolPageShell
            title="Data Import Hub"
            subtitle="Get your traceability data into RegEngine. Upload CSV files for Critical Tracking Events, or connect via the JSON events API. Live today: CSV upload and the JSON events API. Other connectors are Beta or Preview."
            relatedToolIds={['ftl-checker', 'cte-mapper', 'kde-checker']}
        >
            <LeadGate
                source="data-import"
                headline="Unlock the Data Import Hub"
                subheadline="Upload CSV files for Critical Tracking Events, or connect via the JSON events API to start building your traceability records. Live today: CSV upload and the JSON events API. Other connectors are Beta or Preview."
                ctaText="Access Import Tools"
                teaser={
                    <Card padding="spacious" className="text-center">
                        <Upload className="mx-auto mb-3 h-6 w-6 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                        <p className="text-subheading text-re-text-primary">Three Ways to Import</p>
                        <p className="mt-2 text-ui text-re-text-secondary">CSV upload with templates for every Critical Tracking Event (CTE) type, and the JSON events API. Live today: CSV upload and the JSON events API. Other connectors are Beta or Preview.</p>
                    </Card>
                }
            >
                <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabId)} className="w-full">
                    <TabsList className="mb-2 max-w-full overflow-x-auto">
                        {tabs.map((tab) => (
                            <TabsTrigger key={tab.id} value={tab.id}>
                                <tab.icon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                {tab.label}
                            </TabsTrigger>
                        ))}
                    </TabsList>

                    {/* CSV Upload Tab */}
                    <TabsContent value="csv" className="space-y-8">
                        {/* Step 1: Download Template */}
                        <Card>
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-inset font-mono uppercase text-label text-re-text-secondary">
                                        1
                                    </span>
                                    <div>
                                        <CardTitle>Download CSV Template</CardTitle>
                                        <CardDescription>
                                            Select the CTE type you&apos;re recording, then download the template with pre-filled headers.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
                                    {CTE_TYPES.map((cte) => (
                                        <a
                                            key={cte.id}
                                            href={`/api/v1/templates/${cte.id}`}
                                            download
                                            className="group flex items-center justify-between gap-3 rounded-md border border-re-border bg-re-surface-card p-3 no-underline transition-colors duration-120 hover:border-re-border-strong hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none"
                                        >
                                            <div className="min-w-0">
                                                <div className="text-ui font-medium text-re-text-primary">
                                                    {cte.label}
                                                </div>
                                                <div className="text-small text-re-text-tertiary">
                                                    {cte.description}
                                                </div>
                                            </div>
                                            <Download className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        </a>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Step 2: Upload */}
                        <Card>
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-inset font-mono uppercase text-label text-re-text-secondary">
                                        2
                                    </span>
                                    <div>
                                        <CardTitle>Upload Filled CSV</CardTitle>
                                        <CardDescription>
                                            Fill in your data, then upload. Events are validated and SHA-256 hashed automatically.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {/* Hidden file input */}
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".csv,text/csv"
                                    aria-label="Upload CSV file"
                                    title="Upload CSV file"
                                    className="hidden"
                                    onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                                />

                                {/* Drop zone */}
                                <div
                                    className={cn(
                                        'cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors duration-120 motion-reduce:transition-none sm:p-12',
                                        isDragging || selectedFile
                                            ? 'border-re-border-strong bg-re-surface-inset'
                                            : 'border-re-border hover:border-re-border-strong'
                                    )}
                                    onClick={() => fileInputRef.current?.click()}
                                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                                    onDragLeave={() => setIsDragging(false)}
                                    onDrop={handleDrop}
                                >
                                    {selectedFile ? (
                                        <>
                                            <CheckCircle2 className="mx-auto mb-4 h-6 w-6 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                            <div className="mb-1 text-ui font-medium text-re-text-primary">{selectedFile.name}</div>
                                            <div className="text-small text-re-text-tertiary">
                                                {(selectedFile.size / 1024).toFixed(1)} KB. Click to change
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <Upload className="mx-auto mb-4 h-6 w-6 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                            <div className="mb-1 text-ui font-medium text-re-text-primary">
                                                Upload a CSV to get started
                                            </div>
                                            <div className="mb-1 text-small text-re-text-secondary">
                                                Drag and drop your CSV here, or click to browse
                                            </div>
                                            <div className="text-small text-re-text-tertiary">
                                                Supports .csv files up to 5MB
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Upload button */}
                                {selectedFile && (
                                    <Button
                                        onClick={() => void handleUpload()}
                                        disabled={uploadState === 'uploading'}
                                        size="lg"
                                        className="w-full"
                                        leadingIcon={
                                            uploadState === 'uploading'
                                                ? <Loader2 className="animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
                                                : <Upload strokeWidth={1.75} aria-hidden="true" />
                                        }
                                    >
                                        {uploadState === 'uploading' ? 'Uploading…' : 'Submit to Ingestion Pipeline'}
                                    </Button>
                                )}

                                {/* Upload result */}
                                <AnimatePresence>
                                    {uploadResult && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 6 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0 }}
                                        >
                                            <Callout
                                                tone={uploadState === 'success' ? 'success' : uploadState === 'partial' ? 'warning' : 'danger'}
                                                role={uploadState === 'error' ? 'alert' : 'status'}
                                                icon={uploadState === 'success' ? CheckCircle2 : uploadState === 'partial' ? AlertTriangle : XCircle}
                                                title={
                                                    uploadState === 'success'
                                                        ? 'CSV processed'
                                                        : uploadState === 'partial'
                                                            ? 'CSV partially accepted'
                                                            : uploadResult.data ? 'No rows accepted' : 'Upload failed'
                                                }
                                            >
                                                {uploadResult.data && (
                                                    <>
                                                        <p>{uploadResult.data.accepted} of {uploadResult.data.total} rows accepted; {uploadResult.data.rejected} rejected.</p>
                                                        {uploadResult.data.events.filter(event => event.status === 'rejected').flatMap(event => event.errors).map((error, index) => (
                                                            <p key={index} className="mt-2 text-small">{error}</p>
                                                        ))}
                                                        {uploadResult.data.kde_warnings?.map((warning, index) => (
                                                            <p key={index} className="mt-2 text-small">{warning}</p>
                                                        ))}
                                                        <ColumnSuggestionList
                                                            suggestions={columnSuggestions(uploadResult.data.header_mapping_suggestions)}
                                                        />
                                                    </>
                                                )}
                                                {uploadResult.error && (
                                                    <div className="text-small">{uploadResult.error}</div>
                                                )}
                                                {uploadResult.columnSuggestions && (
                                                    <ColumnSuggestionList suggestions={uploadResult.columnSuggestions} />
                                                )}
                                                {uploadResult.cteSuggestion && (
                                                    <CteSuggestionPrompt
                                                        suggestion={uploadResult.cteSuggestion}
                                                        disabled={uploadState === 'uploading'}
                                                        onImport={(cte) => void handleUpload(cte)}
                                                    />
                                                )}
                                            </Callout>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* IoT Import Tab */}
                    <TabsContent value="iot" className="space-y-6">
                        <Card>
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <Thermometer className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <div>
                                        <CardTitle>Sensitech TempTale (Beta)</CardTitle>
                                        <CardDescription>
                                            Sensitech CSV import exists in experimental routers and is not on the production allowlist. Do not market it as Live.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                                    <Card variant="inset" padding="compact">
                                        <div className="mb-2 flex items-center gap-2 text-ui font-medium text-re-text-primary">
                                            <CheckCircle2 className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                            Auto-Detection
                                        </div>
                                        <div className="text-small text-re-text-tertiary">
                                            Automatically detects column format from Sensitech CSV exports
                                        </div>
                                    </Card>
                                    <Card variant="inset" padding="compact">
                                        <div className="mb-2 flex items-center gap-2 text-ui font-medium text-re-text-primary">
                                            <AlertTriangle className="h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                            Excursion Detection
                                        </div>
                                        <div className="text-small text-re-text-tertiary">
                                            Flags any readings exceeding cold chain thresholds (default: 5°C)
                                        </div>
                                    </Card>
                                    <Card variant="inset" padding="compact">
                                        <div className="mb-2 flex items-center gap-2 text-ui font-medium text-re-text-primary">
                                            <CheckCircle2 className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                            TLC Linking
                                        </div>
                                        <div className="text-small text-re-text-tertiary">
                                            Links temperature data to specific Traceability Lot Codes
                                        </div>
                                    </Card>
                                </div>

                                <div className="rounded-lg border-2 border-dashed border-re-border p-8 text-center transition-colors duration-120 hover:border-re-border-strong motion-reduce:transition-none sm:p-12">
                                    <Thermometer className="mx-auto mb-4 h-6 w-6 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <div className="mb-1 text-ui font-medium text-re-text-primary">
                                        Upload Sensitech TempTale CSV
                                    </div>
                                    <div className="break-words font-mono text-[0.8125rem] text-re-text-tertiary">
                                        POST /api/v1/ingest/iot/sensitech exists on experimental routers; not on the production allowlist.
                                    </div>
                                    <div className="mt-4">
                                        <Badge tone="neutral" size="sm" mono>
                                            Beta / not in production allowlist
                                        </Badge>
                                    </div>
                                </div>

                                <div className="text-small text-re-text-tertiary">
                                    <strong className="font-medium text-re-text-secondary">Also supported:</strong> Tive, Monnit, and any CSV with timestamp + temperature columns.
                                    Contact us for custom parser configuration.
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* API Guide Tab */}
                    <TabsContent value="api" className="space-y-6">
                        <Card>
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <Code2 className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <div>
                                        <CardTitle>JSON Events API</CardTitle>
                                        <CardDescription>
                                            Push CTE events from any system using a single REST endpoint.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="flex flex-wrap items-center gap-2">
                                    <Badge tone="neutral" mono>POST</Badge>
                                    <code className="break-all font-mono text-[0.8125rem] text-re-text-primary">
                                        /api/v1/webhooks/ingest
                                    </code>
                                </div>

                                <div className="space-y-3">
                                    <div className="flex items-center justify-between gap-3">
                                        <h4 className="text-subheading text-re-text-primary">Example Request</h4>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={handleCopy}
                                            leadingIcon={copied
                                                ? <CheckCircle2 strokeWidth={1.75} aria-hidden="true" />
                                                : <Copy strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            {copied ? 'Copied' : 'Copy'}
                                        </Button>
                                    </div>
                                    <pre className="overflow-x-auto rounded-md bg-re-surface-inset p-4 font-mono text-[0.8125rem] leading-relaxed text-re-text-secondary">
                                        {EXAMPLE_CURL}
                                    </pre>
                                </div>

                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                    <Card variant="inset" padding="compact">
                                        <h4 className="mb-3 text-subheading text-re-text-primary">Supported CTE Types</h4>
                                        <ul className="space-y-1.5">
                                            {CTE_TYPES.map((cte) => (
                                                <li key={cte.id} className="flex flex-wrap items-center gap-2 text-small text-re-text-secondary">
                                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                    <code className="font-mono text-re-text-primary">{cte.id}</code>
                                                    <span className="text-re-text-tertiary">{cte.description}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </Card>
                                    <Card variant="inset" padding="compact">
                                        <h4 className="mb-3 text-subheading text-re-text-primary">What Happens on Ingest</h4>
                                        <ul className="space-y-2">
                                            {[
                                                'Key Data Element (KDE) validation per CTE type (§1.1325 to §1.1350)',
                                                'SHA-256 hash computed for each event',
                                                'Hash chained to previous event (audit trail)',
                                                'Response includes event_id + chain_hash',
                                            ].map((item) => (
                                                <li key={item} className="flex items-start gap-2 text-small text-re-text-secondary">
                                                    <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                    {item}
                                                </li>
                                            ))}
                                        </ul>
                                    </Card>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
            </LeadGate>
        </FreeToolPageShell>
    );
}
