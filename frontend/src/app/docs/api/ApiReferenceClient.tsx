'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Key,
    FileText,
    ChevronDown,
    ChevronRight,
    Copy,
    Check,
    Leaf,
    Database,
    FileDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

import { PageContainer } from '@/components/layout/page-container';
import { CodeBlock } from '@/components/ui/code-block';

interface Endpoint {
    method: string;
    path: string;
    description: string;
    auth: boolean;
    response: string;
    headers?: string[];
    params?: string[];
    params_table?: { name: string; type: string; required: boolean; desc: string }[];
    body?: string;
}

// API Endpoint Documentation
const API_SERVICES: { name: string; baseUrl: string; icon: React.ComponentType<{ className?: string }>; description: string; provisioned?: boolean; endpoints: Endpoint[] }[] = [
    {
        name: 'Webhook Ingestion API',
        baseUrl: '/api/v1/webhooks',
        icon: FileText,
        description: 'Primary FSMA event ingestion endpoint for CTE batches',
        endpoints: [
            {
                method: 'POST',
                path: '/ingest',
                description: 'Ingest one or more FSMA CTE events. Each event is SHA-256 chain-hashed and linked to the tenant audit trail. Idempotency-Key is required — safe retries replay the cached response for 24 hours per tenant.',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID', 'Idempotency-Key'],
                params_table: [
                    { name: 'source', type: 'string', required: true, desc: 'Source system identifier (e.g. "erp", "wms", "sensitech", "tive", "manual")' },
                    { name: 'events', type: 'CTE[]', required: true, desc: 'Array of Critical Tracking Events (max 500 per batch)' },
                    { name: 'events[].cte_type', type: 'enum', required: true, desc: '"harvesting" | "cooling" | "initial_packing" | "first_land_based_receiving" | "shipping" | "receiving" | "transformation"' },
                    { name: 'events[].traceability_lot_code', type: 'string', required: true, desc: 'TLC per FSMA 204 (e.g. GTIN + lot, min 3 chars)' },
                    { name: 'events[].product_description', type: 'string', required: true, desc: 'Human-readable product name (1–500 chars)' },
                    { name: 'events[].quantity', type: 'number', required: true, desc: 'Quantity (> 0)' },
                    { name: 'events[].unit_of_measure', type: 'string', required: true, desc: '"cases" | "lbs" | "kg" | "pallets" | "each" — full list in docs' },
                    { name: 'events[].location_name', type: 'string', required: true, desc: 'Facility name (or supply events[].location_gln as a 13-digit GLN)' },
                    { name: 'events[].timestamp', type: 'ISO 8601', required: true, desc: 'Event timestamp with timezone' },
                    { name: 'events[].kdes', type: 'object', required: true, desc: 'CTE-specific Key Data Elements per 21 CFR §§1.1325–1.1350. RECEIVING requires receive_date, receiving_location, immediate_previous_source, reference_document, tlc_source_reference.' },
                ],
                body: JSON.stringify({
                    source: "erp",
                    events: [{
                        cte_type: "receiving",
                        traceability_lot_code: "00012345678901-LOT-2026-001",
                        product_description: "Romaine Lettuce",
                        quantity: 500,
                        unit_of_measure: "cases",
                        location_name: "Distribution Center #4",
                        timestamp: "2026-02-05T14:23:00Z",
                        kdes: {
                            receive_date: "2026-02-05",
                            receiving_location: "Distribution Center #4",
                            immediate_previous_source: "GreenLeaf Farms LLC",
                            reference_document: "ASN-2026-02-05-00123",
                            tlc_source_reference: "GLF-2026-001"
                        }
                    }]
                }, null, 2),
                response: JSON.stringify({
                    accepted: 1,
                    rejected: 0,
                    total: 1,
                    events: [{
                        traceability_lot_code: "00012345678901-LOT-2026-001",
                        cte_type: "receiving",
                        status: "accepted",
                        event_id: "evt_9f8e7d6c5b4a",
                        sha256_hash: "a1b2c3d4e5f6...",
                        chain_hash: "7f6e5d4c3b2a..."
                    }],
                    ingestion_timestamp: "2026-02-05T14:23:01.847Z"
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/health',
                description: 'Webhook ingestion health check',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                response: '{ "service": "webhook-ingestion", "status": "healthy" }',
            },
        ],
    },
    {
        name: 'Records API',
        baseUrl: '/api/v1/records',
        icon: Database,
        description: 'Read canonical traceability events with full provenance — what it is, where it came from, what rules were applied, what failed, what must happen next',
        endpoints: [
            {
                method: 'GET',
                path: '',
                description: 'List and search canonical traceability events. Requires an API key with the records.read scope. Keys are tenant-bound — results are always scoped to your workspace.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params_table: [
                    { name: 'tlc', type: 'string', required: false, desc: 'Filter by traceability lot code' },
                    { name: 'event_type', type: 'string', required: false, desc: 'Filter by CTE type (e.g. "receiving", "shipping")' },
                    { name: 'status', type: 'string', required: false, desc: 'Record status (default: "active")' },
                    { name: 'source_system', type: 'string', required: false, desc: 'Filter by ingestion source' },
                    { name: 'start_date', type: 'ISO 8601', required: false, desc: 'Events at or after this timestamp' },
                    { name: 'end_date', type: 'ISO 8601', required: false, desc: 'Events at or before this timestamp' },
                    { name: 'limit', type: 'number', required: false, desc: 'Page size (default: 50, max: 500)' },
                    { name: 'offset', type: 'number', required: false, desc: 'Pagination offset' },
                ],
                response: JSON.stringify({
                    tenant_id: "38e99859-7364-4932-99fa-b1f114bf0202",
                    events: [{
                        event_id: "evt_9f8e7d6c5b4a",
                        cte_type: "receiving",
                        traceability_lot_code: "00012345678901-LOT-2026-001",
                        status: "active",
                        source_system: "erp",
                        event_timestamp: "2026-02-05T14:23:00Z"
                    }],
                    total: 1
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/{event_id}',
                description: 'Full record detail with provenance: source document, applied rules, evaluation results, and amendment chain.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "event_id": "evt_9f8e7d6c5b4a", "cte_type": "receiving", "kdes": {...}, "provenance": {...} }',
            },
            {
                method: 'GET',
                path: '/{event_id}/evaluations',
                description: 'Rule evaluations for a record — which FSMA 204 rules were applied and their outcomes',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "event_id": "evt_9f8e7d6c5b4a", "evaluations": [{ "rule_id": "...", "outcome": "pass" }] }',
            },
            {
                method: 'GET',
                path: '/{event_id}/history',
                description: 'Amendment chain for a record — every correction with who, when, and why',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "event_id": "evt_9f8e7d6c5b4a", "history": [{ "amended_at": "...", "reason": "..." }] }',
            },
        ],
    },
    {
        name: 'FDA Trace & Export API',
        baseUrl: '/api/v1/fda',
        icon: FileDown,
        description: 'Lot tracing and FDA-formatted exports from stored tenant evidence, with cryptographic verification',
        endpoints: [
            {
                method: 'GET',
                path: '/trace/{tlc}',
                description: 'Trace the transformation graph for a traceability lot code — upstream sources and downstream products. Requires the fda.read scope. Unlike the Records API, FDA endpoints take tenant_id as an explicit query parameter (it must match your key’s tenant).',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-tenant-uuid}'],
                response: JSON.stringify({
                    seed_tlc: "00012345678901-LOT-2026-001",
                    tenant_id: "38e99859-7364-4932-99fa-b1f114bf0202",
                    traversal_depth: 5,
                    node_count: 1,
                    edge_count: 0,
                    nodes: [{ tlc: "00012345678901-LOT-2026-001", is_seed: true, role: "seed", event_count: 0 }]
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/export',
                description: 'Generate an FDA export for a traceability lot code (the 24-hour traceability request format). Requires the fda.export scope and an active subscription.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-tenant-uuid}', 'tlc=00012345678901-LOT-2026-001', 'format=csv'],
                response: 'CSV / JSON export with FSMA 204-required KDE columns',
            },
            {
                method: 'GET',
                path: '/export/v2',
                description: 'Generate an FDA export from the canonical record model (v2) — includes provenance and rule-evaluation status per row',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-tenant-uuid}', 'start_date=2026-01-01', 'end_date=2026-01-31'],
                response: 'CSV / JSON export derived from canonical records',
            },
            {
                method: 'GET',
                path: '/export/recall',
                description: 'Recall-filtered FDA export — only events linked to the recalled lot and its trace graph',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-tenant-uuid}', 'tlc=00012345678901-LOT-2026-001'],
                response: 'CSV / JSON export scoped to the recall trace',
            },
            {
                method: 'POST',
                path: '/export/verify',
                description: 'Verify the hash chain of a previously generated export. Requires the fda.verify scope. Pair with the public verify_chain.py script for independent verification.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                body: JSON.stringify({ export_id: "exp_1a2b3c4d" }, null, 2),
                response: '{ "export_id": "exp_1a2b3c4d", "chain_valid": true, "events_verified": 1204 }',
            },
            {
                method: 'GET',
                path: '/export/history',
                description: 'List previously generated exports with their verification status',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-tenant-uuid}'],
                response: '{ "tenant_id": "38e99859-...", "exports": [{ "export_id": "exp_1a2b3c4d", "created_at": "...", "chain_valid": true }], "total": 0 }',
            },
        ],
    },
    {
        name: 'FSMA Traceability API',
        baseUrl: '/v1/fsma',
        icon: Leaf,
        description: 'Supply chain tracing, mock recalls, and FDA 24-hour exports',
        provisioned: true,
        endpoints: [
            {
                method: 'GET',
                path: '/trace/forward/{tlc}',
                description: 'Trace forward from lot to downstream customers and products. Returns the full supply chain graph from this lot outward.',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                params: ['max_depth=10', 'enforce_time_arrow=true'],
                params_table: [
                    { name: 'tlc', type: 'string', required: true, desc: 'Traceability Lot Code (path parameter)' },
                    { name: 'max_depth', type: 'number', required: false, desc: 'Max hops to trace (default: 10, max: 50)' },
                    { name: 'enforce_time_arrow', type: 'boolean', required: false, desc: 'Only follow edges forward in time (default: true)' },
                ],
                response: JSON.stringify({
                    lot_id: "TLC123",
                    facilities: ["Distribution Center #4", "Retail Store #12"],
                    events: [{ cte: "shipping", timestamp: "2026-02-06T08:00:00Z" }],
                    hop_count: 5
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/trace/backward/{tlc}',
                description: 'Trace backward from lot to source materials and suppliers',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                params: ['max_depth=10'],
                response: '{ "lot_id": "TLC123", "source_lots": [...], "facilities": [...] }',
            },
            {
                method: 'GET',
                path: '/timeline/{tlc}',
                description: 'Get chronological timeline of all events for a lot',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                response: '{ "lot_id": "TLC123", "events": [{ "cte": "RECEIVING", "date": "..." }] }',
            },
            {
                method: 'GET',
                path: '/coverage',
                description: 'Get FSMA coverage status and enforcement timeline metadata',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                response: '{ "authority": "FDA FSMA 204", "compliance_deadline": "2028-07-20", "enforcement_status": "..." }',
            },
            {
                method: 'GET',
                path: '/export/fda-request',
                description: 'Generate an FDA-oriented sortable spreadsheet (CSV)',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                params: ['start_date=2026-01-01', 'end_date=2026-01-31'],
                response: 'CSV file download with FSMA-required columns',
            },
            {
                method: 'GET',
                path: '/recall/readiness',
                description: 'Get recall readiness score (0-100) with actionable recommendations for improving recall response time.',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                response: JSON.stringify({
                    readiness_score: 85,
                    gaps: ["recall_drill_cadence", "facility_gln_coverage"],
                    recommendations: [
                        { priority: "high", action: "Run quarterly recall drill", impact: "+5 points" },
                        { priority: "medium", action: "Add GLN to 3 facilities", impact: "+3 points" }
                    ],
                    last_drill: "2026-02-01T10:00:00Z",
                    avg_response_hours: 6.2,
                    sla_target_hours: 24
                }, null, 2),
            },
        ],
    },
];

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <Button size="sm" variant="ghost" onClick={handleCopy} className="h-6 w-6 p-0">
            {copied ? <Check className="h-3 w-3 text-re-success" /> : <Copy className="h-3 w-3" />}
        </Button>
    );
}

function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
    const [expanded, setExpanded] = useState(false);

    const methodColors: Record<string, string> = {
        GET: 'bg-re-info',
        POST: 'bg-re-success',
        PUT: 'bg-re-warning',
        DELETE: 'bg-re-danger',
    };

    return (
        <div className="border rounded-lg overflow-hidden">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex flex-wrap items-center gap-2 p-3 text-left hover:bg-muted/50 transition-colors sm:gap-3"
            >
                {expanded ? (
                    <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                ) : (
                    <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                )}
                <Badge className={`${methodColors[endpoint.method]} text-white font-mono text-xs`}>
                    {endpoint.method}
                </Badge>
                <code className="min-w-0 flex-[1_1_150px] break-all font-mono text-sm">{endpoint.path}</code>
                {endpoint.auth && (
                    <Badge variant="outline" className="ml-6 text-xs sm:ml-0">
                        Auth
                    </Badge>
                )}
            </button>

            {expanded && (
                <div className="border-t p-4 bg-muted/20 space-y-4">
                    <p className="text-sm text-muted-foreground">{endpoint.description}</p>

                    {endpoint.headers && (
                        <div>
                            <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-1">Headers</h4>
                            <div className="flex flex-wrap gap-1">
                                {endpoint.headers.map((h) => (
                                    <Badge key={h} variant="secondary" className="font-mono text-xs">
                                        {h}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {endpoint.params && (
                        <div>
                            <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-1">Query Params</h4>
                            <div className="flex flex-wrap gap-1">
                                {endpoint.params.map((p) => (
                                    <Badge key={p} variant="outline" className="font-mono text-xs">
                                        {p}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {endpoint.params_table && (
                        <div>
                            <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Parameters</h4>
                            <div className="border rounded-lg overflow-x-auto">
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="bg-muted/50 border-b">
                                            <th className="text-left p-2 font-semibold">Name</th>
                                            <th className="text-left p-2 font-semibold">Type</th>
                                            <th className="text-left p-2 font-semibold">Required</th>
                                            <th className="text-left p-2 font-semibold">Description</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {endpoint.params_table.map((p) => (
                                            <tr key={p.name} className="border-b last:border-b-0">
                                                <td className="p-2 font-mono text-re-info dark:text-re-info">{p.name}</td>
                                                <td className="p-2 font-mono text-muted-foreground">{p.type}</td>
                                                <td className="p-2">{p.required ? <Badge variant="destructive" className="text-[10px] px-1.5 py-0">required</Badge> : <span className="text-muted-foreground">optional</span>}</td>
                                                <td className="p-2 text-muted-foreground">{p.desc}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {endpoint.body && (
                        <div>
                            <div className="flex items-center justify-between mb-1">
                                <h4 className="text-xs font-semibold uppercase text-muted-foreground">Request Body</h4>
                                <CopyButton text={endpoint.body} />
                            </div>
                            <CodeBlock code={endpoint.body} language="json" />
                        </div>
                    )}

                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <h4 className="text-xs font-semibold uppercase text-muted-foreground">Response</h4>
                            <CopyButton text={endpoint.response} />
                        </div>
                        <CodeBlock code={endpoint.response} language="json" />
                    </div>
                </div>
            )}
        </div>
    );
}

export function ApiReferenceClient() {
    const [selectedService, setSelectedService] = useState(0);

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-8"
                >
                    {/* Header */}
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold">API Reference</h1>
                            <p className="text-muted-foreground mt-1">
                                Complete documentation for all RegEngine API endpoints
                            </p>
                        </div>
                        <div className="flex gap-2">
                            <Badge variant="outline">v1.0.0</Badge>
                        </div>
                    </div>

                    {/* Authentication Info */}
                    <Card className="border-re-warning bg-re-warning-muted dark:bg-re-warning/20 dark:border-re-warning">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-lg flex items-center gap-2">
                                <Key className="h-5 w-5 text-re-warning" />
                                Authentication
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <p className="text-sm">
                                All authenticated endpoints require one of the following headers:
                            </p>
                            <div >
                                <div className="bg-white dark:bg-re-surface-base rounded p-3">
                                    <code className="text-xs font-mono text-re-warning dark:text-re-warning">
                                        X-RegEngine-API-Key: rge_your_api_key
                                    </code>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Standard API access (tenant-scoped)
                                    </p>
                                </div>
                            </div>
                            <p className="text-sm">
                                For multi-tenant isolation, include: <code className="bg-white dark:bg-re-surface-base px-1 rounded text-xs">X-Tenant-ID: tenant_uuid</code>
                            </p>
                        </CardContent>
                    </Card>

                    {/* Service Navigation */}
                    <div className="flex flex-wrap gap-2">
                        {API_SERVICES.map((service, i) => {
                            const Icon = service.icon;
                            return (
                                <Button
                                    key={service.name}
                                    variant={selectedService === i ? 'default' : 'outline'}
                                    onClick={() => setSelectedService(i)}
                                    className="gap-2"
                                >
                                    <Icon className="h-4 w-4" />
                                    {service.name}
                                    <Badge variant="secondary" className="ml-1 text-xs">
                                        {service.endpoints.length} endpoint{service.endpoints.length !== 1 ? 's' : ''}
                                    </Badge>
                                </Button>
                            );
                        })}
                    </div>

                    {/* Selected Service Details */}
                    <motion.div
                        key={selectedService}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                    >
                        <Card>
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    {(() => {
                                        const Icon = API_SERVICES[selectedService].icon;
                                        return <Icon className="h-6 w-6 text-primary" />;
                                    })()}
                                    <div>
                                        <CardTitle>{API_SERVICES[selectedService].name}</CardTitle>
                                        <CardDescription>
                                            {API_SERVICES[selectedService].description}
                                        </CardDescription>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 mt-2">
                                    <Badge variant="outline" className="font-mono">
                                        Base URL: {API_SERVICES[selectedService].baseUrl}
                                    </Badge>
                                    <Badge variant="outline" className="font-mono">
                                        {API_SERVICES[selectedService].provisioned ? 'provisioned endpoint' : 'regengine.co'}
                                    </Badge>
                                </div>
                                {API_SERVICES[selectedService].provisioned && (
                                    <p className="text-xs text-muted-foreground mt-2">
                                        Available on contracted workspaces. These endpoints are served from your
                                        workspace&apos;s provisioned endpoint URL (supplied during onboarding), not the
                                        public regengine.co base URL. Webhook Ingestion, Records, and FDA
                                        Trace &amp; Export above are the publicly reachable surface.
                                    </p>
                                )}
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {API_SERVICES[selectedService].endpoints.map((endpoint, i) => (
                                    <EndpointCard key={i} endpoint={endpoint} />
                                ))}
                            </CardContent>
                        </Card>
                    </motion.div>

                    {/* Pagination Info */}
                    <Card className="border-blue-200 bg-re-info-muted dark:bg-re-info/20 dark:border-blue-800">
                        <CardHeader>
                            <CardTitle className="text-lg">Pagination</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <p className="text-sm text-muted-foreground">
                                List endpoints support cursor-based pagination for efficient traversal of large datasets.
                            </p>
                            <div className="space-y-3">
                                <div>
                                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Request Parameters</h4>
                                    <div className="grid md:grid-cols-2 gap-3">
                                        <div className="bg-white dark:bg-re-surface-base rounded p-3">
                                            <code className="text-xs font-mono">limit</code>
                                            <span className="text-xs text-muted-foreground ml-2">(default: 50, max: 500)</span>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Number of items to return per page
                                            </p>
                                        </div>
                                        <div className="bg-white dark:bg-re-surface-base rounded p-3">
                                            <code className="text-xs font-mono">cursor</code>
                                            <span className="text-xs text-muted-foreground ml-2">(optional)</span>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                Opaque cursor from previous response's <code>next_cursor</code>
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Response Format</h4>
                                    <CodeBlock code={`{
  "items": [...],        // Array of results
  "next_cursor": "abc",  // Use this for next page (null if no more)
  "has_more": true       // Boolean indicating more pages exist
}`} language="json" />
                                </div>
                                <div className="bg-white dark:bg-re-surface-base rounded p-3">
                                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-1">Example: Paginating Records</h4>
                                    <CodeBlock code={`# First page
GET /api/v1/records?limit=20

# Next page (Records uses limit/offset)
GET /api/v1/records?limit=20&offset=20`} language="http" />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Rate Limiting Info */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-lg">Rate Limiting</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <p className="text-sm text-muted-foreground">
                                API requests are rate-limited per API key. Check response headers:
                            </p>
                            <div className="grid md:grid-cols-3 gap-4">
                                <div className="bg-muted rounded p-3">
                                    <code className="text-xs font-mono">X-RateLimit-Limit</code>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Max requests per window
                                    </p>
                                </div>
                                <div className="bg-muted rounded p-3">
                                    <code className="text-xs font-mono">X-RateLimit-Remaining</code>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Requests left in window
                                    </p>
                                </div>
                                <div className="bg-muted rounded p-3">
                                    <code className="text-xs font-mono">X-RateLimit-Reset</code>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        When limit resets (epoch)
                                    </p>
                                </div>
                            </div>
                            <p className="text-xs text-muted-foreground mt-3">
                                Limits are enforced per API key; your current window is reported in the headers above.
                                See <a href="/docs/rate-limits" className="underline">Rate Limits</a> for details.
                            </p>
                        </CardContent>
                    </Card>

                    {/* Error Codes */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-lg">Error Codes</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid md:grid-cols-2 gap-4 text-sm">
                                <div className="flex items-start gap-3">
                                    <Badge variant="destructive">400</Badge>
                                    <span className="text-muted-foreground">Bad Request - Invalid parameters</span>
                                </div>
                                <div className="flex items-start gap-3">
                                    <Badge variant="destructive">401</Badge>
                                    <span className="text-muted-foreground">Unauthorized - Missing or invalid API key</span>
                                </div>
                                <div className="flex items-start gap-3">
                                    <Badge variant="destructive">403</Badge>
                                    <span className="text-muted-foreground">Forbidden - Insufficient permissions</span>
                                </div>
                                <div className="flex items-start gap-3">
                                    <Badge variant="destructive">404</Badge>
                                    <span className="text-muted-foreground">Not Found - Resource doesn't exist</span>
                                </div>
                                <div className="flex items-start gap-3">
                                    <Badge variant="destructive">429</Badge>
                                    <span className="text-muted-foreground">Too Many Requests - Rate limited</span>
                                </div>
                                <div className="flex items-start gap-3">
                                    <Badge variant="destructive">500</Badge>
                                    <span className="text-muted-foreground">Internal Error - Contact support</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </PageContainer>
        </div>
    );
}
