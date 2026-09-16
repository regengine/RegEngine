"use client";

import Link from 'next/link';
import { AlertTriangle, ArrowRight } from 'lucide-react';
import { EmailGate } from '@/components/tools/EmailGate';
import { Container } from '@/components/layout/container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';

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
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            <Container width="tool">
                <div className="border-b border-re-border-subtle pb-5">
                    <p className="mb-2 text-label text-re-text-muted">FSMA Obligation Scanner</p>
                    <h1 className="text-title text-re-text-primary">
                        Review the core obligations behind FSMA 204 traceability readiness
                    </h1>
                    <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                        This tool now focuses only on the food-traceability obligations RegEngine supports in the current product wedge.
                    </p>
                </div>

                <div className="mt-8 grid gap-4">
                    {OBLIGATIONS.map((obligation) => (
                        <article key={obligation.title}>
                            <Card>
                                <CardContent>
                                    <div className="mb-3 flex flex-wrap items-center gap-3">
                                        <h2 className="text-subheading text-re-text-primary">{obligation.title}</h2>
                                        <Badge tone={obligation.risk === 'HIGH' ? 'warning' : 'neutral'} mono>
                                            {obligation.risk} priority
                                        </Badge>
                                    </div>
                                    <p className="mb-3 font-mono text-[0.8125rem] text-re-text-tertiary">{obligation.citation}</p>
                                    <p className="mb-4 text-ui text-re-text-secondary">{obligation.description}</p>
                                    <div className="flex flex-wrap gap-2">
                                        {obligation.evidence.map((item) => (
                                            <Badge key={item} tone="neutral" mono size="sm">
                                                {item}
                                            </Badge>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        </article>
                    ))}
                </div>

                <Callout tone="warning" role="note" icon={AlertTriangle} title="Next step" className="mt-8">
                    Use the FSMA docs and data-quality tools to validate actual CTE/KDE coverage and export readiness.
                </Callout>

                <div className="mt-8 flex flex-wrap gap-3">
                    <Button asChild size="lg">
                        <Link href="/docs/fsma-204">
                            FSMA 204 Guide
                            <ArrowRight aria-hidden="true" className="ml-2 h-4 w-4" strokeWidth={1.75} />
                        </Link>
                    </Button>
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/tools/kde-checker">
                            KDE Checker
                        </Link>
                    </Button>
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/tools/cte-mapper">
                            CTE Mapper
                        </Link>
                    </Button>
                </div>
            </Container>
        </div>
        </EmailGate>
    );
}
