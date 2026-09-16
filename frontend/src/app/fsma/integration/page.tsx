import React from 'react';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Code, FileSpreadsheet, ScanLine, ArrowRight, CheckCircle2 } from 'lucide-react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const metadata = {
    title: 'Data Integration Hub | RegEngine FSMA 204',
    description: 'Explore the three frictionless paths to connect your supply chain to RegEngine for FSMA 204 compliance.',
};

const DATA_FLOW = [
    'Connect your data source',
    'RegEngine hashes & links records',
    'Records ready for §1.1455(c) production',
];

const MAPPING_ROWS = [
    { from: 'Internal_Lot_Num', to: 'Traceability Lot Code (TLC)' },
    { from: 'Ship_Date', to: 'Event Timestamp' },
    { from: 'Loc_ID', to: 'Facility ID (GLN)' },
    { from: 'Item_Desc', to: 'Product Description' },
];

export default function IntegrationHubPage() {
    return (
        <PageContainer>
            <PageHeader
                title="Data Integration Hub"
                description="Meet FSMA 204 records-keeping obligations without ripping out your current ERP. RegEngine acts as an overlay data layer that captures the CTEs and KDEs your operations require under 21 CFR Part 1, Subpart S — your operation remains responsible for compliance."
            />

            <div className="space-y-12">
                {/* ─── INTRO ─── */}
                <Card padding="spacious">
                    <div className="flex flex-col items-start gap-6 md:flex-row">
                        <div className="min-w-0 flex-1">
                            <Badge tone="neutral" size="sm" mono className="mb-3">ZERO DISRUPTION</Badge>
                            <h2 className="mb-3 text-heading text-re-text-primary">
                                The &quot;Overlay&quot; Traceability Model
                            </h2>
                            <p className="text-ui leading-relaxed text-re-text-secondary">
                                RegEngine doesn&apos;t replace your WMS or inventory management system. We capture the Critical Tracking Events your operations require — Harvesting and Cooling (§1.1325), Initial Packing (§1.1330) for RACs other than from a fishing vessel, First Land-Based Receiving (§1.1335) for seafood from a fishing vessel, Shipping (§1.1340), Receiving (§1.1345, subject to §1.1305(j) restaurant/RFE exemption), and Transformation (§1.1350) — link them to your Traceability Lot Codes, and store them with SHA-256 manifests so you can produce a sortable electronic spreadsheet within 24 hours of an FDA request under §1.1455(c).
                            </p>
                        </div>
                        <div className="w-full shrink-0 rounded-lg border border-re-border-subtle bg-re-surface-inset p-4 md:w-[320px]">
                            <p className="mb-3 text-label text-re-text-muted">The Data Flow</p>
                            <ol className="space-y-3">
                                {DATA_FLOW.map((label, index) => (
                                    <li key={label} className="flex items-center gap-3 text-ui text-re-text-secondary">
                                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-re-border bg-re-surface-card font-mono text-label tabular-nums text-re-text-primary">
                                            {index + 1}
                                        </span>
                                        <span>{label}</span>
                                    </li>
                                ))}
                            </ol>
                        </div>
                    </div>
                </Card>

                {/* ─── INGESTION PATHS ─── */}
                <div>
                    <h3 className="mb-6 text-heading text-re-text-primary">Choose Your Connection Path</h3>
                    <div className="grid gap-6 md:grid-cols-3">

                        {/* API / EPCIS */}
                        <Card variant="interactive" padding="spacious" className="flex flex-col">
                            <Code className="mb-6 h-5 w-5 text-re-cat-1" strokeWidth={1.75} aria-hidden="true" />
                            <h4 className="mb-2 text-subheading text-re-text-primary">API &amp; EPCIS 2.0</h4>
                            <p className="mb-6 text-ui text-re-text-secondary">
                                For enterprise systems (SAP, Oracle, NetSuite). Push events directly to our endpoints via Webhooks or standard GS1 EPCIS 2.0 XML/JSON payloads.
                            </p>

                            <div className="mb-6 rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                                <p className="mb-2 text-label text-re-text-muted">POST /events/ingest</p>
                                <pre className="overflow-x-auto font-mono text-[0.8125rem] text-re-text-secondary">
                                    {`{
  "tlc": "GTIN-1002-4A",
  "cte_type": "RECEIVING",
  "facility_gln": "0860000100",
  "timestamp": "2024-11-20T..."
}`}
                                </pre>
                            </div>

                            <Link
                                href="/developer/register"
                                className="mt-auto inline-flex items-center gap-2 text-ui font-medium text-re-brand underline-offset-[3px] hover:underline"
                            >
                                Get Developer Access
                                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Card>

                        {/* File Upload / CSV */}
                        <Card variant="interactive" padding="spacious" className="flex flex-col">
                            <FileSpreadsheet className="mb-6 h-5 w-5 text-re-cat-3" strokeWidth={1.75} aria-hidden="true" />
                            <h4 className="mb-2 text-subheading text-re-text-primary">File Drop (CSV/Excel)</h4>
                            <p className="mb-6 text-ui text-re-text-secondary">
                                Perfect for mid-market operators. Export a daily BOL or receiving log from your current system and drop it into RegEngine. We handle the data mapping automatically.
                            </p>

                            <div className="mb-6 flex h-[140px] flex-col items-center justify-center gap-2 rounded-md border border-dashed border-re-border bg-re-surface-inset px-4 text-center">
                                <FileSpreadsheet className="h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                <p className="text-ui font-medium text-re-text-primary">Drag &amp; Drop CSV File</p>
                                <p className="text-small text-re-text-tertiary">Supported: .csv, .xlsx</p>
                            </div>

                            <Link
                                href="/tools/data-import"
                                className="mt-auto inline-flex items-center gap-2 text-ui font-medium text-re-brand underline-offset-[3px] hover:underline"
                            >
                                Map Your Columns
                                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Card>

                        {/* Manual Entry */}
                        <Card variant="interactive" padding="spacious" className="flex flex-col">
                            <ScanLine className="mb-6 h-5 w-5 text-re-cat-4" strokeWidth={1.75} aria-hidden="true" />
                            <h4 className="mb-2 text-subheading text-re-text-primary">Label &amp; Barcode Capture</h4>
                            <p className="mb-6 text-ui text-re-text-secondary">
                                Essential for small growers, vessels, or one-off corrections. Scan a GS1 barcode or upload a label photo and RegEngine extracts the lot code, GTIN, and KDEs for your records.
                            </p>

                            <div className="mb-6 h-[140px] space-y-3 rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                                <p className="flex h-8 items-center rounded-md border border-re-border bg-re-surface-card px-3 text-small text-re-text-tertiary">Scan GS1 barcode...</p>
                                <p className="flex h-8 items-center rounded-md border border-re-border bg-re-surface-card px-3 text-small text-re-text-tertiary">Upload label photo</p>
                                <p className="flex h-8 items-center justify-center rounded-md border border-re-border-strong bg-re-surface-card px-3 text-small font-medium text-re-text-primary">Extract KDEs</p>
                            </div>

                            <Link
                                href="/tools/label-scanner"
                                className="mt-auto inline-flex items-center gap-2 text-ui font-medium text-re-brand underline-offset-[3px] hover:underline"
                            >
                                Try Label Capture
                                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Card>

                    </div>
                </div>

                {/* ─── DATA MAPPING PREVIEW ─── */}
                <div className="border-t border-re-border-subtle pt-12">
                    <div className="mb-8 max-w-[68ch]">
                        <h3 className="mb-3 text-heading text-re-text-primary">Intelligent Field Mapping</h3>
                        <p className="text-ui text-re-text-secondary">
                            Don&apos;t worry if your current lot numbers or column headers don&apos;t perfectly match the FDA terminology. RegEngine provides a visual mapping tool to translate your operational language into regulatory compliance.
                        </p>
                    </div>

                    <Card>
                        <CardHeader>
                            <CardTitle className="font-mono text-label text-re-text-muted">RegEngine Mapping Tool</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid gap-8 md:grid-cols-2">
                                {/* Left Side: Uploaded Data */}
                                <div>
                                    <p className="mb-4 text-label text-re-text-muted">Your Uploaded CSV Headers</p>
                                    <div className="space-y-2">
                                        {MAPPING_ROWS.map((row) => (
                                            <div key={row.from} className="flex items-center justify-between gap-3 rounded-md border border-re-border bg-re-surface-card px-3 py-2">
                                                <span className="truncate font-mono text-[0.8125rem] text-re-text-secondary">{row.from}</span>
                                                <ArrowRight className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Right Side: RegEngine Target */}
                                <div>
                                    <p className="mb-4 text-label text-re-text-muted">FSMA 204 Regulatory Fields (KDEs)</p>
                                    <div className="space-y-2">
                                        {MAPPING_ROWS.map((row) => (
                                            <div key={row.to} className="flex items-center gap-3 rounded-md border border-re-border bg-re-surface-inset px-3 py-2">
                                                <CheckCircle2 className="h-4 w-4 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                <span className="truncate text-ui font-medium text-re-text-primary">{row.to}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>

            </div>
        </PageContainer>
    );
}
