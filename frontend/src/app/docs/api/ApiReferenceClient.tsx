'use client';

import { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
    FileText,
    ChevronDown,
    ChevronRight,
    Copy,
    Check,
    Database,
    FileDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';

import { PageHeader } from '@/components/layout/page-header';
import { CodeBlock } from '@/components/ui/code-block';
import { INGEST_RESPONSE_SAMPLE, ingestSamplePayload } from '@/lib/api-samples/ingest-samples';
import requiredKdes from '@/lib/api-samples/required-kdes.json';

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
        name: 'JSON Events API',
        baseUrl: '/api/v1/webhooks',
        icon: FileText,
        description: 'Primary FSMA event ingestion endpoint for CTE batches',
        endpoints: [
            {
                method: 'POST',
                path: '/ingest',
                description: 'Ingest one or more FSMA CTE events (up to 500 per request). Requires the webhooks.ingest scope and an active subscription. The body must be signed: X-Webhook-Signature is "sha256=" plus the HMAC-SHA256 hex digest of the exact request bytes, keyed with the signing secret RegEngine issues to you. Idempotency-Key is required: the same key with the same bytes replays the first successful response for 24 hours, including a 200 that rejected events; the same key with different bytes returns 409. A valid request returns 200 even when some events are rejected, so check each event\'s status. Accepted events are written permanently and may be billed.',
                auth: true,
                headers: ['X-RegEngine-API-Key', 'X-Webhook-Signature', 'Idempotency-Key'],
                params_table: [
                    { name: 'source', type: 'string', required: true, desc: 'Source system identifier (e.g. "erp", "wms", "sensitech", "tive", "manual")' },
                    { name: 'events', type: 'CTE[]', required: true, desc: 'Array of Critical Tracking Events (max 500 per batch)' },
                    { name: 'events[].cte_type', type: 'enum', required: true, desc: '"harvesting" | "cooling" | "initial_packing" | "first_land_based_receiving" | "shipping" | "receiving" | "transformation"' },
                    { name: 'events[].traceability_lot_code', type: 'string', required: true, desc: 'TLC per FSMA 204 (e.g. GTIN + lot, min 3 chars)' },
                    { name: 'events[].product_description', type: 'string', required: true, desc: 'Human-readable product name (1 to 500 chars)' },
                    { name: 'events[].quantity', type: 'number', required: true, desc: 'Quantity (> 0)' },
                    { name: 'events[].unit_of_measure', type: 'string', required: true, desc: '"cases" | "lbs" | "kg" | "pallets" | "each" (full list in docs)' },
                    { name: 'events[].location_name', type: 'string', required: false, desc: 'Facility name. Each event needs at least one location: location_name, events[].location_gln (a 13-digit GLN), or a location KDE. harvesting, cooling, initial_packing and transformation events also require location_name itself.' },
                    { name: 'events[].timestamp', type: 'ISO 8601', required: true, desc: 'Event time with timezone. An event older than 90 days comes back with status "rejected" inside a 200. An event more than 24 hours ahead fails the whole request with a 422 and nothing is stored.' },
                    { name: 'events[].kdes', type: 'object', required: true, desc: 'CTE-specific Key Data Elements per 21 CFR §§1.1325 to 1.1350. Each cte_type has its own required keys; see Required KDEs by event type, below the endpoint list.' },
                ],
                body: ingestSamplePayload('"<current UTC time, ISO 8601>"', '"<today, YYYY-MM-DD>"'),
                response: INGEST_RESPONSE_SAMPLE,
            },
        ],
    },
    {
        name: 'Records API',
        baseUrl: '/api/v1/records',
        icon: Database,
        description: 'Read canonical traceability events with full provenance: what it is, where it came from, what rules were applied, what failed, what must happen next',
        endpoints: [
            {
                method: 'GET',
                path: '',
                description: 'List and search canonical traceability events. Requires an API key with the records.read scope. Keys are tenant-bound, so results are always scoped to your workspace, and no tenant_id or X-Tenant-ID is needed.',
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
                    tenant_id: "<your workspace ID>",
                    events: [{
                        event_id: "0b9c2f4e-6d1a-4c53-9a7e-5f3d8e21c7ab",
                        event_type: "receiving",
                        traceability_lot_code: "TEST-00012345678901-LOT-001",
                        product_reference: "Romaine Lettuce",
                        quantity: 500.0,
                        unit_of_measure: "cases",
                        from_facility_reference: "Distribution Center #4",
                        to_facility_reference: "Distribution Center #4",
                        event_timestamp: "<the event timestamp>",
                        source_system: "webhook_api",
                        status: "active",
                        confidence_score: 1.0,
                        schema_version: "<schema version>",
                        created_at: "<when RegEngine stored it>"
                    }],
                    total: 1
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/{event_id}',
                description: 'Full record detail: the normalized fields, kdes, provenance_metadata, raw_payload, rule_evaluations, exception_cases, and the amendment_chain when the record amends an earlier one.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "event_id": "0b9c2f4e-6d1a-4c53-9a7e-5f3d8e21c7ab", "event_type": "receiving", "kdes": {...}, "provenance_metadata": {...}, "raw_payload": {...}, "rule_evaluations": [...], "exception_cases": [...] }',
            },
            {
                method: 'GET',
                path: '/{event_id}/history',
                description: 'Amendment chain for a record: every correction with who, when, and why',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                response: '{ "event_id": "0b9c2f4e-6d1a-4c53-9a7e-5f3d8e21c7ab", "amendment_chain": [...] }',
            },
        ],
    },
    {
        name: 'FDA Trace & Export API',
        baseUrl: '/api/v1/fda',
        icon: FileDown,
        description: 'Lot tracing and FDA-oriented exports from stored tenant evidence, with cryptographic verification. Every endpoint here needs an active subscription and returns 402 without one.',
        endpoints: [
            {
                method: 'GET',
                path: '/trace/{tlc}',
                description: 'Trace the transformation graph for a traceability lot code (upstream sources and downstream products). Requires the fda.read scope. Unlike the Records API, FDA endpoints take tenant_id as an explicit query parameter (it must match your key’s workspace).',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-workspace-uuid}'],
                response: JSON.stringify({
                    seed_tlc: "TEST-00012345678901-LOT-001",
                    tenant_id: "<your workspace ID>",
                    traversal_depth: 5,
                    node_count: 1,
                    edge_count: 0,
                    nodes: [{ tlc: "TEST-00012345678901-LOT-001", is_seed: true, role: "seed", event_count: 1 }],
                    edges: [],
                    total_events: 1
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/export',
                description: 'Generate an FDA-oriented export for a traceability lot code (the 24-hour traceability request format). Requires the fda.export scope. format is "package" (a ZIP bundle, the default), "csv", or "pdf".',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-workspace-uuid}', 'tlc=TEST-00012345678901-LOT-001', 'format=csv'],
                response: 'A file download: text/csv, application/pdf, or application/zip, depending on format',
            },
            {
                method: 'GET',
                path: '/export/v2',
                description: 'Generate an FDA export from the canonical record model (v2), with provenance and rule-evaluation status per row. Requires the fda.export scope.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-workspace-uuid}', 'start_date=2026-01-01', 'end_date=2026-01-31'],
                response: 'A file download (CSV or ZIP package) derived from canonical records',
            },
            {
                method: 'GET',
                path: '/export/recall',
                description: 'Recall-filtered FDA export: only events matching the product, location, lot code, or event type you filter on. Requires the fda.export scope.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-workspace-uuid}', 'tlc=TEST-00012345678901-LOT-001'],
                response: 'A file download (CSV or ZIP package) scoped to the filters',
            },
            {
                method: 'POST',
                path: '/export/verify',
                description: 'Re-generate a previous export with the same parameters and compare its hash to the original. Requires the fda.verify scope. Both values go in the query string; there is no request body.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-workspace-uuid}', 'export_id={id from /export/history}'],
                response: JSON.stringify({
                    export_id: "<export id>",
                    original_hash: "<hash recorded at export time>",
                    regenerated_hash: "<hash of the regenerated export>",
                    hashes_match: true,
                    original_record_count: 1,
                    current_record_count: 1,
                    data_integrity: "VERIFIED",
                    original_generated_at: "<when the export was generated>",
                    verified_at: "<now>"
                }, null, 2),
            },
            {
                method: 'GET',
                path: '/export/history',
                description: 'List previously generated exports with their hashes. Requires the fda.read scope.',
                auth: true,
                headers: ['X-RegEngine-API-Key'],
                params: ['tenant_id={your-workspace-uuid}'],
                response: JSON.stringify({
                    tenant_id: "<your workspace ID>",
                    exports: [{
                        id: "<export id>",
                        export_type: "<export type>",
                        query_tlc: "TEST-00012345678901-LOT-001",
                        record_count: 1,
                        export_hash: "<hash of the export>",
                        generated_by: "<who generated it>",
                        generated_at: "<when>"
                    }],
                    total: 1
                }, null, 2),
            },
        ],
    },
];

/** Section label inside an endpoint panel - the only uppercase in the system (SPEC §2.2). */
const PANEL_LABEL = 'font-mono text-label uppercase text-re-text-muted';

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <Button
            size="sm"
            variant="ghost"
            onClick={handleCopy}
            aria-label={copied ? 'Copied' : 'Copy'}
            className="h-6 w-6 p-0"
        >
            {copied ? (
                <Check aria-hidden="true" strokeWidth={1.75} className="h-3 w-3 text-re-success" />
            ) : (
                <Copy aria-hidden="true" strokeWidth={1.75} className="h-3 w-3" />
            )}
        </Button>
    );
}

function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="overflow-hidden rounded-lg border border-re-border">
            <button
                onClick={() => setExpanded(!expanded)}
                aria-expanded={expanded}
                className="flex w-full flex-wrap items-center gap-2 p-3 text-left transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none sm:gap-3"
            >
                {expanded ? (
                    <ChevronDown aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 flex-shrink-0 text-re-text-muted" />
                ) : (
                    <ChevronRight aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 flex-shrink-0 text-re-text-muted" />
                )}
                <Badge tone="neutral" size="sm" mono>
                    {endpoint.method}
                </Badge>
                <code className="min-w-0 flex-[1_1_150px] break-all font-mono text-[0.8125rem] text-re-text-primary">{endpoint.path}</code>
                {endpoint.auth && (
                    <Badge tone="neutral" size="sm" className="ml-6 sm:ml-0">
                        Auth
                    </Badge>
                )}
            </button>

            {expanded && (
                <div className="space-y-4 border-t border-re-border-subtle p-4">
                    <p className="text-ui text-re-text-secondary">{endpoint.description}</p>

                    {endpoint.headers && (
                        <div>
                            <h4 className={`${PANEL_LABEL} mb-1`}>Headers</h4>
                            <div className="flex flex-wrap gap-1">
                                {endpoint.headers.map((h) => (
                                    <Badge key={h} tone="neutral" size="sm" mono>
                                        {h}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {endpoint.params && (
                        <div>
                            <h4 className={`${PANEL_LABEL} mb-1`}>Query Params</h4>
                            <div className="flex flex-wrap gap-1">
                                {endpoint.params.map((p) => (
                                    <Badge key={p} tone="neutral" size="sm" mono>
                                        {p}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {endpoint.params_table && (
                        <div>
                            <h4 className={`${PANEL_LABEL} mb-2`}>Parameters</h4>
                            <div className="overflow-hidden rounded-lg border border-re-border bg-re-surface-card">
                                <Table className="min-w-[32rem] text-small">
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead className="w-[14rem]">Name</TableHead>
                                            <TableHead className="w-[7rem]">Type</TableHead>
                                            <TableHead className="w-[7rem]">Required</TableHead>
                                            <TableHead>Description</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {endpoint.params_table.map((p) => (
                                            <TableRow key={p.name}>
                                                <TableCell className="break-all font-mono text-[0.8125rem]">{p.name}</TableCell>
                                                <TableCell className="font-mono text-[0.8125rem] text-re-text-tertiary">{p.type}</TableCell>
                                                <TableCell>
                                                    {p.required ? (
                                                        <Badge tone="danger" size="sm">required</Badge>
                                                    ) : (
                                                        <span className="text-re-text-tertiary">optional</span>
                                                    )}
                                                </TableCell>
                                                <TableCell className="text-re-text-tertiary">{p.desc}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        </div>
                    )}

                    {endpoint.body && (
                        <div>
                            <div className="mb-1 flex items-center justify-between">
                                <h4 className={PANEL_LABEL}>Request Body</h4>
                                <CopyButton text={endpoint.body} />
                            </div>
                            <CodeBlock code={endpoint.body} language="json" />
                        </div>
                    )}

                    <div>
                        <div className="mb-1 flex items-center justify-between">
                            <h4 className={PANEL_LABEL}>Response</h4>
                            <CopyButton text={endpoint.response} />
                        </div>
                        <CodeBlock code={endpoint.response} language="json" />
                    </div>
                </div>
            )}
        </div>
    );
}

const ERROR_CODES = [
    { code: '400', desc: 'Bad Request: Missing Idempotency-Key or invalid parameters' },
    { code: '401', desc: 'Unauthorized: Missing or invalid API key, or a missing or wrong ingest signature' },
    { code: '402', desc: 'Payment Required: No active subscription for the workspace' },
    { code: '403', desc: 'Forbidden: Key lacks the required scope, or tenant_id / X-Tenant-ID names a different workspace' },
    { code: '404', desc: "Not Found: Resource doesn't exist" },
    { code: '409', desc: 'Conflict: Idempotency-Key reused with different request bytes' },
    { code: '422', desc: 'Unprocessable: Request body failed validation' },
    { code: '429', desc: 'Too Many Requests: Rate limited' },
    { code: '500', desc: 'Internal Error: Contact support' },
];

const RATE_LIMIT_HEADERS = [
    { header: 'X-RateLimit-Limit', desc: 'Max requests per window' },
    { header: 'X-RateLimit-Remaining', desc: 'Requests left in window' },
    { header: 'X-RateLimit-Reset', desc: 'When limit resets (epoch)' },
];

/** A key/value well - one surface step below the card it sits on (SPEC §5.1). */
const WELL = 'rounded-md border border-re-border-subtle bg-re-surface-inset p-3';

export function ApiReferenceClient() {
    const [selectedService, setSelectedService] = useState(0);
    const reduceMotion = useReducedMotion();

    // SPEC §5.2: framer-motion is capped at opacity + ≤8px translate / 180ms
    // and is switched off entirely under prefers-reduced-motion.

    return (
        <>
            <PageHeader
                title="API Reference"
                description="Complete documentation for all RegEngine API endpoints"
                meta={<Badge tone="neutral" size="sm" mono>v1.0.0</Badge>}
            />

            <motion.div
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}
                className="space-y-6"
            >
                {/* Authentication Info */}
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Authentication</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <p className="text-ui text-re-text-secondary">
                            Authenticated endpoints require this header:
                        </p>
                        <div>
                            <div className={WELL}>
                                <code className="font-mono text-[0.8125rem] text-re-text-primary">
                                    X-RegEngine-API-Key: rge_live_...
                                </code>
                                <p className="mt-1 text-small text-re-text-tertiary">
                                    Standard API access (tenant-scoped). An Authorization header is not accepted.
                                </p>
                            </div>
                        </div>
                        <p className="text-ui text-re-text-secondary">
                            RegEngine issues the key, your workspace ID, and the ingest signing secret on request. The workspace is taken from the key,
                            so do not send <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary">X-Tenant-ID</code>:
                            a value that differs from the key&apos;s workspace is refused with a 403. Ingest also needs{' '}
                            <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary">X-Webhook-Signature</code>.
                        </p>
                    </CardContent>
                </Card>

                {/* Service Navigation */}
                <div className="flex flex-wrap gap-2">
                    {API_SERVICES.map((service, i) => {
                        const Icon = service.icon;
                        const isSelected = selectedService === i;
                        return (
                            <Button
                                key={service.name}
                                variant={isSelected ? 'secondary' : 'ghost'}
                                aria-pressed={isSelected}
                                onClick={() => setSelectedService(i)}
                                className="gap-2"
                            >
                                <Icon aria-hidden="true" className="h-4 w-4" />
                                {service.name}
                                <Badge tone="neutral" size="sm" className="ml-1">
                                    {service.endpoints.length} endpoint{service.endpoints.length !== 1 ? 's' : ''}
                                </Badge>
                            </Button>
                        );
                    })}
                </div>

                {/* Selected Service Details */}
                <motion.div
                    key={selectedService}
                    initial={reduceMotion ? false : { opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}
                >
                    <Card>
                        <CardHeader>
                            <div className="min-w-0">
                                <CardTitle>{API_SERVICES[selectedService].name}</CardTitle>
                                <CardDescription>
                                    {API_SERVICES[selectedService].description}
                                </CardDescription>
                                <div className="mt-2 flex flex-wrap items-center gap-2">
                                    <Badge tone="neutral" size="sm" mono>
                                        Base URL: {API_SERVICES[selectedService].baseUrl}
                                    </Badge>
                                    <Badge tone="neutral" size="sm" mono>
                                        {API_SERVICES[selectedService].provisioned ? 'provisioned endpoint' : 'regengine.co'}
                                    </Badge>
                                </div>
                                {API_SERVICES[selectedService].provisioned && (
                                    <p className="mt-2 text-small text-re-text-tertiary">
                                        Available on contracted workspaces. These endpoints are served from your
                                        workspace&apos;s provisioned endpoint URL (supplied during onboarding), not the
                                        public regengine.co base URL. JSON Events API, Records, and FDA
                                        Trace &amp; Export above are the publicly reachable surface.
                                    </p>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {API_SERVICES[selectedService].endpoints.map((endpoint, i) => (
                                <EndpointCard key={i} endpoint={endpoint} />
                            ))}
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Required KDEs per event type: required-kdes.json is diffed against the backend table by tests/docs. */}
                <Card id="required-kdes" className="scroll-mt-24">
                    <CardHeader>
                        <div>
                            <CardTitle>Required KDEs by event type</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <p className="text-ui text-re-text-secondary">
                            Every event needs <code className="font-mono text-[0.8125rem] text-re-text-primary">traceability_lot_code</code>,{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">product_description</code>,{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">quantity</code> and{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">unit_of_measure</code> on the event itself. The
                            rest depend on <code className="font-mono text-[0.8125rem] text-re-text-primary">cte_type</code>. Event-level fields
                            sit beside <code className="font-mono text-[0.8125rem] text-re-text-primary">cte_type</code>; the others go inside{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">kdes</code>. A missing one rejects that event
                            inside a 200 with <code className="font-mono text-[0.8125rem] text-re-text-primary">Missing required KDE &apos;&hellip;&apos;</code>.
                        </p>
                        <div className="overflow-hidden rounded-lg border border-re-border bg-re-surface-card">
                            <Table className="min-w-[32rem] text-small">
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-[14rem]">cte_type</TableHead>
                                        <TableHead>Also required on the event</TableHead>
                                        <TableHead>Required in kdes</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {Object.entries(requiredKdes).map(([cteType, row]) => (
                                        <TableRow key={cteType}>
                                            <TableCell className="break-all font-mono text-[0.8125rem]">{cteType}</TableCell>
                                            <TableCell className="font-mono text-[0.8125rem] text-re-text-tertiary">
                                                {row.top_level.length > 0 ? row.top_level.join(', ') : 'None'}
                                            </TableCell>
                                            <TableCell className="font-mono text-[0.8125rem] text-re-text-tertiary">
                                                {row.kdes.join(', ')}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    </CardContent>
                </Card>

                {/* Pagination Info */}
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Pagination</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <p className="text-ui text-re-text-secondary">
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">GET /api/v1/records</code> pages with{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">limit</code> and{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">offset</code>. The response carries{' '}
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">total</code>, the number of matching records.
                        </p>
                        <div className="space-y-4">
                            <div>
                                <h4 className={`${PANEL_LABEL} mb-2`}>Request Parameters</h4>
                                <div className="grid gap-3 md:grid-cols-2">
                                    <div className={WELL}>
                                        <code className="font-mono text-[0.8125rem] text-re-text-primary">limit</code>
                                        <span className="ml-2 text-small text-re-text-tertiary">(default: 50, max: 500)</span>
                                        <p className="mt-1 text-small text-re-text-tertiary">
                                            Number of items to return per page
                                        </p>
                                    </div>
                                    <div className={WELL}>
                                        <code className="font-mono text-[0.8125rem] text-re-text-primary">offset</code>
                                        <span className="ml-2 text-small text-re-text-tertiary">(default: 0)</span>
                                        <p className="mt-1 text-small text-re-text-tertiary">
                                            Number of items to skip
                                        </p>
                                    </div>
                                </div>
                            </div>
                            <div>
                                <h4 className={`${PANEL_LABEL} mb-2`}>Example: Paginating Records</h4>
                                <CodeBlock code={`# First page
GET /api/v1/records?limit=20

# Next page
GET /api/v1/records?limit=20&offset=20`} language="http" />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Rate Limiting Info */}
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Rate Limiting</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <p className="text-ui text-re-text-secondary">
                            API requests are rate limited. When you exceed a limit the API returns a 429. Stop sending for
                            60 seconds, then retry. Some successful responses also carry these headers; treat them as optional and
                            do not rely on them being present, and do not rely on any header on a 429.
                        </p>
                        <div className="grid gap-3 md:grid-cols-3">
                            {RATE_LIMIT_HEADERS.map((item) => (
                                <div key={item.header} className={WELL}>
                                    <code className="font-mono text-[0.8125rem] text-re-text-primary">{item.header}</code>
                                    <p className="mt-1 text-small text-re-text-tertiary">
                                        {item.desc}
                                    </p>
                                </div>
                            ))}
                        </div>
                        <p className="mt-3 text-small text-re-text-tertiary">
                            See <a href="/docs/rate-limits" className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand">Rate Limits</a> for details.
                        </p>
                    </CardContent>
                </Card>

                {/* Error Codes */}
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Error Codes</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <ul className="grid list-none gap-3 text-ui md:grid-cols-2">
                            {ERROR_CODES.map((item) => (
                                <li key={item.code} className="flex items-start gap-3">
                                    <Badge tone="danger" size="sm" mono>{item.code}</Badge>
                                    <span className="min-w-0 text-re-text-secondary">{item.desc}</span>
                                </li>
                            ))}
                        </ul>
                    </CardContent>
                </Card>
            </motion.div>
        </>
    );
}
