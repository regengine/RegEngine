'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
    AlertTriangle,
    ArrowRight,
    CheckCircle2,
    FlaskConical,
    GitBranch,
    Link2,
    RefreshCcw,
    ShieldCheck,
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

type MappingReviewResponse = {
    items?: MappingReviewItem[];
    meta?: {
        status?: string;
        message?: string;
    };
};

export default function DashboardIntegrationsPage() {
    const [items, setItems] = useState<MappingReviewItem[]>([]);
    const [meta, setMeta] = useState<MappingReviewResponse['meta']>();
    const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');

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

    const notConnected = meta?.status === 'not_connected';
    const reviewCount = items.filter((item) => item.status !== 'mapped').length;
    const capabilityCount = CAPABILITY_REGISTRY.filter((item) => item.category !== 'commercial').length;
    const liveApiCount = CAPABILITY_REGISTRY.filter((item) => item.status === 'ga').length;

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
                                    {INFLOW_CONNECTOR.customer_copy} Inbound events use the public slug <code>inflow-lab</code>, then resolve to canonical backend id <code>inflow_lab</code>.
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
