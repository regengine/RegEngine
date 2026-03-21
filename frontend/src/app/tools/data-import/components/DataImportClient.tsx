'use client';

import React, { useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
    Database,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { toast } from '@/components/ui/use-toast';

const CTE_TYPES = [
    { id: 'harvesting', label: 'Harvesting', description: 'Farm harvest events' },
    { id: 'cooling', label: 'Cooling', description: 'Cold storage/cooling events' },
    { id: 'initial_packing', label: 'Initial Packing', description: 'Packing line events' },
    { id: 'shipping', label: 'Shipping', description: 'Outbound shipment events' },
    { id: 'receiving', label: 'Receiving', description: 'Inbound receipt events' },
    { id: 'transformation', label: 'Transformation', description: 'Processing/mixing events' },
];

const EXAMPLE_CURL = `curl -X POST https://www.regengine.co/api/v1/webhooks/ingest \\
  -H "Content-Type: application/json" \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -d '{
    "source": "erp",
    "events": [
      {
        "cte_type": "shipping",
        "traceability_lot_code": "TOM-0226-F3-001",
        "product_description": "Roma Tomatoes 12ct",
        "quantity": 200,
        "unit_of_measure": "cases",
        "location_gln": "0614141000005",
        "location_name": "Valley Fresh Farms",
        "timestamp": "2026-02-26T14:30:00Z",
        "kdes": {
          "ship_date": "2026-02-26",
          "ship_from_location": "Valley Fresh Farms, Salinas CA",
          "ship_to_location": "Metro Distribution, LA",
          "carrier_name": "Cold Express Logistics",
          "temperature_celsius": 3.2
        }
      }
    ]
  }'`;

// Synthetic FSMA 204 traceability dataset — mirrors test_data/regengine_test_traceability.csv
const SAMPLE_EVENTS = [
    { event_type: 'CREATION',       event_date: '2026-03-10', tlc: 'TLC1001', location_identifier: 'Green Valley Farm, Salinas, CA',             product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 1200, uom: 'cases' },
    { event_type: 'RECEIVING',      event_date: '2026-03-10', tlc: 'TLC1001', location_identifier: 'Salinas Cold Storage, Salinas, CA',           product_description: 'Romaine Lettuce', gtin: '09524000059109' },
    { event_type: 'INITIAL_PACKING',event_date: '2026-03-11', tlc: 'TLC1001', location_identifier: 'Pacific Produce Packers, Watsonville, CA',    product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 1200, uom: 'cases' },
    { event_type: 'SHIPPING',       event_date: '2026-03-12', tlc: 'TLC1001', location_identifier: 'Pacific Produce Packers, Watsonville, CA',    product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 1200, uom: 'cases' },
    { event_type: 'RECEIVING',      event_date: '2026-03-13', tlc: 'TLC1001', location_identifier: 'FreshChain Distribution, Los Angeles, CA',    product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 1185, uom: 'cases' },
    { event_type: 'SHIPPING',       event_date: '2026-03-14', tlc: 'TLC1001', location_identifier: 'FreshChain Distribution, Los Angeles, CA',    product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 1185, uom: 'cases' },
    { event_type: 'RECEIVING',      event_date: '2026-03-15', tlc: 'TLC1001', location_identifier: 'MarketFresh Pasadena, Pasadena, CA',          product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 400,  uom: 'cases' },
    { event_type: 'RECEIVING',      event_date: '2026-03-15', tlc: 'TLC1001', location_identifier: 'MarketFresh Glendale, Glendale, CA',          product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 350,  uom: 'cases' },
    { event_type: 'RECEIVING',      event_date: '2026-03-15', tlc: 'TLC1001', location_identifier: 'MarketFresh SantaMonica, Santa Monica, CA',   product_description: 'Romaine Lettuce', gtin: '09524000059109', quantity: 435,  uom: 'cases' },
];

type TabId = 'csv' | 'iot' | 'api';
type UploadState = 'idle' | 'uploading' | 'success' | 'error';
type SampleState = 'idle' | 'running' | 'done' | 'error';

interface SampleStepResult {
    label: string;
    ok: boolean;
    detail: string;
}

export function DataImportClient() {
    const { apiKey } = useAuth();
    const [activeTab, setActiveTab] = useState<TabId>('csv');
    const [copied, setCopied] = useState(false);

    // Real file upload state
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [uploadState, setUploadState] = useState<UploadState>('idle');
    const [uploadResult, setUploadResult] = useState<{ jobId?: string; status?: number; error?: string } | null>(null);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isDragging, setIsDragging] = useState(false);

    // Sample dataset simulation state
    const [sampleState, setSampleState] = useState<SampleState>('idle');
    const [sampleSteps, setSampleSteps] = useState<SampleStepResult[]>([]);

    const handleCopy = useCallback(() => {
        navigator.clipboard.writeText(EXAMPLE_CURL);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, []);

    const handleFileChange = useCallback((file: File | null) => {
        if (!file) return;

        const VALID_EXTENSIONS = ['.csv', '.tsv'];
        const MAX_SIZE_MB = 10;
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();

        if (!VALID_EXTENSIONS.includes(ext)) {
            toast({
                variant: 'destructive',
                title: 'Invalid file type',
                description: `Only CSV and TSV files are supported. You selected a ${ext} file.`,
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

    const handleUpload = useCallback(async () => {
        if (!selectedFile) return;
        setUploadState('uploading');
        setUploadResult(null);
        try {
            const effectiveKey = apiKey || process.env.NEXT_PUBLIC_API_KEY || '';
            const result = await apiClient.ingestFile(effectiveKey, selectedFile, 'fsma');
            const jobId = (result as any).job_id || (result as any).id || (result as any).task_id;
            setUploadResult({ jobId, status: 200 });
            setUploadState('success');
        } catch (err: any) {
            const status = err?.response?.status;
            const msg = err?.response?.data?.detail || err?.message || 'Upload failed';
            setUploadResult({ status, error: msg });
            setUploadState('error');
        }
    }, [selectedFile, apiKey]);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFileChange(file);
    }, [handleFileChange]);

    const handleLoadSample = useCallback(async () => {
        setSampleState('running');
        setSampleSteps([]);

        const addStep = (label: string, ok: boolean, detail: string) => {
            setSampleSteps((prev) => [...prev, { label, ok, detail }]);
        };

        // Map sample events to webhook format
        const CTE_MAP: Record<string, string> = {
            CREATION: 'harvesting', RECEIVING: 'receiving',
            INITIAL_PACKING: 'initial_packing', SHIPPING: 'shipping',
        };

        const webhookEvents = SAMPLE_EVENTS.map((evt) => ({
            cte_type: CTE_MAP[evt.event_type] || evt.event_type.toLowerCase(),
            traceability_lot_code: evt.tlc,
            product_description: evt.product_description,
            quantity: evt.quantity || 0,
            unit_of_measure: evt.uom || 'cases',
            location_name: evt.location_identifier,
            timestamp: `${evt.event_date}T00:00:00Z`,
            kdes: { gtin: evt.gtin },
        }));

        try {
            const effectiveKey = apiKey || process.env.NEXT_PUBLIC_API_KEY || '';
            const result = await apiClient.ingestWebhookEvents(
                effectiveKey,
                webhookEvents,
                'sample_dataset',
                'default',
            );

            // Show individual step results
            for (const evt of SAMPLE_EVENTS) {
                addStep(
                    `${evt.event_type} — ${evt.location_identifier.split(',')[0]}`,
                    true,
                    `TLC ${evt.tlc} · ${evt.event_date}${evt.quantity ? ` · ${evt.quantity} ${evt.uom}` : ''}`,
                );
            }

            addStep(
                `Batch ingest complete`,
                result.accepted > 0,
                `${result.accepted}/${result.total} events persisted to database`,
            );

            setSampleState(result.accepted > 0 ? 'done' : 'error');
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || 'Webhook ingest failed';
            addStep('Batch ingest', false, msg);
            setSampleState('error');
        }
    }, [apiKey]);

    const tabs: { id: TabId; label: string; icon: React.ElementType }[] = [
        { id: 'csv', label: 'CSV Upload', icon: FileSpreadsheet },
        { id: 'iot', label: 'IoT Import', icon: Thermometer },
        { id: 'api', label: 'API Guide', icon: Code2 },
    ];

    return (
        <FreeToolPageShell
            title="Data Import Hub"
            subtitle="Get your traceability data into RegEngine — upload CSV, import IoT logs, or connect via API."
            relatedToolIds={['ftl-checker', 'cte-mapper', 'kde-checker']}
        >
            <LeadGate
                source="data-import"
                headline="Unlock the Data Import Hub"
                subheadline="Upload CSV files, import IoT temperature logs, and connect via API to start building your traceability records."
                ctaText="Access Import Tools"
                teaser={
                    <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 text-center">
                        <div className="text-4xl mb-3">📤</div>
                        <p className="text-lg font-semibold text-[var(--re-text-primary)]">Three Ways to Import</p>
                        <p className="text-sm text-[var(--re-text-muted)] mt-2">CSV Upload with templates for every CTE type, IoT Sensitech TempTale import, and a full REST webhook API.</p>
                    </div>
                }
            >
            {/* Tab Navigation */}
            <div className="flex gap-2 mb-8">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        type="button"
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex items-center gap-2 px-5 py-3 rounded-xl font-medium text-sm transition-all ${activeTab === tab.id
                                ? 'bg-[var(--re-brand)] text-white shadow-lg'
                                : 'bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-muted-foreground hover:border-[var(--re-brand)]'
                            }`}
                    >
                        <tab.icon className="h-4 w-4" />
                        {tab.label}
                    </button>
                ))}
            </div>

            <AnimatePresence mode="wait">
                {/* CSV Upload Tab */}
                {activeTab === 'csv' && (
                    <motion.div
                        key="csv"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="space-y-8"
                    >
                        {/* Step 1: Download Template */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)] text-white text-sm font-bold">
                                        1
                                    </div>
                                    <div>
                                        <CardTitle className="text-lg">Download CSV Template</CardTitle>
                                        <CardDescription>
                                            Select the CTE type you&apos;re recording, then download the template with pre-filled headers.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                    {CTE_TYPES.map((cte) => (
                                        <a
                                            key={cte.id}
                                            href={`/api/v1/templates/${cte.id}`}
                                            download
                                            className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-brand)] transition-all group"
                                        >
                                            <div>
                                                <div className="text-sm font-medium group-hover:text-[var(--re-brand)] transition-colors">
                                                    {cte.label}
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {cte.description}
                                                </div>
                                            </div>
                                            <Download className="h-4 w-4 text-muted-foreground group-hover:text-[var(--re-brand)]" />
                                        </a>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Step 2: Upload */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-brand)] text-white text-sm font-bold">
                                        2
                                    </div>
                                    <div>
                                        <CardTitle className="text-lg">Upload Filled CSV</CardTitle>
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
                                    className={`border-2 border-dashed rounded-2xl p-12 text-center transition-colors cursor-pointer ${
                                        isDragging
                                            ? 'border-[var(--re-brand)] bg-[color-mix(in_srgb,var(--re-brand)_5%,transparent)]'
                                            : selectedFile
                                            ? 'border-emerald-500/50 bg-emerald-500/5'
                                            : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                    }`}
                                    onClick={() => fileInputRef.current?.click()}
                                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                                    onDragLeave={() => setIsDragging(false)}
                                    onDrop={handleDrop}
                                >
                                    {selectedFile ? (
                                        <>
                                            <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto mb-4" />
                                            <div className="text-sm font-medium mb-1">{selectedFile.name}</div>
                                            <div className="text-xs text-muted-foreground">
                                                {(selectedFile.size / 1024).toFixed(1)} KB — click to change
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-4" />
                                            <div className="text-sm font-medium mb-1">
                                                Drag & drop your CSV here, or click to browse
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                Supports .csv files up to 10MB
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Upload button */}
                                {selectedFile && (
                                    <Button
                                        onClick={handleUpload}
                                        disabled={uploadState === 'uploading'}
                                        className="w-full bg-[var(--re-brand)] hover:brightness-110 text-white h-11 rounded-xl font-semibold"
                                    >
                                        {uploadState === 'uploading' ? (
                                            <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Uploading…</>
                                        ) : (
                                            <><Upload className="mr-2 h-4 w-4" /> Submit to Ingestion Pipeline</>
                                        )}
                                    </Button>
                                )}

                                {/* Upload result */}
                                <AnimatePresence>
                                    {uploadResult && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 6 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0 }}
                                            className={`p-4 rounded-xl border text-sm ${
                                                uploadState === 'success'
                                                    ? 'border-emerald-500/30 bg-emerald-500/5'
                                                    : 'border-red-500/30 bg-red-500/5'
                                            }`}
                                        >
                                            <div className="flex items-center gap-2 font-medium mb-1">
                                                {uploadState === 'success' ? (
                                                    <><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Uploaded successfully</>
                                                ) : (
                                                    <><XCircle className="h-4 w-4 text-red-500" /> Upload failed</>
                                                )}
                                            </div>
                                            {uploadResult.jobId && (
                                                <div className="text-xs text-muted-foreground font-mono">Job ID: {uploadResult.jobId}</div>
                                            )}
                                            {uploadResult.error && (
                                                <div className="text-xs text-red-600">{uploadResult.error}</div>
                                            )}
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </CardContent>
                        </Card>

                        {/* Sample Dataset */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-sm font-bold text-muted-foreground">
                                            <Database className="h-4 w-4" />
                                        </div>
                                        <div>
                                            <CardTitle className="text-lg">Load Sample Dataset</CardTitle>
                                            <CardDescription>
                                                Push a synthetic Romaine Lettuce supply chain (TLC1001) through the full pipeline — 9 CTE events from farm to retailer.
                                            </CardDescription>
                                        </div>
                                    </div>
                                    <Button
                                        onClick={handleLoadSample}
                                        disabled={sampleState === 'running'}
                                        variant="outline"
                                        className="shrink-0 rounded-xl border-[var(--re-brand)] text-[var(--re-brand)] hover:bg-[color-mix(in_srgb,var(--re-brand)_5%,transparent)]"
                                    >
                                        {sampleState === 'running' ? (
                                            <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Running…</>
                                        ) : (
                                            'Run Simulation'
                                        )}
                                    </Button>
                                </div>
                            </CardHeader>
                            {sampleSteps.length > 0 && (
                                <CardContent>
                                    <div className="space-y-2">
                                        {sampleSteps.map((step, i) => (
                                            <motion.div
                                                key={i}
                                                initial={{ opacity: 0, x: -8 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: i * 0.05 }}
                                                className={`flex items-start gap-3 p-3 rounded-xl border text-sm ${
                                                    step.ok
                                                        ? 'border-emerald-500/20 bg-emerald-500/5'
                                                        : 'border-red-500/20 bg-red-500/5'
                                                }`}
                                            >
                                                {step.ok ? (
                                                    <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                                                ) : (
                                                    <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                                                )}
                                                <div className="flex-1 min-w-0">
                                                    <div className="font-medium truncate">{step.label}</div>
                                                    <div className="text-xs text-muted-foreground">{step.detail}</div>
                                                </div>
                                            </motion.div>
                                        ))}
                                        {sampleState === 'done' && (
                                            <motion.div
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                className="pt-2 text-xs text-muted-foreground text-center"
                                            >
                                                Dataset loaded — run a recall drill from the Mock Audit Drill tool to trace TLC1001.
                                            </motion.div>
                                        )}
                                    </div>
                                </CardContent>
                            )}
                        </Card>
                    </motion.div>
                )}

                {/* IoT Import Tab */}
                {activeTab === 'iot' && (
                    <motion.div
                        key="iot"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="space-y-6"
                    >
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className="p-3 rounded-xl bg-[color-mix(in_srgb,var(--re-brand)_10%,transparent)]">
                                        <Thermometer className="h-6 w-6 text-[var(--re-brand)]" />
                                    </div>
                                    <div>
                                        <CardTitle className="text-lg">Sensitech TempTale Import</CardTitle>
                                        <CardDescription>
                                            Upload Sensitech TempTale CSV exports to create temperature-linked CTE events.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div className="p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <div className="flex items-center gap-2 text-sm font-medium mb-2">
                                            <CheckCircle2 className="h-4 w-4 text-[var(--re-brand)]" />
                                            Auto-Detection
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            Automatically detects column format from Sensitech CSV exports
                                        </div>
                                    </div>
                                    <div className="p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <div className="flex items-center gap-2 text-sm font-medium mb-2">
                                            <AlertTriangle className="h-4 w-4 text-amber-500" />
                                            Excursion Detection
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            Flags any readings exceeding cold chain thresholds (default: 5°C)
                                        </div>
                                    </div>
                                    <div className="p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <div className="flex items-center gap-2 text-sm font-medium mb-2">
                                            <CheckCircle2 className="h-4 w-4 text-[var(--re-brand)]" />
                                            TLC Linking
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            Links temperature data to specific Traceability Lot Codes
                                        </div>
                                    </div>
                                </div>

                                <div className="border-2 border-dashed border-[var(--re-border-default)] rounded-2xl p-12 text-center hover:border-[var(--re-brand)] transition-colors">
                                    <Thermometer className="h-10 w-10 text-muted-foreground mx-auto mb-4" />
                                    <div className="text-sm font-medium mb-1">
                                        Upload Sensitech TempTale CSV
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        POST /api/v1/ingest/iot/sensitech — available now via API
                                    </div>
                                    <Badge variant="outline" className="mt-4 text-[9px] uppercase tracking-widest">
                                        API Available Now
                                    </Badge>
                                </div>

                                <div className="text-xs text-muted-foreground">
                                    <strong>Also supported:</strong> Tive, Monnit, and any CSV with timestamp + temperature columns.
                                    Contact us for custom parser configuration.
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* API Guide Tab */}
                {activeTab === 'api' && (
                    <motion.div
                        key="api"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="space-y-6"
                    >
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className="p-3 rounded-xl bg-[color-mix(in_srgb,var(--re-brand)_10%,transparent)]">
                                        <Code2 className="h-6 w-6 text-[var(--re-brand)]" />
                                    </div>
                                    <div>
                                        <CardTitle className="text-lg">Webhook Ingestion API</CardTitle>
                                        <CardDescription>
                                            Push CTE events from any system using a single REST endpoint.
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="flex items-center gap-2 text-sm">
                                    <Badge className="bg-emerald-600 text-white text-xs font-bold">POST</Badge>
                                    <code className="text-sm font-mono text-[var(--re-brand)]">
                                        /api/v1/webhooks/ingest
                                    </code>
                                </div>

                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <h4 className="text-sm font-bold">Example Request</h4>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={handleCopy}
                                            className="text-xs"
                                        >
                                            {copied ? (
                                                <><CheckCircle2 className="h-3 w-3 mr-1" /> Copied</>
                                            ) : (
                                                <><Copy className="h-3 w-3 mr-1" /> Copy</>
                                            )}
                                        </Button>
                                    </div>
                                    <pre className="p-4 rounded-xl bg-[#0d1117] text-[#c9d1d9] text-xs font-mono overflow-x-auto leading-relaxed">
                                        {EXAMPLE_CURL}
                                    </pre>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <h4 className="text-sm font-bold mb-3">Supported CTE Types</h4>
                                        <ul className="space-y-1.5">
                                            {CTE_TYPES.map((cte) => (
                                                <li key={cte.id} className="flex items-center gap-2 text-xs">
                                                    <CheckCircle2 className="h-3 w-3 text-[var(--re-brand)]" />
                                                    <code className="font-mono">{cte.id}</code>
                                                    <span className="text-muted-foreground">— {cte.description}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                    <div className="p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                        <h4 className="text-sm font-bold mb-3">What Happens on Ingest</h4>
                                        <ul className="space-y-2">
                                            {[
                                                'KDE validation per CTE type (§1.1325–§1.1350)',
                                                'SHA-256 hash computed for each event',
                                                'Hash chained to previous event (audit trail)',
                                                'Response includes event_id + chain_hash',
                                            ].map((item) => (
                                                <li key={item} className="flex items-start gap-2 text-xs">
                                                    <ArrowRight className="h-3 w-3 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                                    {item}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>
            </LeadGate>
        </FreeToolPageShell>
    );
}
