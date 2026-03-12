'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, Link2, RefreshCcw } from 'lucide-react';
import {
    DELIVERY_MODE_LABELS,
    type MappingReviewItem,
    STATUS_LABELS,
    getCapabilitiesByCategory,
} from '@/lib/customer-readiness';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const CATEGORY_LABELS = [
    { id: 'food_safety_iot' as const, title: 'Food safety & IoT' },
    { id: 'erp_warehouse' as const, title: 'ERP & warehouse' },
    { id: 'retailer_network' as const, title: 'Retailer exports' },
    { id: 'developer_api' as const, title: 'Developer APIs' },
];

export default function DashboardIntegrationsPage() {
    const [items, setItems] = useState<MappingReviewItem[]>([]);
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

                const data = (await response.json()) as { items: MappingReviewItem[] };
                if (!cancelled) {
                    setItems(data.items);
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

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-6xl mx-auto space-y-6">
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Link2 className="h-6 w-6 text-[var(--re-brand)]" />
                            Integrations & Mapping Review
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Track delivery mode, customer-visible status, and unresolved mapping or identity issues before data is treated as compliance-ready.
                        </p>
                    </div>
                    <Button
                        variant="outline"
                        className="rounded-xl"
                        onClick={() => window.location.reload()}
                    >
                        <RefreshCcw className="h-4 w-4 mr-1" />
                        Refresh review queue
                    </Button>
                </div>

                <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                    Preview interface: capability metadata is shared across the public site, while the review queue below is loaded from the current frontend contract route rather than a persistent backend reconciliation service.
                </div>

                <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                    <Card>
                        <CardHeader>
                            <CardTitle>Customer-visible capability registry</CardTitle>
                            <CardDescription>
                                Public integration claims are rendered from this status model instead of hardcoded “Live” badges.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-5">
                            {CATEGORY_LABELS.map((category) => (
                                <div key={category.id}>
                                    <h2 className="text-sm font-semibold mb-2">{category.title}</h2>
                                    <div className="space-y-2">
                                        {getCapabilitiesByCategory(category.id).map((item) => (
                                            <div key={item.id} className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-3">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-sm font-medium">{item.name}</span>
                                                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{STATUS_LABELS[item.status]}</span>
                                                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{DELIVERY_MODE_LABELS[item.delivery_mode]}</span>
                                                </div>
                                                <p className="text-sm text-muted-foreground mt-2">{item.customer_copy}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>How the review queue works</CardTitle>
                            <CardDescription>
                                Mapping and reconciliation are explicit. RegEngine does not assume upstream exports are already clean FSMA records.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm text-muted-foreground">
                            <p>1. Upload or connect a source export.</p>
                            <p>2. Map source fields to FSMA CTE and KDE targets.</p>
                            <p>3. Resolve missing KDEs, identity conflicts, and ambiguous facility matches.</p>
                            <p>4. Publish only after exceptions are reviewed.</p>
                            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-amber-200">
                                Cryptographic hashing verifies the exported record after normalization. It does not prove the upstream source data was correct.
                            </div>
                        </CardContent>
                    </Card>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Reconciliation & exception queue</CardTitle>
                        <CardDescription>
                            Missing required KDEs, unmapped fields, and identity conflicts are surfaced here from the current review-queue contract.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {items.map((item) => (
                            <div key={item.id} className="rounded-xl border border-[var(--re-border-default)] p-4">
                                <div className="flex flex-wrap items-center gap-2">
                                    <span className="text-sm font-semibold">{item.source}</span>
                                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{item.status.replaceAll('_', ' ')}</span>
                                </div>
                                <div className="mt-2 text-sm text-muted-foreground">
                                    <strong className="text-foreground">{item.sourceField}</strong>
                                    {' → '}
                                    <span>{item.mappedField ?? 'Unmapped'}</span>
                                </div>
                                <p className="text-sm text-muted-foreground mt-2">{item.detail}</p>
                            </div>
                        ))}
                        {status === 'loading' && items.length === 0 && (
                            <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                                Loading review-queue preview data...
                            </div>
                        )}
                        {status === 'error' && (
                            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-200">
                                The mapping review contract route did not respond. Public status copy still renders from the shared registry above.
                            </div>
                        )}
                        <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                            <AlertTriangle className="h-4 w-4 inline mr-2 text-amber-500" />
                            Required KDE gaps block automated publication into recall-ready exports until they are resolved.
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
