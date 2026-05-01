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
    Link2,
    Play,
    RefreshCcw,
    Save,
    ShieldCheck,
    SlidersHorizontal,
    Terminal,
} from 'lucide-react';
import {
    CAPABILITY_REGISTRY,
    DELIVERY_MODE_LABELS,
    INTEGRATION_TYPE_LABELS,
    type MappingReviewItem,
    STATUS_LABELS,
    getCapabilitiesByCategory,
} from '@/lib/customer-readiness';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import type {
    CreateIntegrationProfileRequest,
    IntegrationProfile,
    IntegrationProfileSourceType,
    MappingPreviewResponse,
} from '@/types/api';
import styles from './page.module.css';

const CATEGORY_LABELS = [
    { id: 'food_safety_iot' as const, title: 'Food safety & IoT' },
    { id: 'erp_warehouse' as const, title: 'ERP & warehouse' },
    { id: 'retailer_network' as const, title: 'Retailer exports' },
    { id: 'developer_api' as const, title: 'Developer APIs' },
];

const INFLOW_CONNECTOR = CAPABILITY_REGISTRY.find((item) => item.id === 'inflow-lab');

const INFLOW_FACTS = [
    ['Public slug', 'inflow-lab'],
    ['Backend id', 'inflow_lab'],
    ['Repository', 'regengine/inflow-lab'],
    ['Contract CI', 'Live ingest replay'],
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
        let cancelled = false;

        async function loadItems() {
            setStatus('loading');

            try {
                const response = await fetch('/api/fsma/customer-readiness/mappings');
                if (!response.ok) {
                    throw new Error('Failed to load mappings');
                }

                const data = (await response.json()) as MappingReviewResponse;
                if (!cancelled) {
                    setItems(data.items ?? []);
                    setMeta(data.meta);
                    setStatus('idle');
                }
            } catch {
                if (!cancelled) {
                    setStatus('error');
                }
            }
        }

        void loadItems();

        return () => {
            cancelled = true;
        };
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
                    setProfileError('Unable to load saved integration profiles for this tenant.');
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
    const liveApiCount = CAPABILITY_REGISTRY.filter((item) => item.status === 'ga').length;
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
            setProfileError('Unable to save the integration profile. Check tenant access and try again.');
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

    return (
        <div className={styles.page}>
            <div className={styles.shell}>
                <div className={styles.header}>
                    <div>
                        <h1 className={styles.title}>
                            <Link2 className={styles.titleIcon} />
                            Integrations
                        </h1>
                        <p className={styles.lede}>
                            Track connector readiness, Inflow Lab validation, and mapping exceptions before upstream data is treated as compliance-ready.
                        </p>
                    </div>
                    <Button
                        variant="outline"
                        className={styles.refreshButton}
                        onClick={() => window.location.reload()}
                    >
                        <RefreshCcw className={styles.buttonIcon} />
                        Refresh
                    </Button>
                </div>

                <div className={styles.statsGrid}>
                    <div className={styles.statCard}>
                        <div className={styles.statLabel}>Registry entries</div>
                        <div className={styles.statValue}>{capabilityCount}</div>
                        <p className={styles.statCopy}>Customer-visible connectors and export surfaces.</p>
                    </div>
                    <div className={styles.statCard}>
                        <div className={styles.statLabel}>GA API surfaces</div>
                        <div className={styles.statValue}>{liveApiCount}</div>
                        <p className={styles.statCopy}>Current production-ready API and import claims.</p>
                    </div>
                    <div className={styles.statCard}>
                        <div className={styles.statLabel}>Open review items</div>
                        <div className={styles.statValue}>{status === 'loading' ? '-' : reviewCount}</div>
                        <p className={styles.statCopy}>Mapping exceptions blocking automated publication.</p>
                    </div>
                </div>

                <section className={styles.card}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>Data inflow entry points</h2>
                        <p className={styles.cardDescription}>
                            Pick the route by intent so simulated connector traffic stays separate from customer imports and FDA export work.
                        </p>
                    </div>
                    <div className={styles.cardContent}>
                        <div className={styles.factGrid}>
                            {ROUTE_GUIDANCE.map((route) => (
                                <Link key={route.href} href={route.href} className={styles.factCard}>
                                    <div className={styles.connectorHeading}>
                                        <route.icon className={styles.inlineIcon} />
                                        <div className={styles.factValue}>{route.title}</div>
                                        <ArrowRight className={styles.evidenceIcon} />
                                    </div>
                                    <div>
                                        <p className={styles.registryCopy}>{route.description}</p>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>
                </section>

                <section className={styles.card}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>Saved supplier integration profiles</h2>
                        <p className={styles.cardDescription}>
                            Preserve supplier-specific field mappings once, attach them to portal links, and preview messy source rows before they become evidence candidates.
                        </p>
                    </div>
                    <div className={styles.profileContent}>
                        <div className={styles.profileSummaryGrid}>
                            <div className={styles.profileMetric}>
                                <div className={styles.statLabel}>Saved profiles</div>
                                <div className={styles.statValue}>{profilesStatus === 'loading' ? '-' : profiles.length}</div>
                                <p className={styles.statCopy}>Reusable mappings for CSV, spreadsheet, API, EDI-style, and supplier portal feeds.</p>
                            </div>
                            <div className={styles.profileMetric}>
                                <div className={styles.statLabel}>Active profiles</div>
                                <div className={styles.statValue}>{profilesStatus === 'loading' ? '-' : activeProfileCount}</div>
                                <p className={styles.statCopy}>Eligible to attach to supplier self-service portal links.</p>
                            </div>
                        </div>

                        {!isAuthenticated && (
                            <div className={styles.warningBox}>
                                Sign in to create tenant-scoped supplier profiles and attach them to portal invites.
                            </div>
                        )}
                        {profileError && <div className={styles.errorBox}>{profileError}</div>}

                        <div className={styles.profileGrid}>
                            <div className={styles.profileBuilder}>
                                <div className={styles.connectorHeading}>
                                    <div className={styles.connectorIcon}>
                                        <SlidersHorizontal className={styles.connectorSvg} />
                                    </div>
                                    <div>
                                        <h3 className={styles.sectionTitle}>Create a mapping profile</h3>
                                        <p className={styles.muted}>Start with a supplier’s real column names, then reuse the mapping on every replay and portal submission.</p>
                                    </div>
                                </div>

                                <div className={styles.profileFormGrid}>
                                    <label className={styles.formField}>
                                        <span>Profile name</span>
                                        <input
                                            value={profileName}
                                            onChange={(event) => setProfileName(event.target.value)}
                                            placeholder="FreshPack shipping CSV"
                                            className={styles.input}
                                        />
                                    </label>
                                    <label className={styles.formField}>
                                        <span>Supplier/source</span>
                                        <input
                                            value={supplierName}
                                            onChange={(event) => setSupplierName(event.target.value)}
                                            placeholder="Supplier name"
                                            className={styles.input}
                                        />
                                    </label>
                                    <label className={styles.formField}>
                                        <span>Source type</span>
                                        <select
                                            value={sourceType}
                                            onChange={(event) => setSourceType(event.target.value as IntegrationProfileSourceType)}
                                            className={styles.input}
                                        >
                                            <option value="csv">CSV</option>
                                            <option value="spreadsheet">Spreadsheet</option>
                                            <option value="edi">EDI-style</option>
                                            <option value="epcis">EPCIS</option>
                                            <option value="api">API</option>
                                            <option value="webhook">Webhook</option>
                                            <option value="supplier_portal">Supplier portal</option>
                                        </select>
                                    </label>
                                    <label className={styles.formField}>
                                        <span>Default CTE</span>
                                        <select
                                            value={defaultCteType}
                                            onChange={(event) => setDefaultCteType(event.target.value)}
                                            className={styles.input}
                                        >
                                            <option value="shipping">Shipping</option>
                                            <option value="receiving">Receiving</option>
                                            <option value="transformation">Transformation</option>
                                            <option value="packing">Packing</option>
                                            <option value="cooling">Cooling</option>
                                            <option value="harvesting">Harvesting</option>
                                        </select>
                                    </label>
                                </div>

                                <div className={styles.mappingGrid}>
                                    {PROFILE_FIELDS.map(([key, label]) => (
                                        <label key={key} className={styles.formField}>
                                            <span>{label}</span>
                                            <input
                                                value={fieldMapping[key] ?? ''}
                                                onChange={(event) => handleMappingChange(key, event.target.value)}
                                                placeholder="supplier_column"
                                                className={styles.input}
                                            />
                                        </label>
                                    ))}
                                </div>

                                <label className={styles.formField}>
                                    <span>Notes</span>
                                    <textarea
                                        value={profileNotes}
                                        onChange={(event) => setProfileNotes(event.target.value)}
                                        className={styles.textarea}
                                        rows={3}
                                    />
                                </label>

                                <Button
                                    className={styles.primaryAction}
                                    onClick={handleCreateProfile}
                                    disabled={!isAuthenticated || !tenantId || savingProfile || !profileName.trim()}
                                >
                                    <Save className={styles.buttonIcon} />
                                    {savingProfile ? 'Saving...' : 'Save profile'}
                                </Button>
                            </div>

                            <div className={styles.profileListPanel}>
                                <div className={styles.pathHeader}>
                                    <div>
                                        <h3 className={styles.pathTitle}>Tenant profiles</h3>
                                        <p className={styles.muted}>Attach one when you invite a supplier from Supplier Management.</p>
                                    </div>
                                    <span className={styles.verifiedBadge}>
                                        <ShieldCheck className={styles.badgeIcon} />
                                        Tenant-scoped
                                    </span>
                                </div>

                                <div className={styles.profileList}>
                                    {profiles.map((profile) => (
                                        <button
                                            key={profile.profile_id}
                                            type="button"
                                            className={`${styles.profileCard} ${previewProfileId === profile.profile_id ? styles.profileCardActive : ''}`}
                                            onClick={() => setPreviewProfileId(profile.profile_id)}
                                        >
                                            <div className={styles.profileCardHeader}>
                                                <div>
                                                    <div className={styles.profileName}>{profile.display_name}</div>
                                                    <div className={styles.profileMeta}>
                                                        {profile.source_type.replace('_', ' ')} · {profile.default_cte_type} · {Math.round(profile.confidence * 100)}%
                                                    </div>
                                                </div>
                                                <span className={styles.metaBadge}>{profile.status}</span>
                                            </div>
                                            {profile.supplier_name && (
                                                <p className={styles.registryCopy}>{profile.supplier_name}</p>
                                            )}
                                            <div className={styles.mappingChips}>
                                                {Object.entries(profile.field_mapping).slice(0, 4).map(([target, source]) => (
                                                    <span key={target} className={styles.mappingChip}>
                                                        {source}{' -> '}{target}
                                                    </span>
                                                ))}
                                            </div>
                                        </button>
                                    ))}
                                    {profilesStatus === 'loading' && <div className={styles.emptyBox}>Loading saved profiles...</div>}
                                    {profilesStatus === 'idle' && profiles.length === 0 && (
                                        <div className={styles.emptyBox}>
                                            No profiles yet. Save a supplier mapping to make future portal invites faster.
                                        </div>
                                    )}
                                </div>

                                <div className={styles.previewPanel}>
                                    <div className={styles.connectorHeading}>
                                        <Braces className={styles.inlineIcon} />
                                        <h3 className={styles.pathTitle}>Validate-only preview</h3>
                                    </div>
                                    <textarea
                                        value={previewEventText}
                                        onChange={(event) => setPreviewEventText(event.target.value)}
                                        className={styles.codeTextarea}
                                        rows={9}
                                    />
                                    <Button
                                        variant="outline"
                                        className={styles.secondaryAction}
                                        onClick={handlePreviewProfile}
                                        disabled={!previewProfileId || previewing}
                                    >
                                        <Play className={styles.buttonIcon} />
                                        {previewing ? 'Previewing...' : 'Preview mapping'}
                                    </Button>
                                    {previewError && <div className={styles.errorBox}>{previewError}</div>}
                                    {previewResult && (
                                        <div className={styles.previewResult}>
                                            <div className={styles.profileCardHeader}>
                                                <span>{previewResult.mapped} event{previewResult.mapped === 1 ? '' : 's'} mapped</span>
                                                <span>{Object.keys(previewResult.missing_fields).length} with missing fields</span>
                                            </div>
                                            <pre>{JSON.stringify(previewResult.events[0] ?? {}, null, 2)}</pre>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {INFLOW_CONNECTOR && (
                    <section className={styles.inflowPanel}>
                        <div className={styles.inflowGrid}>
                            <div className={styles.inflowMain}>
                                <div className={styles.connectorHeading}>
                                    <div className={styles.connectorIcon}>
                                        <FlaskConical className={styles.connectorSvg} />
                                    </div>
                                    <div>
                                        <h2 className={styles.sectionTitle}>Inflow Lab</h2>
                                        <p className={styles.muted}>RegEngine-owned simulator connector</p>
                                    </div>
                                </div>

                                <p className={styles.inflowCopy}>
                                    {INFLOW_CONNECTOR.customer_copy} Use Inflow Lab for simulated FSMA event batches and webhook validation. Use Import Data for customer documents or files, then Curation Queue and FDA Export when records are ready. Inbound events use the public slug <code>inflow-lab</code>, then resolve to canonical backend id <code>inflow_lab</code>.
                                </p>

                                <div className={styles.factGrid}>
                                    {INFLOW_FACTS.map(([label, value]) => (
                                        <div key={label} className={styles.factCard}>
                                            <div className={styles.factLabel}>{label}</div>
                                            <div className={styles.factValue}>{value}</div>
                                        </div>
                                    ))}
                                </div>

                                <div className={styles.actionRow}>
                                    <Button asChild className={styles.primaryAction}>
                                        <Link href="/dashboard/inflow-lab">
                                            <FlaskConical className={styles.buttonIcon} />
                                            Open Inflow Lab
                                        </Link>
                                    </Button>
                                    <Button asChild className={styles.primaryAction}>
                                        <Link href="/docs/connectors/inflow-lab">
                                            <Terminal className={styles.buttonIcon} />
                                            Connector docs
                                        </Link>
                                    </Button>
                                    <Button asChild variant="outline" className={styles.secondaryAction}>
                                        <Link href="/integrations">
                                            Public registry
                                            <ArrowRight className={styles.buttonIconRight} />
                                        </Link>
                                    </Button>
                                </div>
                            </div>

                            <div className={styles.pathPanel}>
                                <div className={styles.pathHeader}>
                                    <div>
                                        <h3 className={styles.pathTitle}>Live data path</h3>
                                        <p className={styles.muted}>The same path is exercised by contract CI.</p>
                                    </div>
                                    <span className={styles.verifiedBadge}>
                                        <CheckCircle2 className={styles.badgeIcon} />
                                        Verified
                                    </span>
                                </div>
                                <div className={styles.pathList}>
                                    {INFLOW_PATH.map(([label, detail], index) => (
                                        <div key={label} className={styles.pathItem}>
                                            <div className={styles.pathRail}>
                                                <div className={styles.pathNumber}>
                                                    {index + 1}
                                                </div>
                                                {index < INFLOW_PATH.length - 1 && <div className={styles.pathLine} />}
                                            </div>
                                            <div className={styles.pathText}>
                                                <div className={styles.pathItemTitle}>{label}</div>
                                                <div className={styles.pathItemDetail}>{detail}</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </section>
                )}

                <section className={styles.card}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>Capability Registry</h2>
                        <p className={styles.cardDescription}>
                            Public integration claims are rendered from this status model instead of hardcoded live badges.
                        </p>
                    </div>
                    <div className={styles.cardContent}>
                        {CATEGORY_LABELS.map((category) => (
                            <div key={category.id} className={styles.categoryBlock}>
                                <h3 className={styles.categoryTitle}>{category.title}</h3>
                                <div className={styles.registryTable}>
                                    {getCapabilitiesByCategory(category.id).map((item) => (
                                        <div
                                            key={item.id}
                                            className={`${styles.registryRow} ${item.id === 'inflow-lab' ? styles.registryRowFeatured : ''}`}
                                        >
                                            <div className={styles.registryNameCell}>
                                                <div className={styles.registryName}>
                                                    {item.id === 'inflow-lab' && <FlaskConical className={styles.inlineIcon} />}
                                                    <span>{item.name}</span>
                                                </div>
                                                <p className={styles.registryCopy}>{item.customer_copy}</p>
                                            </div>
                                            <div className={styles.badgeGroup}>
                                                <span className={styles.metaBadge}>
                                                    {STATUS_LABELS[item.status]}
                                                </span>
                                                <span className={styles.metaBadge}>
                                                    {DELIVERY_MODE_LABELS[item.delivery_mode]}
                                                </span>
                                            </div>
                                            <div className={styles.evidenceCell}>
                                                <span>{INTEGRATION_TYPE_LABELS[item.integration_type]}</span>
                                                {item.evidence_url && (
                                                    <Link href={item.evidence_url} className={styles.evidenceLink}>
                                                        Evidence
                                                        <ArrowRight className={styles.evidenceIcon} />
                                                    </Link>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                <section className={styles.card}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>Reconciliation & Exception Queue</h2>
                        <p className={styles.cardDescription}>
                            Missing required KDEs, unmapped fields, and identity conflicts are surfaced here from the current review-queue contract.
                        </p>
                    </div>
                    <div className={styles.queueContent}>
                        {notConnected && (
                            <div className={styles.warningBox}>
                                {meta?.message ?? 'Field mapping review is not yet configured for this account.'}
                            </div>
                        )}
                        {items.map((item) => (
                            <div key={item.id} className={styles.queueItem}>
                                <div className={styles.queueItemBody}>
                                    <div>
                                        <div className={styles.queueHeading}>
                                            <span className={styles.queueSource}>{item.source}</span>
                                            <span className={styles.queueStatus}>{item.status.replaceAll('_', ' ')}</span>
                                        </div>
                                        <div className={styles.mappingLine}>
                                            <strong>{item.sourceField}</strong>
                                            {' -> '}
                                            <span>{item.mappedField ?? 'Unmapped'}</span>
                                        </div>
                                        <p className={styles.queueDetail}>{item.detail}</p>
                                    </div>
                                    <ShieldCheck className={styles.queueIcon} />
                                </div>
                            </div>
                        ))}
                        {status === 'loading' && items.length === 0 && (
                            <div className={styles.emptyBox}>
                                Loading review-queue preview data...
                            </div>
                        )}
                        {status === 'idle' && !notConnected && items.length === 0 && (
                            <div className={styles.emptyBox}>
                                No mapping exceptions are currently queued.
                            </div>
                        )}
                        {status === 'error' && (
                            <div className={styles.errorBox}>
                                The mapping review contract route did not respond. Public status copy still renders from the shared registry above.
                            </div>
                        )}
                        <div className={styles.infoBox}>
                            <AlertTriangle className={styles.infoIconWarning} />
                            Required KDE gaps block automated publication into recall-ready exports until they are resolved.
                        </div>
                        <div className={styles.infoBox}>
                            <GitBranch className={styles.infoIconBrand} />
                            Inflow Lab traffic is intentionally tagged by source so simulator events can be separated from generic webhook submissions during demos and CI replay.
                        </div>
                    </div>
                </section>
            </div>
        </div>
    );
}
