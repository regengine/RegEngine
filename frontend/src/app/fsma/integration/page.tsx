import React from 'react';
import { PageContainer } from '@/components/layout/page-container';
import { Code, FileSpreadsheet, ScanLine, ArrowRight, CheckCircle2 } from 'lucide-react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';

export const metadata = {
    title: 'Data Integration Hub | RegEngine FSMA 204',
    description: 'Explore the three frictionless paths to connect your supply chain to RegEngine for FSMA 204 compliance.',
};

export default function IntegrationHubPage() {
    return (
        <div className="min-h-screen pb-24" style={{ background: 'var(--re-surface-base)' }}>
            <PageContainer>
                <div className="pt-8 pb-12">
                    <h1 className="text-3xl font-bold tracking-tight text-foreground mb-4">Data Integration Hub</h1>
                    <p className="text-muted-foreground text-lg max-w-3xl">
                        Meet FSMA 204 records-keeping obligations without ripping out your current ERP. RegEngine acts as an overlay data layer that captures the CTEs and KDEs your operations require under 21 CFR Part 1, Subpart S — your operation remains responsible for compliance.
                    </p>
                </div>
                <div className="space-y-12">
                    {/* ─── INTRO ─── */}
                    <div className="rounded-2xl border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 p-6 md:p-8">
                        <div className="flex flex-col md:flex-row gap-6 items-start">
                            <div className="flex-1">
                                <Badge variant="outline" className="mb-3 text-[var(--re-brand)] border-[var(--re-brand)]/30">ZERO DISRUPTION</Badge>
                                <h2 className="text-2xl font-bold text-foreground mb-3">
                                    The &quot;Overlay&quot; Traceability Model
                                </h2>
                                <p className="text-muted-foreground leading-relaxed">
                                    RegEngine doesn&apos;t replace your WMS or inventory management system. We capture the Critical Tracking Events your operations require — Harvesting and Cooling (§1.1325), Initial Packing (§1.1330) for RACs other than from a fishing vessel, First Land-Based Receiving (§1.1335) for seafood from a fishing vessel, Shipping (§1.1340), Receiving (§1.1345, subject to §1.1305(j) restaurant/RFE exemption), and Transformation (§1.1350) — link them to your Traceability Lot Codes, and store them with SHA-256 manifests so you can produce a sortable electronic spreadsheet within 24 hours of an FDA request under §1.1455(c).
                                </p>
                            </div>
                            <div className="shrink-0 w-full md:w-[320px] bg-background/50 backdrop-blur-sm rounded-xl border p-4">
                                <div className="text-xs font-mono text-muted-foreground mb-3 uppercase tracking-wider">The Data Flow</div>
                                <div className="space-y-3">
                                    <div className="flex items-center gap-3 text-sm">
                                        <div className="w-8 h-8 rounded-lg bg-[var(--re-brand)]/10 flex items-center justify-center text-[var(--re-brand)] shrink-0">1</div>
                                        <span className="text-foreground">Connect your data source</span>
                                    </div>
                                    <div className="w-0.5 h-4 bg-border ml-4"></div>
                                    <div className="flex items-center gap-3 text-sm">
                                        <div className="w-8 h-8 rounded-lg bg-[var(--re-accent-purple)]/10 flex items-center justify-center text-[var(--re-accent-purple)] shrink-0">2</div>
                                        <span className="text-foreground">RegEngine hashes &amp; links records</span>
                                    </div>
                                    <div className="w-0.5 h-4 bg-border ml-4"></div>
                                    <div className="flex items-center gap-3 text-sm">
                                        <div className="w-8 h-8 rounded-lg bg-[var(--re-success)]/10 flex items-center justify-center text-[var(--re-success)] shrink-0">3</div>
                                        <span className="text-foreground">Records ready for §1.1455(c) production</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ─── INGESTION PATHS ─── */}
                    <div>
                        <h3 className="text-xl font-bold text-foreground mb-6">Choose Your Connection Path</h3>
                        <div className="grid md:grid-cols-3 gap-6">

                            {/* API / EPCIS */}
                            <div className="group relative rounded-2xl border bg-background p-6 transition-all hover:border-[var(--re-accent-blue)]/50 hover:shadow-lg hover:shadow-[var(--re-accent-blue)]/5">
                                <div className="w-12 h-12 rounded-xl bg-[var(--re-accent-blue)]/10 flex items-center justify-center text-[var(--re-accent-blue)] mb-6">
                                    <Code className="w-6 h-6" />
                                </div>
                                <h4 className="text-lg font-bold text-foreground mb-2">API &amp; EPCIS 2.0</h4>
                                <p className="text-sm text-muted-foreground mb-6 line-clamp-3">
                                    For enterprise systems (SAP, Oracle, NetSuite). Push events directly to our endpoints via Webhooks or standard GS1 EPCIS 2.0 XML/JSON payloads.
                                </p>

                                <div className="rounded-lg bg-black/40 border border-white/5 p-4 mb-6 relative overflow-hidden">
                                    <div className="text-[10px] font-mono text-muted-foreground mb-2 uppercase tracking-wider">POST /events/ingest</div>
                                    <pre className="overflow-x-auto text-xs font-mono text-re-brand">
                                        {`{
  "tlc": "GTIN-1002-4A",
  "cte_type": "RECEIVING",
  "facility_gln": "0860000100",
  "timestamp": "2024-11-20T..."
}`}
                                    </pre>
                                </div>

                                <Link href="/developer/register" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--re-accent-blue)] hover:underline">
                                    Get Developer Access <ArrowRight className="w-4 h-4" />
                                </Link>
                            </div>

                            {/* File Upload / CSV */}
                            <div className="group relative rounded-2xl border bg-background p-6 transition-all hover:border-[var(--re-brand)]/50 hover:shadow-lg hover:shadow-[var(--re-brand)]/5">
                                <div className="w-12 h-12 rounded-xl bg-[var(--re-brand)]/10 flex items-center justify-center text-[var(--re-brand)] mb-6">
                                    <FileSpreadsheet className="w-6 h-6" />
                                </div>
                                <h4 className="text-lg font-bold text-foreground mb-2">File Drop (CSV/Excel)</h4>
                                <p className="text-sm text-muted-foreground mb-6 line-clamp-3">
                                    Perfect for mid-market operators. Export a daily BOL or receiving log from your current system and drop it into RegEngine. We handle the data mapping automatically.
                                </p>

                                <div className="rounded-lg border border-dashed border-border bg-muted/30 p-6 flex flex-col items-center justify-center text-center gap-2 mb-6 h-[140px]">
                                    <FileSpreadsheet className="w-6 h-6 text-muted-foreground/50" />
                                    <div className="text-sm font-medium text-foreground">Drag &amp; Drop CSV File</div>
                                    <div className="text-xs text-muted-foreground">Supported: .csv, .xlsx</div>
                                </div>

                                <Link href="/tools/data-import" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--re-brand)] hover:underline">
                                    Map Your Columns <ArrowRight className="w-4 h-4" />
                                </Link>
                            </div>

                            {/* Manual Entry */}
                            <div className="group relative rounded-2xl border bg-background p-6 transition-all hover:border-[var(--re-accent-purple)]/50 hover:shadow-lg hover:shadow-[var(--re-accent-purple)]/5">
                                <div className="w-12 h-12 rounded-xl bg-[var(--re-accent-purple)]/10 flex items-center justify-center text-[var(--re-accent-purple)] mb-6">
                                    <ScanLine className="w-6 h-6" />
                                </div>
                                <h4 className="text-lg font-bold text-foreground mb-2">Label &amp; Barcode Capture</h4>
                                <p className="text-sm text-muted-foreground mb-6 line-clamp-3">
                                    Essential for small growers, vessels, or one-off corrections. Scan a GS1 barcode or upload a label photo and RegEngine extracts the lot code, GTIN, and KDEs for your records.
                                </p>

                                <div className="rounded-lg border bg-surface p-4 space-y-3 mb-6 relative overflow-hidden h-[140px]">
                                    <div className="h-8 rounded bg-muted/50 border flex items-center px-3 text-xs text-muted-foreground">Scan GS1 barcode...</div>
                                    <div className="h-8 rounded bg-muted/50 border flex items-center px-3 text-xs text-muted-foreground">Upload label photo</div>
                                    <div className="h-8 rounded bg-[var(--re-accent-purple)]/20 border border-[var(--re-accent-purple)]/30 flex items-center justify-center text-xs font-medium text-[var(--re-accent-purple)]">Extract KDEs</div>
                                </div>

                                <Link href="/tools/label-scanner" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--re-accent-purple)] hover:underline">
                                    Try Label Capture <ArrowRight className="w-4 h-4" />
                                </Link>
                            </div>

                        </div>
                    </div>

                    {/* ─── DATA MAPPING PREVIEW ─── */}
                    <div className="mt-16 pt-12 border-t">
                        <div className="text-center mb-8">
                            <h3 className="text-2xl font-bold text-foreground mb-3">Intelligent Field Mapping</h3>
                            <p className="text-muted-foreground max-w-2xl mx-auto">
                                Don&apos;t worry if your current lot numbers or column headers don&apos;t perfectly match the FDA terminology. RegEngine provides a visual mapping tool to translate your operational language into regulatory compliance.
                            </p>
                        </div>

                        <div className="max-w-4xl mx-auto rounded-3xl border bg-surface/50 overflow-hidden shadow-2xl">
                            {/* Fake Browser header */}
                            <div className="flex items-center gap-2 px-4 py-3 border-b bg-background">
                                <div className="flex gap-1.5">
                                    <div className="w-2.5 h-2.5 rounded-full bg-re-danger-muted0/80"></div>
                                    <div className="w-2.5 h-2.5 rounded-full bg-re-warning-muted0/80"></div>
                                    <div className="w-2.5 h-2.5 rounded-full bg-re-success-muted0/80"></div>
                                </div>
                                <div className="ml-4 text-xs font-mono text-muted-foreground">RegEngine Mapping Tool</div>
                            </div>

                            <div className="p-6 md:p-8">
                                <div className="grid md:grid-cols-2 gap-8">
                                    {/* Left Side: Uploaded Data */}
                                    <div className="space-y-4">
                                        <div className="text-sm font-bold text-foreground mb-4">Your Uploaded CSV Headers</div>
                                        {['Internal_Lot_Num', 'Ship_Date', 'Loc_ID', 'Item_Desc'].map((col) => (
                                            <div key={col} className="flex items-center justify-between p-3 rounded-lg border bg-background">
                                                <span className="font-mono text-sm text-muted-foreground">{col}</span>
                                                <ArrowRight className="w-4 h-4 text-muted-foreground" />
                                            </div>
                                        ))}
                                    </div>

                                    {/* Right Side: RegEngine Target */}
                                    <div className="space-y-4">
                                        <div className="text-sm font-bold text-foreground mb-4">FSMA 204 Regulatory Fields (KDEs)</div>
                                        {['Traceability Lot Code (TLC)', 'Event Timestamp', 'Facility ID (GLN)', 'Product Description'].map((col) => (
                                            <div key={col} className="flex items-center gap-3 p-3 rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5">
                                                <CheckCircle2 className="w-4 h-4 text-[var(--re-brand)]" />
                                                <span className="font-medium text-sm text-foreground">{col}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                </div>
            </PageContainer>
        </div>
    );
}
