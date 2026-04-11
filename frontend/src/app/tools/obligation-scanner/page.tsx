"use client";

import Link from 'next/link';
import { AlertTriangle, ArrowRight, Shield } from 'lucide-react';
import { EmailGate } from '@/components/tools/EmailGate';

const OBLIGATIONS = [
    {
        title: 'CTE Capture Coverage',
        citation: '21 CFR 1.1325-1.1350',
        description: 'Document how receiving, transformation, shipping, and other applicable Critical Tracking Events are captured across each facility.',
        evidence: ['cte_type', 'event_timestamp', 'facility_identifier', 'linked_traceability_lot_code'],
        risk: 'HIGH',
    },
    {
        title: 'KDE Completeness',
        citation: '21 CFR 1.1325-1.1350',
        description: 'Verify required Key Data Elements are stored and retrievable for each event and Food Traceability List product.',
        evidence: ['product_description', 'quantity', 'unit_of_measure', 'ship_from', 'ship_to'],
        risk: 'HIGH',
    },
    {
        title: '24-Hour FDA Export Readiness',
        citation: '21 CFR 1.1455(c)',
        description: 'Confirm traceability records can be exported in sortable form within 24 hours of FDA request.',
        evidence: ['export_job_log', 'csv_preview', 'tenant_scope', 'request_audit_trail'],
        risk: 'HIGH',
    },
    {
        title: 'Supplier Onboarding Controls',
        citation: 'FSMA 204 operational readiness',
        description: 'Ensure suppliers provide consistent lot, facility, and shipment data before records enter the traceability system.',
        evidence: ['supplier_profile', 'facility_roster', 'bulk_upload_validation', 'api_key_provisioning'],
        risk: 'MEDIUM',
    },
    {
        title: 'Tamper-Evident Record Integrity',
        citation: 'RegEngine evidence chain',
        description: 'Maintain immutable hashes and verification history for ingested traceability events and downstream exports.',
        evidence: ['sha256_hash', 'chain_hash', 'verification_status', 'export_hash'],
        risk: 'MEDIUM',
    },
];

export default function ObligationScannerPage() {
    return (
        <EmailGate toolName="obligation-scanner">
        <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            <section className="max-w-[1080px] mx-auto px-6 py-20">
                <div className="max-w-[760px]">
                    <p className="text-xs uppercase tracking-[0.12em] text-[var(--re-brand)] mb-3">FSMA Obligation Scanner</p>
                    <h1 className="text-[clamp(32px,4vw,48px)] font-bold text-[var(--re-text-primary)] leading-tight">
                        Review the core obligations behind FSMA 204 traceability readiness
                    </h1>
                    <p className="mt-4 text-lg text-[var(--re-text-muted)] leading-relaxed">
                        This tool now focuses only on the food-traceability obligations RegEngine supports in the current product wedge.
                    </p>
                </div>

                <div className="mt-10 grid gap-4">
                    {OBLIGATIONS.map((obligation) => (
                        <article key={obligation.title} className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6">
                            <div className="flex flex-wrap items-center gap-3 mb-3">
                                <Shield className="h-5 w-5 text-[var(--re-brand)]" />
                                <h2 className="text-xl font-semibold text-[var(--re-text-primary)]">{obligation.title}</h2>
                                <span className="rounded-full bg-[var(--re-brand-muted)] px-3 py-1 text-xs font-semibold text-[var(--re-brand)]">
                                    {obligation.risk} priority
                                </span>
                            </div>
                            <p className="text-sm text-[var(--re-text-muted)] mb-3">{obligation.citation}</p>
                            <p className="text-base text-[var(--re-text-secondary)] mb-4">{obligation.description}</p>
                            <div className="flex flex-wrap gap-2">
                                {obligation.evidence.map((item) => (
                                    <span key={item} className="rounded-full border border-[var(--re-surface-border)] px-3 py-1 text-xs text-[var(--re-text-primary)]">
                                        {item}
                                    </span>
                                ))}
                            </div>
                        </article>
                    ))}
                </div>

                <div className="mt-10 rounded-2xl border border-[rgba(245,158,11,0.24)] bg-[rgba(245,158,11,0.08)] p-6">
                    <div className="flex items-start gap-3">
                        <AlertTriangle className="h-5 w-5 text-re-warning mt-0.5" />
                        <div>
                            <p className="font-semibold text-[var(--re-text-primary)]">Next step</p>
                            <p className="mt-1 text-sm text-[var(--re-text-muted)]">
                                Use the FSMA docs and data-quality tools to validate actual CTE/KDE coverage and export readiness.
                            </p>
                        </div>
                    </div>
                </div>

                <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/docs/fsma-204" className="inline-flex items-center justify-center h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold">
                        FSMA 204 Guide
                        <ArrowRight className="ml-2 h-4 w-4" />
                    </Link>
                    <Link href="/tools/kde-checker" className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
                        KDE Checker
                    </Link>
                    <Link href="/tools/cte-mapper" className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
                        CTE Mapper
                    </Link>
                </div>
            </section>
        </main>
        </EmailGate>
    );
}
