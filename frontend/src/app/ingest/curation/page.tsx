'use client';

import { useCallback, useRef, useState, useEffect } from 'react';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import {
    ShieldCheck,
    Search,
    Trash2,
    CheckCircle,
    AlertTriangle,
    ExternalLink,
    RefreshCw
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';

interface DiscoveryItem {
    body: string;
    url: string;
    index: number;
}

/**
 * The three queue facts. `StatTile` is the system's tile, but this page's unit
 * test (src/__tests__/pages/curation.test.tsx) mocks `lucide-react` with a
 * nine-icon factory, and vitest throws on any other icon access at import time
 * — which rules out StatTile, DataTable, StatusBadge, Callout and Checkbox
 * here. These follow StatTile's recipe: mono label, tabular value, no colour.
 */
const QUEUE_STATS = (pending: number, domains: number) => [
    { label: 'Pending Review', value: pending },
    { label: 'Unique Source Domains', value: domains },
    { label: 'FDA Sources', value: 'FSMA' },
];

const GUIDELINES = [
    'Verify the link leads to an official regulatory document or landing page before approval.',
    'If the link is a direct download (PDF/DOCX), our parser will prioritize high-fidelity extraction.',
    'Approval bypasses robots.txt checks. Only approve if the source is legally scrapable or manually provided.',
];

export default function CurationDashboard() {
    if (!experimentalFeaturesEnabled()) {
        return (
            <FeatureNotEnabled
                featureName="Curation queue"
                backHref="/ingest"
                backLabel="Back to ingestion"
            />
        );
    }
    return <CurationDashboardContent />;
}

function CurationDashboardContent() {
    const { isAuthenticated, isHydrated } = useAuth();
    const [items, setItems] = useState<DiscoveryItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [processing, setProcessing] = useState<number | null>(null);
    const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
    const { toast } = useToast();
    const toastRef = useRef(toast);

    useEffect(() => {
        toastRef.current = toast;
    }, [toast]);

    const fetchQueue = useCallback(async () => {
        try {
            setLoading(true);
            const data = await apiClient.getDiscoveryQueue();
            setItems(data);
            setLoadError(null);
            setSelectedIndices(new Set()); // Clear selection on refresh
        } catch (error) {
            console.error('Failed to fetch discovery queue:', error);
            setLoadError('Could not connect to the ingestion service. Please ensure the backend is running.');
            toastRef.current({
                title: 'Offline Error',
                description: 'Could not connect to the ingestion service. Please ensure the backend is running.',
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!isHydrated) return;
        if (!isAuthenticated) {
            setLoading(false);
            return;
        }
        fetchQueue();
    }, [fetchQueue, isAuthenticated, isHydrated]);

    const toggleSelect = (index: number) => {
        const next = new Set(selectedIndices);
        if (next.has(index)) {
            next.delete(index);
        } else {
            next.add(index);
        }
        setSelectedIndices(next);
    };

    const toggleSelectAll = () => {
        if (selectedIndices.size === items.length) {
            setSelectedIndices(new Set());
        } else {
            setSelectedIndices(new Set(items.map(i => i.index)));
        }
    };

    const handleBulkApprove = async () => {
        if (selectedIndices.size === 0) return;
        try {
            setLoading(true);
            const indices = Array.from(selectedIndices);
            await apiClient.bulkApproveDiscovery(indices);
            toast({
                title: 'Success',
                description: `Successfully approved and triggered scrape for ${indices.length} items.`,
            });
            fetchQueue();
        } catch (error) {
            toast({
                title: 'Bulk Action Failed',
                description: 'Failed to approve multiple items.',
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    };

    const handleBulkReject = async () => {
        if (selectedIndices.size === 0) return;
        try {
            setLoading(true);
            const indices = Array.from(selectedIndices);
            await apiClient.bulkRejectDiscovery(indices);
            toast({
                title: 'Success',
                description: `Successfully rejected ${indices.length} items.`,
            });
            fetchQueue();
        } catch (error) {
            toast({
                title: 'Bulk Action Failed',
                description: 'Failed to reject multiple items.',
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (index: number) => {
        try {
            setProcessing(index);
            await apiClient.approveDiscovery(index);
            toast({
                title: 'Success',
                description: 'Discovery approved and scrape triggered',
            });
            fetchQueue();
        } catch (error) {
            console.error('Approval failed:', error);
            toast({
                title: 'Error',
                description: 'Failed to approve discovery',
                variant: 'destructive',
            });
        } finally {
            setProcessing(null);
        }
    };

    const handleReject = async (index: number) => {
        try {
            setProcessing(index);
            await apiClient.rejectDiscovery(index);
            toast({
                title: 'Success',
                description: 'Discovery rejected',
            });
            fetchQueue();
        } catch (error) {
            console.error('Rejection failed:', error);
            toast({
                title: 'Error',
                description: 'Failed to reject discovery',
                variant: 'destructive',
            });
        } finally {
            setProcessing(null);
        }
    };

    if (!isHydrated) {
        return (
            <PageContainer>
                <div className="space-y-6" aria-busy="true">
                    <div className="space-y-3 border-b border-re-border-subtle pb-5">
                        <Skeleton className="h-8 w-72" />
                        <Skeleton className="h-4 w-full max-w-[42rem]" />
                    </div>
                    <p className="text-ui text-re-text-tertiary">Loading session...</p>
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                        <Skeleton className="h-24 w-full" />
                        <Skeleton className="h-24 w-full" />
                        <Skeleton className="h-24 w-full" />
                    </div>
                    <Skeleton className="h-64 w-full" />
                </div>
            </PageContainer>
        );
    }

    if (!isAuthenticated) {
        return (
            <PageContainer>
                <EmptyState
                    icon={ShieldCheck}
                    title="Authentication Required"
                    description="You must be signed in to access the curation dashboard."
                    action={
                        <Button asChild>
                            <a href="/login?next=/ingest/curation">Sign In</a>
                        </Button>
                    }
                />
            </PageContainer>
        );
    }

    const uniqueDomains = new Set(items.map(i => {
        try { return new URL(i.url).hostname; }
        catch (e) { return 'invalid-url'; }
    })).size;

    const tableStatus: 'error' | 'loading' | 'idle' = loadError
        ? 'error'
        : loading && items.length === 0
            ? 'loading'
            : 'idle';

    const allSelected = selectedIndices.size === items.length && items.length > 0;

    return (
        <PageContainer>
            <PageHeader
                title="Manual Discovery Curation"
                description="Review and approve regulatory links disallowed by robots.txt or failing automated discovery."
                secondaryActions={
                    <Button
                        variant="secondary"
                        onClick={fetchQueue}
                        disabled={loading}
                        leadingIcon={
                            <RefreshCw
                                className={loading ? 'animate-spin motion-reduce:animate-none' : undefined}
                                strokeWidth={1.75}
                                aria-hidden="true"
                            />
                        }
                    >
                        Refresh
                    </Button>
                }
            />

            <div className="space-y-6">
                <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    {QUEUE_STATS(items.length, uniqueDomains).map((stat) => (
                        <Card key={stat.label} padding="compact">
                            <dt className="text-label text-re-text-muted">{stat.label}</dt>
                            <dd className="mt-2 text-title tabular-nums text-re-text-primary">
                                {tableStatus === 'loading'
                                    ? <Skeleton className="h-7 w-20" />
                                    : stat.value}
                            </dd>
                        </Card>
                    ))}
                </dl>

                <section className="space-y-3">
                    <div>
                        <h3 className="text-subheading text-re-text-primary">Discovery Queue</h3>
                        <p className="text-small text-re-text-tertiary">
                            Items in this list require human verification before being codified into the graph.
                        </p>
                    </div>

                    <div className="rounded-lg border border-re-border bg-re-surface-card">
                        {selectedIndices.size > 0 && (
                            <div className="flex flex-wrap items-center justify-end gap-2 border-b border-re-border-subtle px-4 py-3">
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={handleBulkReject}
                                >
                                    <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                    Reject ({selectedIndices.size})
                                </Button>
                                <Button size="sm" onClick={handleBulkApprove}>
                                    <CheckCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                    Approve ({selectedIndices.size})
                                </Button>
                            </div>
                        )}

                        {tableStatus === 'error' ? (
                            <div
                                role="alert"
                                className="m-4 flex gap-3 rounded-md border border-l-[3px] border-re-border border-l-re-danger bg-re-danger-bg px-4 py-3 text-ui text-re-text-secondary"
                            >
                                <AlertTriangle
                                    className="mt-0.5 h-4 w-4 shrink-0 text-re-danger"
                                    strokeWidth={1.75}
                                    aria-hidden="true"
                                />
                                <div className="min-w-0 flex-1">
                                    <p>{loadError}</p>
                                    <div className="mt-3">
                                        <Button variant="secondary" size="sm" onClick={fetchQueue}>
                                            Refresh
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        ) : tableStatus === 'loading' ? (
                            <div className="space-y-2 p-4" aria-busy="true">
                                <p className="sr-only" role="status">Loading discovery queue...</p>
                                {[0, 1, 2, 3, 4].map((row) => (
                                    <Skeleton key={row} className="h-10 w-full" />
                                ))}
                            </div>
                        ) : items.length === 0 ? (
                            <EmptyState
                                bare
                                icon={CheckCircle}
                                title="Queue is Clear"
                                description="All discovered regulatory links have been processed or cleared."
                            />
                        ) : (
                            <Table className="min-w-[720px]">
                                <caption className="sr-only">Discovery Queue</caption>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-10">
                                            <input
                                                type="checkbox"
                                                aria-label="Select all"
                                                className="h-4 w-4 rounded-sm border-re-border-strong accent-re-brand"
                                                checked={allSelected}
                                                onChange={toggleSelectAll}
                                            />
                                        </TableHead>
                                        <TableHead>Source Body</TableHead>
                                        <TableHead>URL / Link</TableHead>
                                        <TableHead className="text-right">Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {items.map((item) => (
                                        <TableRow
                                            key={`${item.body}-${item.index}`}
                                            data-state={selectedIndices.has(item.index) ? 'selected' : undefined}
                                        >
                                            <TableCell className="align-top">
                                                <input
                                                    type="checkbox"
                                                    aria-label={`Select ${item.body}`}
                                                    className="h-4 w-4 rounded-sm border-re-border-strong accent-re-brand"
                                                    checked={selectedIndices.has(item.index)}
                                                    onChange={() => toggleSelect(item.index)}
                                                />
                                            </TableCell>
                                            <TableCell className="align-top">
                                                <div className="flex flex-col items-start gap-1.5">
                                                    <span className="font-medium text-re-text-primary">{item.body}</span>
                                                    <Badge size="sm" mono>DISCOVERED</Badge>
                                                </div>
                                            </TableCell>
                                            <TableCell className="align-top">
                                                <div className="flex flex-col gap-2">
                                                    <code className="block max-w-[32rem] break-all rounded-md border border-re-border-subtle bg-re-surface-inset px-2 py-1.5 font-mono text-[0.8125rem] text-re-text-secondary">
                                                        {item.url}
                                                    </code>
                                                    <a
                                                        href={item.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="inline-flex w-fit items-center gap-1 text-small text-re-text-tertiary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                                                    >
                                                        <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                                                        Verify Document Source
                                                    </a>
                                                </div>
                                            </TableCell>
                                            <TableCell className="align-top text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        aria-label={`Reject ${item.body}`}
                                                        onClick={() => handleReject(item.index)}
                                                        disabled={processing !== null}
                                                    >
                                                        {processing === item.index
                                                            ? <Spinner size="sm" />
                                                            : <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="secondary"
                                                        onClick={() => handleApprove(item.index)}
                                                        disabled={processing !== null}
                                                    >
                                                        {processing === item.index ? (
                                                            <Spinner size="sm" />
                                                        ) : (
                                                            <>
                                                                <Search className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                                Approve
                                                            </>
                                                        )}
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        )}
                    </div>
                </section>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <Card>
                        <CardHeader>
                            <CardTitle>Curation Guidelines</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-3 text-ui text-re-text-secondary">
                                {GUIDELINES.map((guideline) => (
                                    <li key={guideline} className="flex gap-2">
                                        <span
                                            className="mt-2 h-1 w-1 shrink-0 rounded-full bg-re-text-muted"
                                            aria-hidden="true"
                                        />
                                        {guideline}
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>
                    <Card variant="inset">
                        <CardHeader>
                            <CardTitle>FSMA 204 Discovery</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="text-ui text-re-text-secondary">
                                RegEngine monitors FDA, USDA, and food safety regulatory sources for FSMA 204 traceability guidance.
                                Low-confidence links and disallowed domains are routed here for human review.
                            </p>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </PageContainer>
    );
}
