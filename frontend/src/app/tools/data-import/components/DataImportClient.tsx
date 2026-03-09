'use client';

import React, { useState, useCallback } from 'react';
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
} from 'lucide-react';

const CTE_TYPES = [
    { id: 'harvesting', label: 'Harvesting', description: 'Farm harvest events' },
    { id: 'cooling', label: 'Cooling', description: 'Cold storage/cooling events' },
    { id: 'initial_packing', label: 'Initial Packing', description: 'Packing line events' },
    { id: 'shipping', label: 'Shipping', description: 'Outbound shipment events' },
    { id: 'receiving', label: 'Receiving', description: 'Inbound receipt events' },
    { id: 'transformation', label: 'Transformation', description: 'Processing/mixing events' },
];

const EXAMPLE_CURL = `curl -X POST https://api.regengine.co/api/v1/webhooks/ingest \\
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

type TabId = 'csv' | 'iot' | 'api';

export function DataImportClient() {
    const [activeTab, setActiveTab] = useState<TabId>('csv');
    const [copied, setCopied] = useState(false);

    const handleCopy = useCallback(() => {
        navigator.clipboard.writeText(EXAMPLE_CURL);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, []);

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
            {/* Tab Navigation */}
            <div className="flex gap-2 mb-8">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
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
                            <CardContent>
                                <div className="border-2 border-dashed border-[var(--re-border-default)] rounded-2xl p-12 text-center hover:border-[var(--re-brand)] transition-colors">
                                    <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-4" />
                                    <div className="text-sm font-medium mb-1">
                                        Drag & drop your CSV here, or click to browse
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        Supports .csv files up to 10MB
                                    </div>
                                    <Badge variant="outline" className="mt-4 text-[9px] uppercase tracking-widest">
                                        UI Release in Beta — API Available Now
                                    </Badge>
                                </div>
                            </CardContent>
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
                                        UI Upload Beta Rollout — API Available Now
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
        </FreeToolPageShell>
    );
}
