import type { Metadata } from 'next';
import Link from 'next/link';
import {
    CAPABILITY_REGISTRY,
    DELIVERY_MODE_LABELS,
    INTEGRATION_TYPE_LABELS,
    INTEGRATION_TYPE_DESCRIPTIONS,
    INTEGRATION_TYPE_VERIFY,
    STATUS_LABELS,
    SUPPORT_CHANNELS,
    TRUST_ARTIFACTS,
} from '@/lib/customer-readiness';
import type { IntegrationType } from '@/lib/customer-readiness';
import { TRUST_SUBPROCESSORS } from '@/lib/trust-subprocessors';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCaption,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { StatTile } from '@/components/ui/stat-tile';

export const metadata: Metadata = {
    title: 'Trust Center | RegEngine',
    description: 'Customer diligence surface for product status, retention, support, deployment posture, and available security artifacts.',
    openGraph: {
        title: 'Trust Center | RegEngine',
        description: 'Customer diligence surface for RegEngine FSMA 204 deployments and support posture.',
        url: 'https://regengine.co/trust',
        type: 'website',
    },
};
const STATUS_SUMMARY = [
    {
        label: 'Implemented',
        detail: 'Core FSMA workspace, exports, dashboard flows, and public documentation surfaces are available for contracted workspaces.',
    },
    {
        label: 'Supported',
        detail: 'Capability is available where the relevant workspace, plan, or workflow has been enabled.',
    },
    {
        label: 'Preview',
        detail: 'Capability is usable for evaluation in supported workspaces, but is not GA. GS1 EPCIS 2.0 export and ingest stay Preview until separately promoted.',
    },
    {
        label: 'Pilot',
        detail: 'Capability exists but should be treated as guided rollout or customer-specific onboarding work.',
    },
    {
        label: 'Design Partner',
        detail: 'Reserved for customers needing custom integration, implementation support, or pilot collaboration.',
    },
    {
        label: 'Export Supported',
        detail: 'RegEngine can prepare outbound packages, but does not claim a managed portal integration.',
    },
    {
        label: 'File Import Supported',
        detail: 'Customer data can be onboarded through CSV upload with mapping review and exception handling.',
    },
    {
        label: 'Custom Scoped',
        detail: 'Requires customer-specific mapping, implementation, or support before production use.',
    },
    {
        label: 'Preparation',
        detail: 'Roadmap or diligence-preparation item; not a public commitment unless included in an executed agreement.',
    },
    {
        label: 'Contract-only',
        detail: 'Available commitments are governed by the executed agreement, DPA, or NDA package.',
    },
];

const TRUST_AT_A_GLANCE = [
    {
        tier: 'Public',
        title: 'Published diligence pages',
        detail: 'Trust, Security, DPA, Privacy, Terms, Architecture, Retention, and Support pages are available for buyer review.',
    },
    {
        tier: 'Request/NDA',
        title: 'Security evidence package',
        detail: 'Approved diligence materials, identity/graph hardening notes, and completed artifacts are shared when applicable.',
    },
    {
        tier: 'Contract-only',
        title: 'Binding commitments',
        detail: 'SLA, retention, deletion, subprocessor notice, escalation, and support terms live in the executed agreement or DPA.',
    },
    {
        tier: 'Not claimed',
        title: 'No overclaim posture',
        detail: 'No SOC 2 certification, third-party penetration-test report, FDA endorsement, or public availability commitment is claimed.',
    },
];

const DILIGENCE_SHORTCUTS = [
    { title: 'Security', detail: 'Controls, verifier posture, disclosure path', href: '/security', tier: 'Public' },
    { title: 'DPA', detail: 'Processor terms and subprocessor summary', href: '/dpa', tier: 'Public' },
    { title: 'Subprocessors', detail: 'Shared vendor list and locations', href: '#subprocessors', tier: 'Public' },
    { title: 'Retention', detail: 'Deletion, return, backup, and archive boundaries', href: '/trust/retention', tier: 'Public' },
    { title: 'Architecture', detail: 'Topology, data flow, and tenant isolation', href: '/trust/architecture', tier: 'Public' },
    { title: 'Claims matrix', detail: 'Allowed wording and evidence owner map', href: '/contact', tier: 'Request/NDA' },
];

const PROSE_LINK =
    'text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand';

const OPERATIONAL_REALITIES = [
    'Source-system fields must be mapped into FSMA CTE and KDE structures.',
    'Lot codes, GLNs, product IDs, and facility identities have to be normalized.',
    'Missing KDEs and conflicting facility matches still require human review.',
    'Cryptographic hashing provides tamper-evidence after ingest, not proof of upstream data entry.',
];

const RETENTION_BOUNDARIES = [
    'Customers should schedule recurring exports and maintain off-platform archives from day one.',
    'Public support windows are not a substitute for recall-readiness operations.',
    'Premium escalation and SLA terms are contractual, not implied by public pricing copy.',
    'Security and diligence materials are a mix of public pages and request/NDA workflows.',
];

const POSITIONING = [
    {
        title: 'Evidence layer (current posture)',
        detail: 'You own the data and compliance posture. RegEngine documents, normalizes, and exports it. Audit response liability remains with the customer.',
    },
    {
        title: 'Not a system of record',
        detail: 'RegEngine does not replace your ERP, WMS, or operational food safety system. Source data quality is inherited from upstream systems.',
    },
    {
        title: 'Full data portability',
        detail: 'Supported workflows can export CTE events, KDE fields, lot records, and supplier relationships in EPCIS 2.0 JSON-LD (Preview), FDA-oriented sortable spreadsheet, or CSV.',
    },
    {
        title: 'Tenant isolation',
        detail: 'PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict cross-tenant reads on core PostgreSQL-backed paths. Identity-resolution and graph-layer hardening is in progress; details available under NDA.',
    },
];

const UPSTREAM_QUALITY = [
    {
        title: 'Ingestion validation',
        items: [
            'Per-CTE-type required KDE validation (7 CTE types)',
            'GLN format and GS1 check-digit verification',
            'Rejects events more than 24 hours in the future or more than 90 days old (configurable)',
            'Unit of measure validation against FSMA 204 standard units',
            'Location requirement validation per CTE',
        ],
    },
    {
        title: 'Rejection and flagging',
        items: [
            'Missing required KDEs trigger event rejection with detailed error messages',
            'Obligation-gap alerts are surfaced asynchronously; rule enforcement is configurable per deployment and is advisory in production today',
            'Batch deduplication prevents duplicate CTE submissions',
            'Rejected events returned with status and actionable error detail',
        ],
    },
    {
        title: 'Supplier data quality',
        items: [
            'Per-supplier KDE completeness tracking',
            'Submission history retained for review',
            'Specific scoring and alerting features ship per workspace configuration',
        ],
    },
    {
        title: 'Compliance readiness scoring',
        items: [
            'Six weighted signals: export readiness (30%), KDE completeness (25%), CTE coverage (15%), chain integrity (10%), obligation coverage (10%), FTL product coverage (10%)',
            'Calculated from data in the active workspace',
            'Internal readiness signal, not an FDA endorsement',
        ],
    },
];

const REGULATORY_BASIS = [
    {
        title: 'Current regulatory basis',
        items: [
            'FDA Final Rule: Requirements for Additional Traceability Records (21 CFR Part 1, Subpart S)',
            'Compliance date under the rule: January 20, 2026 (87 FR 70910). The 30-month extension is only proposed (90 FR 38084). FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.',
            'Food Traceability List (FTL): reviewed against FDA publications current as of April 1, 2026',
            'FDA Q&A draft guidance: February 2026; FAQ updates reviewed June 2026',
        ],
    },
    {
        title: 'Update mechanism',
        items: [
            'Validation rules are versioned and reference the underlying FDA guidance',
            'Compliance logic changes are documented in the changelog',
            'FTL category definitions are reviewed against current FDA publications',
            'Customers are responsible for confirming their own regulatory interpretation',
        ],
    },
];

const EXPORT_FORMAT_GROUPS = [
    {
        title: 'Export formats',
        items: [
            'GS1 EPCIS 2.0 JSON-LD (Preview, industry standard)',
            'FDA-oriented sortable spreadsheet aligned to 21 CFR 1.1455 where applicable',
            'CSV with all CTE/KDE fields',
            'Audit evidence bundle with manifest hashing',
        ],
    },
    {
        title: 'Automated export scheduling',
        items: [
            'Export cadence can be scoped per deployment',
            'Archive delivery may use object storage or downloadable bundles',
            'Manifest hashing is part of the intended export posture',
            'Monitoring and retry behavior depend on the configured delivery path',
        ],
    },
];

function Bullets({ items }: { items: string[] }) {
    return (
        <ul className="mt-2 space-y-2 text-ui text-re-text-secondary">
            {items.map((item) => (
                <li key={item} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-muted" aria-hidden="true" />
                    {item}
                </li>
            ))}
        </ul>
    );
}

export default function TrustCenterPage() {
    const capabilityCount = CAPABILITY_REGISTRY.length;

    return (
        <div className="re-page min-h-screen">
            {/* ─── HEADER ─── */}
            <Container className="pb-10 pt-14 sm:pb-14 sm:pt-20">
                <PageHeader
                    size="hero"
                    title="Trust Center"
                    description="Product status, data ownership, retention terms, and diligence materials in one place. Specific commitments (SLAs, retention, security obligations) live in your contract; this page is a starting point for diligence, not a substitute for it."
                    className="mb-0 border-b-0 pb-0"
                />
                <Callout tone="warning" className="mt-6">
                    <div className="text-subheading text-re-text-primary">Pre-production trust posture</div>
                    <p className="mt-2 text-ui text-re-text-secondary">
                        RegEngine is a design-partner oriented FSMA 204 evidence layer. Public pages describe
                        implemented and supported capabilities, not binding service-level commitments. RegEngine does not
                        currently claim SOC 2 certification, a completed third-party penetration test, FDA
                        endorsement, or a public availability commitment. Binding commitments are controlled
                        by the executed agreement, order form, or DPA.
                    </p>
                </Callout>
                <div className="mt-6 grid gap-3 md:grid-cols-2">
                    {TRUST_AT_A_GLANCE.map((item) => (
                        <Card key={item.tier} padding="compact">
                            <div className="flex items-start justify-between gap-3">
                                <div className="text-subheading text-re-text-primary">{item.title}</div>
                                <Badge tone="neutral" size="sm" mono className="shrink-0">{item.tier}</Badge>
                            </div>
                            <p className="mt-2 text-ui text-re-text-secondary">{item.detail}</p>
                        </Card>
                    ))}
                </div>
                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                    <StatTile label="Capability Registry" value={capabilityCount}>
                        <p className="text-small text-re-text-tertiary">Customer-visible entries rendered from one shared status model</p>
                    </StatTile>
                    <StatTile label="Retention" value="Per contract">
                        <p className="text-small text-re-text-tertiary">Post-cancellation retention is set in your agreement.</p>
                    </StatTile>
                    <StatTile label="Data Residency" value="US-configured core">
                        <p className="text-small text-re-text-tertiary">CDN, edge, AI, and storage locations vary by provider and executed DPA.</p>
                    </StatTile>
                </div>
                <div className="mt-6">
                    <div className="mb-3 font-mono text-label uppercase text-re-text-muted">
                        Diligence shortcuts
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {DILIGENCE_SHORTCUTS.map((shortcut) => (
                            <Link key={shortcut.title} href={shortcut.href} className="block no-underline focus-visible:outline-none">
                                <Card variant="interactive" padding="compact" className="h-full">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="text-subheading text-re-text-primary">{shortcut.title}</div>
                                        <Badge tone="neutral" size="sm" mono className="shrink-0">{shortcut.tier}</Badge>
                                    </div>
                                    <p className="mt-2 text-ui text-re-text-secondary">{shortcut.detail}</p>
                                </Card>
                            </Link>
                        ))}
                    </div>
                </div>
            </Container>

            {/* ─── SOURCE-OF-TRUTH POSITIONING (moved up) ─── */}
            <Section
                width="marketing"
                title="Source-of-truth positioning"
                description="RegEngine is a compliance evidence layer, not a system-of-record replacement. This distinction drives retention, audit ownership, and liability boundaries."
            >
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                    {POSITIONING.map((item) => (
                        <Card key={item.title} padding="compact">
                            <div className="text-subheading text-re-text-primary">{item.title}</div>
                            <p className="mt-2 text-ui text-re-text-secondary">{item.detail}</p>
                        </Card>
                    ))}
                </div>
            </Section>

            {/* ─── RETENTION + SUPPORT BOUNDARIES (moved up) ─── */}
            <Section
                width="marketing"
                title="What RegEngine actually does in your stack"
                description="RegEngine ingests upstream traceability data, normalizes it into FSMA workflows, attaches audit-integrity metadata, and prepares FDA- or retailer-oriented exports. It still depends on upstream data quality, stable identities, and review of missing or conflicting KDEs."
            >
                <div className="grid gap-4 md:grid-cols-2">
                    <Card className="p-5">
                        <h3 className="text-subheading text-re-text-primary">Operational realities</h3>
                        <Bullets items={OPERATIONAL_REALITIES} />
                    </Card>
                    <Card className="p-5">
                        <h3 className="text-subheading text-re-text-primary">Retention and support boundaries</h3>
                        <Bullets items={RETENTION_BOUNDARIES} />
                    </Card>
                </div>
            </Section>

            {/* ─── PUBLIC PROOF SURFACE CALLOUT ─── */}
            <Section width="marketing" flush className="py-6 sm:py-8">
                <Card className="p-5">
                    <div className="text-subheading text-re-text-primary">Verify supported evidence bundles yourself</div>
                    <p className="mt-2 text-ui text-re-text-secondary">
                        Supported evidence export workflows can include SHA-256 manifests for independent verification. Drop a supported bundle into <Link href="/verify" className={PROSE_LINK}>/verify</Link> to check it yourself.
                    </p>
                </Card>
            </Section>

            {/* ─── ARTIFACTS ─── */}
            <Section
                width="marketing"
                title="Artifacts and diligence materials"
                description="Public pages are linked directly. Request and NDA items route through contact."
            >
                <div className="grid gap-3 md:grid-cols-2">
                    {TRUST_ARTIFACTS.map((artifact) => (
                        <Card key={artifact.id} padding="compact">
                            <div className="flex items-center justify-between gap-3">
                                <div className="text-subheading text-re-text-primary">{artifact.title}</div>
                                <span className="shrink-0 font-mono text-label uppercase text-re-text-muted">{artifact.access}</span>
                            </div>
                            <p className="mt-2 text-ui text-re-text-secondary">{artifact.summary}</p>
                            <Link href={artifact.href} className={`mt-3 inline-block text-ui ${PROSE_LINK}`}>
                                Open →
                            </Link>
                        </Card>
                    ))}
                </div>
            </Section>

            {/* ─── DATA PORTABILITY ─── */}
            <Section
                width="marketing"
                title="Data portability and exit rights"
                description="Exports use open standards (GS1 EPCIS 2.0 (Preview), the FDA sortable spreadsheet, CSV) so records can be read and stored outside RegEngine. Re-import into another system depends on that system's ingest support for the chosen format."
            >
                <div className="grid gap-3 md:grid-cols-2">
                    <Card padding="compact">
                        <div className="text-subheading text-re-text-primary">{EXPORT_FORMAT_GROUPS[0].title}</div>
                        <Bullets items={EXPORT_FORMAT_GROUPS[0].items} />
                    </Card>
                    <Card padding="compact">
                        <div className="text-subheading text-re-text-primary">Integrity and chain of custody</div>
                        <ul className="mt-2 space-y-2 text-ui text-re-text-secondary">
                            <li className="flex items-start gap-2">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-muted" aria-hidden="true" />
                                Supported evidence workflows can hash and chain-link accepted events
                            </li>
                            <li className="flex items-start gap-2">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-muted" aria-hidden="true" />
                                Timestamped manifests are generated where the configured export workflow supports them
                            </li>
                            <li className="flex items-start gap-2">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-muted" aria-hidden="true" />
                                <span>Public verification endpoint at <Link href="/verify" className={PROSE_LINK}>/verify</Link></span>
                            </li>
                            <li className="flex items-start gap-2">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-muted" aria-hidden="true" />
                                Legacy Kafka-compatible signing exists for opt-in deployments; the default deployment uses PostgreSQL-backed task processing instead of a managed message bus
                            </li>
                        </ul>
                    </Card>
                    <Card padding="compact">
                        <div className="text-subheading text-re-text-primary">{EXPORT_FORMAT_GROUPS[1].title}</div>
                        <Bullets items={EXPORT_FORMAT_GROUPS[1].items} />
                    </Card>
                </div>
            </Section>

            {/* ─── UPSTREAM DATA QUALITY ─── */}
            <Section
                width="marketing"
                title="Upstream data quality controls"
                description="RegEngine validates incoming CTE/KDE records at ingestion time. Incomplete or non-compliant records are rejected or flagged before they enter the compliance evidence chain."
            >
                <div className="grid gap-3 md:grid-cols-2">
                    {UPSTREAM_QUALITY.map((group) => (
                        <Card key={group.title} padding="compact">
                            <div className="text-subheading text-re-text-primary">{group.title}</div>
                            <Bullets items={group.items} />
                        </Card>
                    ))}
                </div>
            </Section>

            {/* ─── REGULATORY INTERPRETATION ─── */}
            <Section
                width="marketing"
                title="Regulatory interpretation tracking"
                description="FSMA 204 compliance logic embeds vendor interpretation of FDA guidance. RegEngine tracks and documents which guidance versions inform its validation rules, export formats, and compliance algorithms."
            >
                <div className="grid gap-3 md:grid-cols-2">
                    {REGULATORY_BASIS.map((group) => (
                        <Card key={group.title} padding="compact">
                            <div className="text-subheading text-re-text-primary">{group.title}</div>
                            <Bullets items={group.items} />
                        </Card>
                    ))}
                </div>
            </Section>

            {/* ─── SUPPORT + ARCHIVE ─── */}
            <Section width="marketing">
                <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                    <Card className="p-5">
                        <h2 className="mb-2 font-display text-heading-lg text-re-text-primary">Support and escalation</h2>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Support posture depends on plan tier. Customers should not rely on ad hoc vendor intervention for statutory retention or a live recall response. Specific availability, latency, RPO, and RTO commitments are negotiated per contract; we do not publish SLA numbers we are not yet measuring against a public status page.
                        </p>
                        <div className="space-y-3">
                            {SUPPORT_CHANNELS.map((channel) => (
                                <Card key={channel.tier} variant="inset" padding="compact">
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="text-subheading text-re-text-primary">{channel.tier}</div>
                                        <div className="font-mono text-[0.8125rem] text-re-text-tertiary">{channel.responseWindow}</div>
                                    </div>
                                    <p className="mt-2 text-ui text-re-text-secondary">{channel.escalation}</p>
                                    <p className="mt-2 text-small text-re-text-tertiary">{channel.notes}</p>
                                </Card>
                            ))}
                        </div>
                    </Card>
                    <Card className="p-5">
                        <h2 className="mb-2 font-display text-heading-lg text-re-text-primary">Scheduled exports</h2>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Hashing, manifests, run history, and scheduled delivery depend on the
                            configured workflow and customer agreement.
                        </p>
                        <Card variant="inset" padding="compact">
                            <div className="text-subheading text-re-text-primary">No data yet</div>
                            <p className="mt-2 text-ui text-re-text-secondary">
                                No public export-job configurations are published. Scheduled exports are
                                configured per workspace.
                            </p>
                        </Card>
                        <Link href="/dashboard/export-jobs" className={`mt-4 inline-block text-ui ${PROSE_LINK}`}>
                            Open export jobs →
                        </Link>
                    </Card>
                </div>
            </Section>

            {/* Subprocessors */}
            <Section
                id="subprocessors"
                width="marketing"
                className="scroll-mt-24"
                title="Infrastructure and subprocessors"
                description="Third-party services that process or store customer data. This table is rendered from the same shared list used by the public DPA page, but your executed DPA remains the contractual source of truth."
            >
                <Card className="overflow-hidden">
                    <Table className="min-w-[720px]">
                        <TableCaption className="sr-only">Infrastructure and subprocessors</TableCaption>
                        <TableHeader>
                            <TableRow>
                                <TableHead scope="col">Provider</TableHead>
                                <TableHead scope="col">Use</TableHead>
                                <TableHead scope="col">Purpose</TableHead>
                                <TableHead scope="col">Data processed</TableHead>
                                <TableHead scope="col">Location</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {TRUST_SUBPROCESSORS.map((sp) => (
                                <TableRow key={sp.name}>
                                    <TableCell>{sp.name}</TableCell>
                                    <TableCell>{sp.availabilityLabel}</TableCell>
                                    <TableCell>{sp.purpose}</TableCell>
                                    <TableCell>{sp.dataProcessed}</TableCell>
                                    <TableCell>{sp.location}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Card>
                <p className="mt-4 text-small text-re-text-tertiary">
                    Last reviewed: June 2026. The authoritative subprocessor list for your contract is in your executed DPA; the table above is informational and may lag the DPA. Notice periods for subprocessor changes are set in your agreement.
                </p>
            </Section>

            {/* ─── CAPABILITY REGISTRY (collapsible for technical diligence) ─── */}
            <Section width="marketing">
                <Card className="overflow-hidden">
                    <details>
                        <summary className="flex cursor-pointer select-none items-center justify-between gap-4 p-5">
                            <div>
                                <h2 className="inline font-display text-heading-lg text-re-text-primary">Full Capability Registry</h2>
                                <span className="ml-2 text-ui text-re-text-secondary">(for technical diligence)</span>
                            </div>
                            <span className="shrink-0 text-ui text-re-text-tertiary">Click to expand</span>
                        </summary>
                        <div className="px-5 pb-5">
                            {/* Status model */}
                            <h3 className="mb-3 text-heading text-re-text-primary">Status model</h3>
                            <div className="mb-8 grid gap-3 md:grid-cols-2">
                                {STATUS_SUMMARY.map((item) => (
                                    <Card key={item.label} variant="inset" padding="compact">
                                        <div className="text-subheading text-re-text-primary">{item.label}</div>
                                        <p className="mt-1 text-ui text-re-text-secondary">{item.detail}</p>
                                    </Card>
                                ))}
                            </div>
                            {/* Integration classification */}
                            <h3 className="mb-3 text-heading text-re-text-primary">Integration classification</h3>
                            <p className="mb-6 max-w-[68ch] text-ui text-re-text-secondary">
                                Each integration is classified by both delivery mode and integration type. Integration type uses the procurement diligence taxonomy: Standards-Based Ingest / Export, API-Based Custom, File-Based Import, or One-Way Export Adapter.
                            </p>
                            <div className="mb-8 grid gap-3 md:grid-cols-2">
                                {(Object.keys(INTEGRATION_TYPE_LABELS) as IntegrationType[]).map((type) => (
                                    <Card key={type} variant="inset" padding="compact">
                                        <div className="text-subheading text-re-text-primary">{INTEGRATION_TYPE_LABELS[type]}</div>
                                        <p className="mt-1 text-ui text-re-text-secondary">{INTEGRATION_TYPE_DESCRIPTIONS[type]}</p>
                                        <p className="mt-2 text-small text-re-text-tertiary">Verify: {INTEGRATION_TYPE_VERIFY[type]}</p>
                                    </Card>
                                ))}
                            </div>
                            {/* Full capability table */}
                            <Card className="overflow-hidden">
                                <Table className="min-w-[880px]">
                                    <TableCaption className="sr-only">Full Capability Registry</TableCaption>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead scope="col">Capability</TableHead>
                                            <TableHead scope="col">Status</TableHead>
                                            <TableHead scope="col">Integration type</TableHead>
                                            <TableHead scope="col">Delivery mode</TableHead>
                                            <TableHead scope="col">Customer meaning</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {CAPABILITY_REGISTRY.map((item) => (
                                            <TableRow key={item.id} className="align-top">
                                                <TableCell>{item.name}</TableCell>
                                                <TableCell>{STATUS_LABELS[item.status]}</TableCell>
                                                <TableCell>{INTEGRATION_TYPE_LABELS[item.integration_type]}</TableCell>
                                                <TableCell>{DELIVERY_MODE_LABELS[item.delivery_mode]}</TableCell>
                                                <TableCell>{item.customer_copy}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </Card>
                        </div>
                    </details>
                </Card>
            </Section>
        </div>
    );
}
