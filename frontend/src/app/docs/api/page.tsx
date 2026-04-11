'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Server,
    Key,
    FileText,
    Search,
    Shield,
    ChevronDown,
    ChevronRight,
    Copy,
    Check,
    Leaf,
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
const API_SERVICES: { name: string; port: number; baseUrl: string; icon: React.ComponentType<{ className?: string }>; description: string; endpoints: Endpoint[] }[] = [
    {
        name: 'Ingestion API',
        port: 8000,
        baseUrl: '/api/ingestion',
        icon: FileText,
        description: 'Document fetching, normalization, and processing',
        endpoints: [
            {
                method: 'GET',
                path: '/health',
                description: 'Service health check',
                auth: false,
                response: '{ "status": "healthy" }',
            },
            {
                method: 'POST',
                path: '/v1/ingest/url',
                description: 'Ingest a document from URL',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                body: '{ "url": "https://example.com/document.pdf", "source_system": "generic" }',
                response: '{ "job_id": "uuid", "status": "queued" }',
            },
            {
                method: 'GET',
                path: '/v1/ingest/status/{job_id}',
                description: 'Get ingestion job status',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "job_id": "uuid", "status": "completed", "step": "extraction" }',
            },
        ],
    },
    {
        name: 'Compliance API',
        port: 8500,
        baseUrl: '/api/compliance',
        icon: Shield,
        description: 'Checklists, validation, and gap analysis',
        endpoints: [
            {
                method: 'GET',
                path: '/health',
                description: 'Service health check',
                auth: false,
                response: '{ "status": "healthy" }',
            },
            {
                method: 'GET',
                path: '/checklists',
                description: 'Get compliance checklists',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['industry=food'],
                response: '{ "checklists": [...], "total": 10 }',
            },
            {
                method: 'GET',
                path: '/checklists/{checklistId}',
                description: 'Get specific checklist details',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "id": "uuid", "name": "FSMA 204", "items": [...] }',
            },
            {
                method: 'POST',
                path: '/validate',
                description: 'Validate configuration against rules',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                body: '{ "config": {...}, "ruleset": "fsma_204" }',
                response: '{ "valid": true, "errors": [], "warnings": [...] }',
            },
            {
                method: 'GET',
                path: '/industries',
                description: 'List supported food compliance domains',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "industries": ["food"], "total": 1 }',
            },
        ],
    },
    {
        name: 'Graph API',
        port: 8200,
        baseUrl: '/api/graph',
        icon: Search,
        description: 'FSMA labels, supply chain tracing, and knowledge graph',
        endpoints: [
            {
                method: 'GET',
                path: '/v1/labels/health',
                description: 'Labels service health check',
                auth: false,
                response: '{ "status": "healthy" }',
            },
            {
                method: 'POST',
                path: '/v1/labels/batch/init',
                description: 'Initialize a label batch for FSMA traceability',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                body: '{ "batch_id": "uuid", "product_description": "Romaine Lettuce" }',
                response: '{ "batch_id": "uuid", "status": "initialized" }',
            },
        ],
    },
    {
        name: 'Webhook Ingestion API',
        port: 8002,
        baseUrl: '/api/v1/webhooks',
        icon: FileText,
        description: 'Primary FSMA event ingestion endpoint for CTE batches',
        endpoints: [
            {
                method: 'POST',
                path: '/ingest',
                description: 'Ingest one or more FSMA CTE events. Each event is SHA-256 chain-hashed and linked to the tenant audit trail.',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Tenant-ID'],
                params_table: [
                    { name: 'source', type: 'string', required: false, desc: 'Source system identifier (e.g. "erp", "wms")' },
                    { name: 'events', type: 'CTE[]', required: true, desc: 'Array of Critical Tracking Events' },
                    { name: 'events[].cte_type', type: 'enum', required: true, desc: '"receiving" | "shipping" | "transforming" | "creating"' },
                    { name: 'events[].traceability_lot_code', type: 'string', required: true, desc: 'TLC per FSMA 204 (e.g. GTIN + lot)' },
                    { name: 'events[].product_description', type: 'string', required: true, desc: 'Human-readable product name' },
                    { name: 'events[].quantity', type: 'number', required: true, desc: 'Quantity received/shipped' },
                    { name: 'events[].unit_of_measure', type: 'string', required: true, desc: '"cases" | "lbs" | "kg" | "pallets"' },
                    { name: 'events[].location_name', type: 'string', required: true, desc: 'Facility name or GLN' },
                    { name: 'events[].timestamp', type: 'ISO 8601', required: true, desc: 'Event timestamp with timezone' },
                    { name: 'events[].kdes', type: 'object', required: false, desc: 'Key Data Elements (supplier_lot, po_number, carrier, etc.)' },
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
                            receiving_location: "Distribution Center #4"
                        }
                    }]
                }, null, 2),
                response: JSON.stringify({
                    accepted: 1,
                    rejected: 0,
                    total: 1,
                    events: [{
                        event_id: "evt_9f8e7d6c5b4a",
                        status: "accepted",
                        sha256_hash: "sha256:a1b2c3d4e5f6..."
                    }]
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
        name: 'FSMA Traceability API',
        port: 8200,
        baseUrl: '/v1/fsma',
        icon: Leaf,
        description: 'Supply chain tracing, mock recalls, and FDA 24-hour exports',
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
                description: 'Generate FDA-compliant sortable spreadsheet (CSV)',
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
                    grade: "B+",
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
        GET: 'bg-re-info-muted0',
        POST: 'bg-re-success-muted0',
        PUT: 'bg-re-warning',
        DELETE: 'bg-re-danger-muted0',
    };

    return (
        <div className="border rounded-lg overflow-hidden">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center gap-3 p-3 text-left hover:bg-muted/50 transition-colors"
            >
                {expanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <Badge className={`${methodColors[endpoint.method]} text-white font-mono text-xs`}>
                    {endpoint.method}
                </Badge>
                <code className="font-mono text-sm flex-1">{endpoint.path}</code>
                {endpoint.auth && (
                    <Badge variant="outline" className="text-xs">
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

export default function ApiReferencePage() {
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
                                        www.regengine.co
                                    </Badge>
                                </div>
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
                                    <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-1">Example: Paginating Compliance Checklists</h4>
                                    <CodeBlock code={`# First page
GET /checklists?industry=food?limit=20

# Next page
GET /checklists?industry=food?limit=20&cursor=eyJpZCI6IjEyMyJ9`} language="http" />
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
                            <div className="bg-re-warning-muted dark:bg-re-warning/20 border border-re-warning dark:border-re-warning rounded p-3 mt-3">
                                <p className="text-xs text-re-warning dark:text-re-warning">
                                    <strong>Tier Limits:</strong> Growth (500/min), Scale (1,000/min), Enterprise (custom)
                                </p>
                            </div>
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
