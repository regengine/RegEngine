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
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-6xl mx-auto space-y-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <Link2 className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Integrations & Mapping Review
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            Track delivery mode, customer-visible status, and unresolved mapping or identity issues before data is treated as compliance-ready.
                        </p>
                    </div>
                    <Button
                        variant="outline"
                        className="rounded-xl min-h-[44px] w-full sm:w-auto active:scale-[0.97]"
                        onClick={() => window.location.reload()}
                    >
                        <RefreshCcw className="h-4 w-4 mr-1" />
                        Refresh review queue
                    </Button>
                </div>

                <div className="rounded-xl border border-re-info/20 bg-re-info-muted0/[0.04] p-4 text-sm text-muted-foreground">
                    Alpha release — Browse available integrations and queue connection requests. Live data sync activates during onboarding.
                </div>

                <div className="grid gap-3 sm:gap-4 grid-cols-1 lg:grid-cols-[1.2fr_0.8fr]">
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
                                            <div key={item.id} className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-3 min-h-[48px]">
                                                <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                                                    <span className="text-xs sm:text-sm font-medium">{item.name}</span>
                                                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{STATUS_LABELS[item.status]}</span>
                                                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground hidden sm:inline">{DELIVERY_MODE_LABELS[item.delivery_mode]}</span>
                                                </div>
                                                <p className="text-xs sm:text-sm text-muted-foreground mt-1.5 sm:mt-2">{item.customer_copy}</p>
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
                            <div className="rounded-xl border border-re-warning/20 bg-re-warning-muted0/10 p-3 text-re-warning">
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
                            <div key={item.id} className="rounded-xl border border-[var(--re-border-default)] p-3 sm:p-4">
                                <div className="flex flex-wrap items-center gap-2">
                                    <span className="text-xs sm:text-sm font-semibold">{item.source}</span>
                                    <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{item.status.replaceAll('_', ' ')}</span>
                                </div>
                                <div className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-muted-foreground break-all">
                                    <strong className="text-foreground">{item.sourceField}</strong>
                                    {' → '}
                                    <span>{item.mappedField ?? 'Unmapped'}</span>
                                </div>
                                <p className="text-xs sm:text-sm text-muted-foreground mt-1.5 sm:mt-2">{item.detail}</p>
                            </div>
                        ))}
                        {status === 'loading' && items.length === 0 && (
                            <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                                Loading review-queue preview data...
                            </div>
                        )}
                        {status === 'error' && (
                            <div className="rounded-xl border border-re-danger/20 bg-re-danger-muted0/10 p-4 text-sm text-re-danger">
                                The mapping review contract route did not respond. Public status copy still renders from the shared registry above.
                            </div>
                        )}
                        <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4 text-sm text-muted-foreground">
                            <AlertTriangle className="h-4 w-4 inline mr-2 text-re-warning" />
                            Required KDE gaps block automated publication into recall-ready exports until they are resolved.
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
