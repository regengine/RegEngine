'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
    AlertTriangle,
    ArrowRight,
    Archive,
    Braces,
    CheckCircle2,
    ClipboardCheck,
    FileSpreadsheet,
    FlaskConical,
    GitBranch,
    Play,
    RefreshCcw,
    Save,
    ShieldCheck,
    Terminal,
} from 'lucide-react';
import {
    CAPABILITY_REGISTRY,
    DELIVERY_MODE_LABELS,
    INTEGRATION_TYPE_LABELS,
    type CapabilityRegistryEntry,
    type CustomerVisibleStatus,
    type MappingReviewItem,
    STATUS_LABELS,
    getCapabilitiesByCategory,
} from '@/lib/customer-readiness';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { experimentalFeaturesEnabled, filterExperimentalLinks } from '@/lib/experimental-features';
import type {
    CreateIntegrationProfileRequest,
    IntegrationProfile,
    IntegrationProfileSourceType,
    MappingPreviewResponse,
} from '@/types/api';

const CATEGORY_LABELS = [
    { id: 'food_safety_iot' as const, title: 'Food safety & IoT' },
    { id: 'erp_warehouse' as const, title: 'ERP & warehouse' },
    { id: 'retailer_network' as const, title: 'Retailer exports' },
    { id: 'developer_api' as const, title: 'Developer APIs' },
];

/** Registry status is a tone on a Badge, not a bespoke tinted chip. */
const STATUS_TONES: Record<CustomerVisibleStatus, BadgeTone> = {
    implemented: 'success',
    supported: 'success',
    export_supported: 'info',
    file_import_supported: 'info',
    pilot: 'warning',
    design_partner: 'warning',
    custom_scoped: 'neutral',
    preparation: 'neutral',
    contract_only: 'neutral',
};

const INFLOW_CONNECTOR = CAPABILITY_REGISTRY.find((item) => item.id === 'inflow-lab');

const INFLOW_FACTS = [
    ['Public slug', 'inflow-lab'],
];

const INFLOW_PATH = [
    ['Simulator', 'FSMA 204 event batch'],
    ['Webhook ingest', '/api/v1/webhooks/ingest'],
    ['Alias resolution', 'inflow-lab -> inflow_lab'],
    ['Dashboard source', 'Tagged as Inflow Lab'],
];

const ROUTE_GUIDANCE = [
    {
        title: 'Import Data',
        description: 'Upload documents, CSV, XML, or spreadsheet files that need parsing before compliance use.',
        href: '/ingest',
        icon: FileSpreadsheet,
    },
    {
        title: 'Curation Queue',
        description: 'Review normalized records and KDE mapping issues before publication.',
        href: '/ingest/curation',
        icon: ClipboardCheck,
    },
    {
        title: 'Inflow Lab',
        description: 'Run FSMA event simulations and webhook replay without mixing test traffic into normal imports.',
        href: '/dashboard/inflow-lab',
        icon: FlaskConical,
    },
    {
        title: 'FDA Export',
        description: 'Generate export jobs after records are curated and ready for regulator response.',
        href: '/dashboard/export-jobs',
        icon: Archive,
    },
];

type MappingReviewResponse = {
    items?: MappingReviewItem[];
    meta?: {
        status?: string;
        message?: string;
    };
};

const PROFILE_FIELDS = [
    ['cte_type', 'CTE type'],
    ['traceability_lot_code', 'Traceability lot code'],
    ['product_description', 'Product description'],
    ['quantity', 'Quantity'],
    ['unit_of_measure', 'Unit of measure'],
    ['timestamp', 'Event timestamp'],
    ['ship_from_location', 'Ship from'],
    ['ship_to_location', 'Ship to'],
    ['reference_document', 'Reference document'],
] as const;

const DEFAULT_PROFILE_MAPPING = {
    cte_type: 'event_type',
    traceability_lot_code: 'lot_code',
    product_description: 'item_description',
    quantity: 'case_count',
    unit_of_measure: 'uom',
    timestamp: 'ship_date',
    ship_from_location: 'origin_facility',
    ship_to_location: 'destination_facility',
    reference_document: 'bol_number',
};

const DEFAULT_PREVIEW_EVENT = JSON.stringify([
    {
        event_type: 'shipping',
        lot_code: 'TLC-ROMAINE-0426',
        item_description: 'Romaine hearts',
        case_count: 24,
        uom: 'cases',
        ship_date: '2026-04-30T15:00:00Z',
        origin_facility: 'FreshPack Central',
        destination_facility: 'DC-17',
        bol_number: 'BOL-88921',
    },
], null, 2);

export default function DashboardIntegrationsPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();
    const [items, setItems] = useState<MappingReviewItem[]>([]);
    const [meta, setMeta] = useState<MappingReviewResponse['meta']>();
    const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');
    const [profiles, setProfiles] = useState<IntegrationProfile[]>([]);
    const [profilesStatus, setProfilesStatus] = useState<'idle' | 'loading' | 'error'>('loading');
    const [profileError, setProfileError] = useState<string | null>(null);
    const [profileName, setProfileName] = useState('FreshPack shipping CSV');
    const [supplierName, setSupplierName] = useState('FreshPack Central');
    const [sourceType, setSourceType] = useState<IntegrationProfileSourceType>('csv');
    const [defaultCteType, setDefaultCteType] = useState('shipping');
    const [profileNotes, setProfileNotes] = useState('Supplier uses BOL number for FSMA reference document.');
    const [fieldMapping, setFieldMapping] = useState<Record<string, string>>({ ...DEFAULT_PROFILE_MAPPING });
    const [savingProfile, setSavingProfile] = useState(false);
    const [previewProfileId, setPreviewProfileId] = useState('');
    const [previewEventText, setPreviewEventText] = useState(DEFAULT_PREVIEW_EVENT);
    const [previewResult, setPreviewResult] = useState<MappingPreviewResponse | null>(null);
    const [previewError, setPreviewError] = useState<string | null>(null);
    const [previewing, setPreviewing] = useState(false);

    useEffect(() => {
        // The former anonymous BFF was a placeholder that proxied any future
        // upstream 2xx response without tenant authentication. Keep the UI
        // honest and local until a classified tenant-scoped contract ships.
        setItems([]);
        setMeta({
            status: 'not_connected',
            message: 'Field mapping review is not yet available on this workspace.',
        });
        setStatus('idle');
    }, []);

    useEffect(() => {
        let cancelled = false;

        async function loadProfiles() {
            if (!isAuthenticated || !tenantId) {
                setProfiles([]);
                setProfilesStatus('idle');
                return;
            }

            setProfilesStatus('loading');
            setProfileError(null);

            try {
                const response = await apiClient.listIntegrationProfiles();
                if (!cancelled) {
                    setProfiles(response.profiles ?? []);
                    setProfilesStatus('idle');
                    setPreviewProfileId((current) => current || response.profiles?.[0]?.profile_id || '');
                }
            } catch {
                if (!cancelled) {
                    setProfiles([]);
                    setProfilesStatus('error');
                    setProfileError('Unable to load saved integration profiles for this workspace.');
                }
            }
        }

        void loadProfiles();

        return () => {
            cancelled = true;
        };
    }, [isAuthenticated, tenantId]);

    const notConnected = meta?.status === 'not_connected';
    const reviewCount = items.filter((item) => item.status !== 'mapped').length;
    const capabilityCount = CAPABILITY_REGISTRY.filter((item) => item.category !== 'commercial').length;
    const liveApiCount = CAPABILITY_REGISTRY.filter((item) => item.status === 'implemented').length;
    const activeProfileCount = profiles.filter((profile) => profile.status === 'active').length;

    const handleMappingChange = (key: string, value: string) => {
        setFieldMapping((current) => ({ ...current, [key]: value }));
    };

    const handleCreateProfile = async () => {
        if (!profileName.trim() || savingProfile) return;

        setSavingProfile(true);
        setProfileError(null);
        try {
            const request: CreateIntegrationProfileRequest = {
                display_name: profileName.trim(),
                supplier_name: supplierName.trim() || undefined,
                source_type: sourceType,
                default_cte_type: defaultCteType,
                field_mapping: fieldMapping,
                status: 'active',
                confidence: 0.82,
                notes: profileNotes.trim() || undefined,
            };
            const created = await apiClient.createIntegrationProfile(request);
            setProfiles((current) => [created, ...current]);
            setPreviewProfileId(created.profile_id);
            setProfileName('');
            setSupplierName('');
            setProfileNotes('');
        } catch {
            setProfileError('Unable to save the integration profile. Check workspace access and try again.');
        } finally {
            setSavingProfile(false);
        }
    };

    const handlePreviewProfile = async () => {
        if (!previewProfileId || previewing) return;

        setPreviewing(true);
        setPreviewError(null);
        setPreviewResult(null);
        try {
            const parsed = JSON.parse(previewEventText) as unknown;
            const events = Array.isArray(parsed) ? parsed : [parsed];
            const normalizedEvents = events.filter((event): event is Record<string, unknown> => (
                Boolean(event) && typeof event === 'object' && !Array.isArray(event)
            ));
            if (normalizedEvents.length === 0) {
                throw new Error('No sample events');
            }
            const result = await apiClient.previewIntegrationProfile(previewProfileId, normalizedEvents);
            setPreviewResult(result);
        } catch {
            setPreviewError('Preview needs valid JSON: either one event object or an array of event objects.');
        } finally {
            setPreviewing(false);
        }
    };

    const registryColumns: DataTableColumn<CapabilityRegistryEntry>[] = [
        {
            key: 'name',
            header: 'Connector',
            width: '22rem',
            cell: (item) => (
                <div className="min-w-0">
                    <span className="font-medium text-re-text-primary">{item.name}</span>
                    <p className="mt-0.5 text-small text-re-text-tertiary">{item.customer_copy}</p>
                </div>
            ),
        },
        {
            key: 'status',
            header: 'Status',
            width: '11rem',
            cell: (item) => (
                <Badge tone={STATUS_TONES[item.status]} size="sm">
                    {STATUS_LABELS[item.status]}
                </Badge>
            ),
        },
        {
            key: 'delivery_mode',
            header: 'Delivery',
            width: '11rem',
            cell: (item) => (
                <Badge tone="neutral" size="sm">{DELIVERY_MODE_LABELS[item.delivery_mode]}</Badge>
            ),
        },
        {
            key: 'integration_type',
            header: 'Integration type',
            cell: (item) => (
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-re-text-secondary">{INTEGRATION_TYPE_LABELS[item.integration_type]}</span>
                    {item.evidence_url && (
                        <Link
                            href={item.evidence_url}
                            className="inline-flex items-center gap-1 text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand"
                        >
                            Evidence
                            <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                        </Link>
                    )}
                </div>
            ),
        },
    ];

    return (
        <PageContainer>
            <PageHeader
                title="Integrations"
                description="Track connector readiness, Inflow Lab validation, and mapping exceptions before upstream data is treated as compliance-ready."
                secondaryActions={
                    <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
                        <RefreshCcw className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        Refresh
                    </Button>
                }
            />

            <div className="space-y-6">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <StatTile label="Registry entries" value={capabilityCount}>
                        <p className="text-small text-re-text-tertiary">
                            Customer-visible connectors and export surfaces.
                        </p>
                    </StatTile>
                    <StatTile label="Registry items marked implemented" value={liveApiCount}>
                        <p className="text-small text-re-text-tertiary">
                            Status-model entries currently marked usable in supported workspaces.
                        </p>
                    </StatTile>
                    <StatTile
                        label="Open review items"
                        value={reviewCount}
                        empty={status === 'loading'}
                        emptyCaption={status === 'loading' ? 'Checking the review queue.' : undefined}
                    >
                        <p className="text-small text-re-text-tertiary">
                            Mapping exceptions blocking automated publication.
                        </p>
                    </StatTile>
                </div>

                {/* Data inflow entry points */}
                <Card>
                    <CardHeader className="flex-col items-start gap-1">
                        <h2 className="text-subheading text-re-text-primary">Data inflow entry points</h2>
                        <p className="text-small text-re-text-tertiary">
                            Pick the route by intent so simulated connector traffic stays separate from customer imports and FDA export work.
                        </p>
                    </CardHeader>
                    <CardContent className="p-0">
                        <ul className="divide-y divide-re-border-subtle">
                            {filterExperimentalLinks(ROUTE_GUIDANCE).map((route) => (
                                <li key={route.href}>
                                    <Link
                                        href={route.href}
                                        className="flex items-start gap-3 px-5 py-4 no-underline transition-colors duration-120 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                                    >
                                        <route.icon
                                            className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                        <div className="min-w-0 flex-1">
                                            <p className="text-ui font-medium text-re-text-primary">{route.title}</p>
                                            <p className="mt-0.5 text-small text-re-text-tertiary">{route.description}</p>
                                        </div>
                                        <ArrowRight
                                            className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    </CardContent>
                </Card>

                {/* Saved supplier integration profiles */}
                <Card>
                    <CardHeader className="flex-col items-start gap-1">
                        <h2 className="text-subheading text-re-text-primary">Saved supplier integration profiles</h2>
                        <p className="text-small text-re-text-tertiary">
                            Preserve supplier-specific field mappings once, attach them to portal links, and preview messy source rows before they become evidence candidates.
                        </p>
                    </CardHeader>
                    <CardContent className="space-y-5">
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <StatTile
                                label="Saved profiles"
                                value={profiles.length}
                                loading={profilesStatus === 'loading'}
                            >
                                <p className="text-small text-re-text-tertiary">
                                    Reusable mappings for CSV, spreadsheet, API, EDI-style, and supplier portal feeds.
                                </p>
                            </StatTile>
                            <StatTile
                                label="Active profiles"
                                value={activeProfileCount}
                                loading={profilesStatus === 'loading'}
                            >
                                <p className="text-small text-re-text-tertiary">
                                    Eligible to attach to supplier self-service portal links.
                                </p>
                            </StatTile>
                        </div>

                        {!isAuthenticated && (
                            <Callout tone="warning">
                                Sign in to create workspace-scoped supplier profiles and attach them to portal invites.
                            </Callout>
                        )}
                        {profileError && (
                            <Callout tone="danger" role="alert">{profileError}</Callout>
                        )}

                        <div className="grid gap-6 lg:grid-cols-2">
                            {/* Builder */}
                            <section className="space-y-4">
                                <div>
                                    <h3 className="text-subheading text-re-text-primary">Create a mapping profile</h3>
                                    <p className="mt-1 text-small text-re-text-tertiary">
                                        Start with a supplier’s real column names, then reuse the mapping on every replay and portal submission.
                                    </p>
                                </div>

                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <Field label="Profile name" htmlFor="integration-profile-name">
                                        <Input
                                            value={profileName}
                                            onChange={(event) => setProfileName(event.target.value)}
                                            placeholder="FreshPack shipping CSV"
                                        />
                                    </Field>
                                    <Field label="Supplier/source" htmlFor="integration-supplier-name">
                                        <Input
                                            value={supplierName}
                                            onChange={(event) => setSupplierName(event.target.value)}
                                            placeholder="Supplier name"
                                        />
                                    </Field>
                                    <Field label="Source type" htmlFor="integration-source-type">
                                        <select
                                            value={sourceType}
                                            onChange={(event) => setSourceType(event.target.value as IntegrationProfileSourceType)}
                                            className={fieldControlClasses}
                                        >
                                            <option value="csv">CSV</option>
                                            <option value="spreadsheet">Spreadsheet</option>
                                            <option value="edi">EDI-style</option>
                                            <option value="epcis">EPCIS</option>
                                            <option value="api">API</option>
                                            <option value="webhook">Webhook</option>
                                            <option value="supplier_portal">Supplier portal</option>
                                        </select>
                                    </Field>
                                    <Field label="Default CTE" htmlFor="integration-default-cte">
                                        <select
                                            value={defaultCteType}
                                            onChange={(event) => setDefaultCteType(event.target.value)}
                                            className={fieldControlClasses}
                                        >
                                            <option value="shipping">Shipping</option>
                                            <option value="receiving">Receiving</option>
                                            <option value="transformation">Transformation</option>
                                            <option value="packing">Packing</option>
                                            <option value="cooling">Cooling</option>
                                            <option value="harvesting">Harvesting</option>
                                        </select>
                                    </Field>
                                </div>

                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    {PROFILE_FIELDS.map(([key, label]) => (
                                        <Field key={key} label={label} htmlFor={`integration-mapping-${key}`}>
                                            <Input
                                                mono
                                                value={fieldMapping[key] ?? ''}
                                                onChange={(event) => handleMappingChange(key, event.target.value)}
                                                placeholder="supplier_column"
                                            />
                                        </Field>
                                    ))}
                                </div>

                                <Field label="Notes" htmlFor="integration-profile-notes">
                                    <Textarea
                                        value={profileNotes}
                                        onChange={(event) => setProfileNotes(event.target.value)}
                                        rows={3}
                                    />
                                </Field>

                                <Button
                                    onClick={handleCreateProfile}
                                    disabled={!isAuthenticated || !tenantId || savingProfile || !profileName.trim()}
                                >
                                    <Save className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                    {savingProfile ? 'Saving...' : 'Save profile'}
                                </Button>
                            </section>

                            {/* Workspace profiles + preview */}
                            <section className="space-y-4">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                        <h3 className="text-subheading text-re-text-primary">Workspace profiles</h3>
                                        <p className="mt-1 text-small text-re-text-tertiary">
                                            Attach one when you invite a supplier from Supplier Management.
                                        </p>
                                    </div>
                                    <Badge tone="neutral" size="sm">
                                        <ShieldCheck className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        Workspace-scoped
                                    </Badge>
                                </div>

                                <div className="space-y-2">
                                    {profiles.map((profile) => {
                                        const selected = previewProfileId === profile.profile_id;
                                        return (
                                            <button
                                                key={profile.profile_id}
                                                type="button"
                                                aria-pressed={selected}
                                                className={cn(
                                                    'block w-full rounded-lg border p-4 text-left transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none',
                                                    selected
                                                        ? 'border-re-border-strong bg-re-surface-inset'
                                                        : 'border-re-border bg-re-surface-card hover:border-re-border-strong'
                                                )}
                                                onClick={() => setPreviewProfileId(profile.profile_id)}
                                            >
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <div className="text-ui font-medium text-re-text-primary">
                                                            {profile.display_name}
                                                        </div>
                                                        <div className="mt-0.5 text-small text-re-text-tertiary">
                                                            {profile.source_type.replace('_', ' ')} · {profile.default_cte_type} · {Math.round(profile.confidence * 100)}%
                                                        </div>
                                                    </div>
                                                    <Badge tone="neutral" size="sm">{profile.status}</Badge>
                                                </div>
                                                {profile.supplier_name && (
                                                    <p className="mt-2 text-small text-re-text-tertiary">{profile.supplier_name}</p>
                                                )}
                                                <div className="mt-2 flex flex-wrap gap-1.5">
                                                    {Object.entries(profile.field_mapping).slice(0, 4).map(([target, source]) => (
                                                        <Badge key={target} tone="neutral" size="sm" mono>
                                                            {source}{' -> '}{target}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </button>
                                        );
                                    })}
                                    {profilesStatus === 'loading' && (
                                        <EmptyState size="sm" title="Loading saved profiles..." />
                                    )}
                                    {profilesStatus === 'idle' && profiles.length === 0 && (
                                        <EmptyState
                                            size="sm"
                                            title="No profiles yet."
                                            description="Save a supplier mapping to make future portal invites faster."
                                        />
                                    )}
                                </div>

                                <div className="space-y-3 border-t border-re-border-subtle pt-4">
                                    <div className="flex items-center gap-2">
                                        <Braces className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <h3 className="text-subheading text-re-text-primary">Validate-only preview</h3>
                                    </div>
                                    <label htmlFor="integration-preview-events" className="sr-only">
                                        Sample events JSON
                                    </label>
                                    <Textarea
                                        id="integration-preview-events"
                                        value={previewEventText}
                                        onChange={(event) => setPreviewEventText(event.target.value)}
                                        rows={9}
                                        className="font-mono text-[0.8125rem]"
                                    />
                                    <Button
                                        variant="secondary"
                                        onClick={handlePreviewProfile}
                                        disabled={!previewProfileId || previewing}
                                    >
                                        <Play className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                        {previewing ? 'Previewing...' : 'Preview mapping'}
                                    </Button>
                                    {previewError && (
                                        <Callout tone="danger" role="alert">{previewError}</Callout>
                                    )}
                                    {previewResult && (
                                        <Card variant="inset" padding="compact">
                                            <div className="flex flex-wrap items-center justify-between gap-2 text-small text-re-text-secondary">
                                                <span>{previewResult.mapped} event{previewResult.mapped === 1 ? '' : 's'} mapped</span>
                                                <span>{Object.keys(previewResult.missing_fields).length} with missing fields</span>
                                            </div>
                                            <pre className="mt-3 overflow-x-auto rounded-md bg-re-surface-card p-3 font-mono text-[0.8125rem] leading-5 text-re-text-secondary">
                                                {JSON.stringify(previewResult.events[0] ?? {}, null, 2)}
                                            </pre>
                                        </Card>
                                    )}
                                </div>
                            </section>
                        </div>
                    </CardContent>
                </Card>

                {/* Inflow Lab connector */}
                {INFLOW_CONNECTOR && (
                    <Card>
                        <CardHeader className="flex-col items-start gap-1">
                            <h2 className="text-subheading text-re-text-primary">Inflow Lab</h2>
                            <p className="text-small text-re-text-tertiary">RegEngine-owned simulator connector</p>
                        </CardHeader>
                        <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
                            <div className="space-y-4">
                                <p className="max-w-[68ch] text-ui text-re-text-secondary">
                                    {INFLOW_CONNECTOR.customer_copy} Use Inflow Lab for simulated FSMA event batches and webhook validation. Use Import Data for customer documents or files, then Curation Queue and FDA Export when records are ready. Inbound events use the public slug <code className="font-mono text-[0.8125rem]">inflow-lab</code>, then resolve to canonical backend id <code className="font-mono text-[0.8125rem]">inflow_lab</code>.
                                </p>

                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                    {INFLOW_FACTS.map(([label, value]) => (
                                        <Card key={label} variant="inset" padding="compact">
                                            <div className="text-label text-re-text-muted">{label}</div>
                                            <div className="mt-1 font-mono text-[0.8125rem] text-re-text-primary">{value}</div>
                                        </Card>
                                    ))}
                                </div>

                                <div className="flex flex-wrap gap-2">
                                    {experimentalFeaturesEnabled() && (
                                        <Button asChild>
                                            <Link href="/dashboard/inflow-lab">
                                                <FlaskConical className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                Open Inflow Lab
                                            </Link>
                                        </Button>
                                    )}
                                    <Button variant="secondary" asChild>
                                        <Link href="/docs/connectors/inflow-lab">
                                            <Terminal className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                            Connector docs
                                        </Link>
                                    </Button>
                                    <Button variant="ghost" asChild>
                                        <Link href="/integrations">
                                            Public registry
                                            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                        </Link>
                                    </Button>
                                </div>
                            </div>

                            <div className="space-y-3">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                        <h3 className="text-subheading text-re-text-primary">Reference path</h3>
                                        <p className="mt-1 text-small text-re-text-tertiary">
                                            Used for simulator replay and implementation validation workflows.
                                        </p>
                                    </div>
                                    <Badge tone="neutral" size="sm">
                                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        Documented
                                    </Badge>
                                </div>
                                <ol className="divide-y divide-re-border-subtle rounded-lg border border-re-border-subtle bg-re-surface-inset">
                                    {INFLOW_PATH.map(([label, detail], index) => (
                                        <li key={label} className="flex items-start gap-3 px-4 py-3">
                                            <span className="font-mono text-label text-re-text-muted">
                                                {String(index + 1).padStart(2, '0')}
                                            </span>
                                            <div className="min-w-0">
                                                <div className="text-ui font-medium text-re-text-primary">{label}</div>
                                                <div className="mt-0.5 font-mono text-[0.8125rem] text-re-text-tertiary">{detail}</div>
                                            </div>
                                        </li>
                                    ))}
                                </ol>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Capability registry */}
                <Card>
                    <CardHeader className="flex-col items-start gap-1">
                        <h2 className="text-subheading text-re-text-primary">Capability Registry</h2>
                        <p className="text-small text-re-text-tertiary">
                            Public integration claims are rendered from this status model instead of hardcoded live badges.
                        </p>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        {CATEGORY_LABELS.map((category) => (
                            <section key={category.id} className="space-y-3">
                                <h3 className="text-subheading text-re-text-primary">{category.title}</h3>
                                <DataTable
                                    caption={`${category.title} connectors and their delivery status`}
                                    columns={registryColumns}
                                    data={getCapabilitiesByCategory(category.id)}
                                    rowKey={(item) => item.id}
                                    minWidth="760px"
                                    stickyFirstColumn
                                    empty={{ title: 'No connectors in this category yet', size: 'sm' }}
                                />
                            </section>
                        ))}
                    </CardContent>
                </Card>

                {/* Reconciliation & exception queue */}
                <Card>
                    <CardHeader className="flex-col items-start gap-1">
                        <h2 className="text-subheading text-re-text-primary">Reconciliation &amp; Exception Queue</h2>
                        <p className="text-small text-re-text-tertiary">
                            Missing required KDEs, unmapped fields, and identity conflicts are surfaced here from the current review-queue contract.
                        </p>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {notConnected && (
                            <Callout tone="warning">
                                {meta?.message ?? 'Field mapping review is not yet configured for this account.'}
                            </Callout>
                        )}

                        {items.length > 0 && (
                            <ul className="divide-y divide-re-border-subtle rounded-lg border border-re-border">
                                {items.map((item) => (
                                    <li key={item.id} className="flex items-start justify-between gap-3 px-4 py-3">
                                        <div className="min-w-0">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <span className="text-ui font-medium text-re-text-primary">{item.source}</span>
                                                <Badge tone="neutral" size="sm">{item.status.replaceAll('_', ' ')}</Badge>
                                            </div>
                                            <div className="mt-1 font-mono text-[0.8125rem] text-re-text-secondary">
                                                <strong className="font-medium">{item.sourceField}</strong>
                                                {' -> '}
                                                <span>{item.mappedField ?? 'Unmapped'}</span>
                                            </div>
                                            <p className="mt-1 text-small text-re-text-tertiary">{item.detail}</p>
                                        </div>
                                        <ShieldCheck
                                            className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                    </li>
                                ))}
                            </ul>
                        )}

                        {status === 'loading' && items.length === 0 && (
                            <EmptyState size="sm" title="Loading review-queue preview data..." />
                        )}
                        {status === 'idle' && !notConnected && items.length === 0 && (
                            <EmptyState size="sm" title="No mapping exceptions are currently queued." />
                        )}
                        {status === 'error' && (
                            <Callout tone="danger" role="alert">
                                Mapping review is temporarily unavailable. Connector statuses above are still current.
                            </Callout>
                        )}

                        <Callout tone="warning" icon={AlertTriangle}>
                            Required KDE gaps block automated publication into recall-ready exports until they are resolved.
                        </Callout>
                        <Callout tone="info" icon={GitBranch}>
                            Inflow Lab traffic is intentionally tagged by source so simulator events can be separated from generic webhook submissions during demos and CI replay.
                        </Callout>
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    );
}
