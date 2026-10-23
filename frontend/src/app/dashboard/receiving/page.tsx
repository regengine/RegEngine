'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
    AlertTriangle,
    ArrowLeft,
    Check,
    CheckCircle2,
    ClipboardList,
    Package,
    Plus,
    ScanLine,
    Truck,
} from 'lucide-react';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge } from '@/components/ui/status-badge';
import { useAuth } from '@/lib/auth-context';
import { getServiceURL } from '@/lib/api-config';
import { useToast } from '@/components/ui/use-toast';
import { parseGS1 } from '@/lib/gs1-parser';
import { scanMatchesItem } from '@/lib/scan-match';
import { notifyDashboardRefresh } from '@/hooks/use-dashboard-refresh';
import { NOT_SET } from '@/lib/empty-values';

/* ─── Types ─── */
interface LineItem {
    id: string;
    gtin: string;
    lotCode: string;
    productName: string;
    quantity: number;
    expiryDate: string;
    status: 'pending' | 'scanned' | 'mismatch';
    scannedAt?: string;
}

interface ReceivingSession {
    supplier: string;
    poNumber: string;
    expectedItems: LineItem[];
    unexpectedScans: LineItem[];
    startedAt: string;
    status: 'active' | 'completed';
}

const SESSION_STEPS: readonly (readonly [string, string])[] = [
    ['1. Start session', 'Enter the supplier and PO or ASN so the receiving CTE has source context.'],
    ['2. Add or scan items', 'Add expected lots from the PO, or scan directly to capture unexpected items.'],
    ['3. Confirm & ingest', 'Accepted scans become receiving events for audit logs and compliance scoring.'],
];

const EXPECTED_FIELD_HINTS: readonly (readonly [string, string])[] = [
    ['GTIN / barcode', 'Optional, but helps match labels quickly.'],
    ['Lot code', 'The traceability lot code used for FSMA records.'],
    ['Quantity', 'The cases or units received for this item.'],
];

const RECEIPT_COLUMNS: DataTableColumn<LineItem>[] = [
    { key: 'productName', header: 'Product', cell: (item) => item.productName || NOT_SET },
    { key: 'gtin', header: 'Barcode', mono: true, cell: (item) => item.gtin || NOT_SET },
    { key: 'lotCode', header: 'Lot', mono: true, cell: (item) => item.lotCode || NOT_SET },
    { key: 'quantity', header: 'Qty', align: 'right', cell: (item) => item.quantity },
];

/* ─── Component ─── */
export default function ReceivingDockPage() {
    const { isAuthenticated, tenantId } = useAuth();
    const { toast } = useToast();
    const [session, setSession] = useState<ReceivingSession | null>(null);
    const [supplier, setSupplier] = useState('');
    const [poNumber, setPoNumber] = useState('');
    const [manualGtin, setManualGtin] = useState('');
    const [manualLot, setManualLot] = useState('');
    const [manualProduct, setManualProduct] = useState('');
    const [manualQty, setManualQty] = useState('1');
    const [showAddExpected, setShowAddExpected] = useState(false);
    const [scanInput, setScanInput] = useState('');
    const [ingesting, setIngesting] = useState(false);
    const scanInputRef = useRef<HTMLInputElement>(null);

    /* ─── Start session ─── */
    const startSession = useCallback(() => {
        setSession({
            supplier: supplier || 'Unknown Supplier',
            poNumber: poNumber || `PO-${Date.now()}`,
            expectedItems: [],
            unexpectedScans: [],
            startedAt: new Date().toISOString(),
            status: 'active',
        });
        toast({ title: 'Receiving Session Started', description: `Supplier: ${supplier || 'Unknown'}` });
    }, [supplier, poNumber, toast]);

    const startSampleSession = useCallback(() => {
        const sampleSupplier = supplier || 'Valley Fresh Farms';
        const samplePo = poNumber || 'PO-2026-0042';
        setSupplier(sampleSupplier);
        setPoNumber(samplePo);
        setSession({
            supplier: sampleSupplier,
            poNumber: samplePo,
            expectedItems: [
                {
                    id: 'sample-romaine',
                    gtin: '00614141000012',
                    lotCode: 'TLC-ROM-20260426-001',
                    productName: 'Romaine Lettuce',
                    quantity: 18,
                    expiryDate: '',
                    status: 'pending',
                },
                {
                    id: 'sample-spring-mix',
                    gtin: '00614141000029',
                    lotCode: 'TLC-MIX-20260426-004',
                    productName: 'Spring Mix',
                    quantity: 12,
                    expiryDate: '',
                    status: 'pending',
                },
            ],
            unexpectedScans: [],
            startedAt: new Date().toISOString(),
            status: 'active',
        });
        toast({ title: 'Sample Receiving Session Started', description: 'Two expected items are ready to scan.' });
    }, [poNumber, supplier, toast]);

    /* ─── Add expected item ─── */
    const addExpectedItem = useCallback(() => {
        if (!session || (!manualGtin && !manualLot)) return;
        const item: LineItem = {
            id: `exp-${Date.now()}`,
            gtin: manualGtin,
            lotCode: manualLot,
            productName: manualProduct || `Product ${manualGtin || manualLot}`,
            quantity: parseInt(manualQty) || 1,
            expiryDate: '',
            status: 'pending',
        };
        setSession({ ...session, expectedItems: [...session.expectedItems, item] });
        setManualGtin(''); setManualLot(''); setManualProduct(''); setManualQty('1');
        setShowAddExpected(false);
    }, [session, manualGtin, manualLot, manualProduct, manualQty]);

    /* ─── Handle scan (keyboard wedge or manual) ─── */
    const handleScan = useCallback((raw: string) => {
        if (!session) return;
        const parsed = parseGS1(raw);
        const scannedGtin = parsed.gtin || '';
        const scannedLot = parsed.tlc || '';
        // The input invites typing a bare GTIN or lot code, but parseGS1 only
        // extracts values from AI-encoded / Digital Link strings — so a user
        // typing exactly what the Expected Items list displays never matched
        // and every scan landed in Unexpected Items. scanMatchesItem also
        // compares the raw string directly (matrix unit-tested in
        // lib/scan-match.test.ts).
        const scanCandidate = { gtin: parsed.gtin, lot: parsed.tlc, raw };
        const now = new Date().toISOString();

        // Try to match against expected items
        const updated = { ...session };
        let matched = false;

        for (const item of updated.expectedItems) {
            if (item.status !== 'pending') continue;
            if (scanMatchesItem(item, scanCandidate)) {
                item.status = 'scanned';
                item.scannedAt = now;
                if (parsed.expiryDate) item.expiryDate = parsed.expiryDate;
                matched = true;
                toast({ title: '✓ Match', description: item.productName });
                break;
            }
        }

        if (!matched) {
            // Unexpected scan — add to unexpected list
            updated.unexpectedScans.push({
                id: `unx-${Date.now()}`,
                gtin: scannedGtin,
                lotCode: scannedLot || raw,
                productName: scannedGtin ? `GTIN ${scannedGtin}` : `Scan: ${raw.slice(0, 30)}`,
                quantity: 1,
                expiryDate: parsed.expiryDate || '',
                status: 'mismatch',
                scannedAt: now,
            });
            toast({ title: '⚠ Unexpected Item', description: raw.slice(0, 40), variant: 'destructive' });
        }

        setSession(updated);
        setScanInput('');
        scanInputRef.current?.focus();
    }, [session, toast]);

    /* ─── GTIN auto-fill from catalog ─── */
    const lookupGtin = useCallback(async (gtin: string) => {
        if (!isAuthenticated || !tenantId || gtin.length < 8) return;
        try {
            const res = await fetchWithCsrf(
                `${getServiceURL('ingestion')}/api/v1/products/${tenantId}/lookup?gtin=${gtin}`,
                {
                    credentials: 'include',
                    signal: AbortSignal.timeout(8000),
                },
            );
            if (!res.ok) return;
            const data = await res.json();
            if (data.found && data.product) {
                setManualProduct(data.product.name || data.product.description || '');
            }
        } catch { /* best-effort */ }
    }, [isAuthenticated, tenantId]);

    /* ─── Confirm & Ingest all scanned items ─── */
    const confirmAll = useCallback(async () => {
        if (!session || !isAuthenticated || !tenantId) return;
        setIngesting(true);
        try {
            const allItems = [
                ...session.expectedItems.filter(i => i.status === 'scanned'),
                ...session.unexpectedScans,
            ];
            if (allItems.length === 0) {
                toast({ title: 'Nothing to ingest', description: 'Scan items first.' });
                setIngesting(false);
                return;
            }

            const events = allItems.map(item => ({
                cte_type: 'receiving',
                traceability_lot_code: item.lotCode || item.gtin || `RCV-${Date.now()}`,
                product_description: item.productName,
                quantity: item.quantity,
                unit_of_measure: 'cases',
                timestamp: item.scannedAt || new Date().toISOString(),
                location_name: `Receiving Dock — ${session.supplier}`,
                kdes: {
                    gtin: item.gtin || undefined,
                    lot_code: item.lotCode || undefined,
                    expiry_date: item.expiryDate || undefined,
                    po_number: session.poNumber,
                    supplier_name: session.supplier,
                },
            }));

            const res = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    source: 'receiving_dock',
                    tenant_id: tenantId,
                    events,
                }),
            });

            if (!res.ok) {
                // Same billing gate as FDA export: surface the reason
                // instead of an opaque "Error: Ingest failed".
                if (res.status === 402) {
                    throw new Error(
                        'Ingestion requires an active plan. Choose one under Settings → Manage Plan, then retry.'
                    );
                }
                let detail = '';
                try {
                    const payload = await res.json();
                    detail = payload?.error?.message || payload?.detail || '';
                } catch {
                    /* non-JSON body */
                }
                throw new Error(detail || `The ingestion service returned status ${res.status}.`);
            }
            const data = await res.json();
            setSession({ ...session, status: 'completed' });
            notifyDashboardRefresh();
            toast({
                title: 'Receiving Complete',
                description: `${data.accepted} items ingested into trace pipeline`,
            });
        } catch (err) {
            toast({
                title: 'Ingest Failed',
                description: err instanceof Error ? err.message : String(err),
                variant: 'destructive',
            });
        } finally {
            setIngesting(false);
        }
    }, [session, isAuthenticated, tenantId, toast]);

    /* ─── Stats ─── */
    const stats = session ? {
        total: session.expectedItems.length,
        scanned: session.expectedItems.filter(i => i.status === 'scanned').length,
        pending: session.expectedItems.filter(i => i.status === 'pending').length,
        unexpected: session.unexpectedScans.length,
    } : null;

    /* ─── Render ─── */
    return (
        <PageContainer>
            {/* Back link — the shell owns the breadcrumb; this stays as the
                dock's own return affordance. */}
            <Link href="/dashboard" className="mb-4 inline-flex">
                <Button variant="ghost" size="icon" aria-label="Back to dashboard">
                    <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Button>
            </Link>

            <PageHeader
                title="Receiving Dock"
                description="Scan incoming shipments against expected items"
            />

            <div className="space-y-6">
                {/* ─── Session Setup ─── */}
                {!session && (
                    <Card>
                        <CardHeader>
                            <div className="min-w-0">
                                <CardTitle>Start Receiving Session</CardTitle>
                                <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                                    Use this dock when a shipment arrives. Start a session, add expected PO items if you have them, scan labels, then confirm the matched items into the traceability pipeline.
                                </p>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid gap-3 md:grid-cols-3">
                                {SESSION_STEPS.map(([title, detail]) => (
                                    <div key={title} className="rounded-md border border-re-border-subtle bg-re-surface-inset px-3 py-2">
                                        <p className="text-ui font-medium text-re-text-primary">{title}</p>
                                        <p className="mt-1 text-small text-re-text-tertiary">{detail}</p>
                                    </div>
                                ))}
                            </div>
                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                <Field label="Supplier Name" htmlFor="receiving-supplier">
                                    <Input
                                        id="receiving-supplier"
                                        type="text"
                                        placeholder="e.g. Valley Fresh Farms"
                                        value={supplier}
                                        onChange={e => setSupplier(e.target.value)}
                                    />
                                </Field>
                                <Field label="PO / ASN Number" htmlFor="receiving-po">
                                    <Input
                                        id="receiving-po"
                                        type="text"
                                        placeholder="e.g. PO-2026-0042"
                                        value={poNumber}
                                        onChange={e => setPoNumber(e.target.value)}
                                    />
                                </Field>
                            </div>
                            <div className="flex flex-col gap-2 sm:flex-row">
                                <Button
                                    onClick={startSession}
                                    size="lg"
                                    className="w-full sm:w-auto"
                                    leadingIcon={<Truck strokeWidth={1.75} aria-hidden="true" />}
                                >
                                    Start Receiving
                                </Button>
                                <Button variant="outline" size="lg" onClick={startSampleSession} className="w-full sm:w-auto">
                                    Load sample PO
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* ─── Active Session ─── */}
                {session && session.status === 'active' && (
                    <>
                        {/* Session header */}
                        <Card>
                            <CardContent className="flex flex-wrap items-center justify-between gap-3">
                                <div className="flex flex-wrap items-center gap-3">
                                    <Badge>{session.supplier}</Badge>
                                    <span className="font-mono text-[0.8125rem] text-re-text-tertiary">{session.poNumber}</span>
                                </div>
                                {stats && (
                                    <div className="flex flex-wrap items-center gap-4 text-small text-re-text-secondary">
                                        <span>{stats.scanned} scanned</span>
                                        <span className="text-re-text-tertiary">{stats.pending} pending</span>
                                        {stats.unexpected > 0 && (
                                            <span className="inline-flex items-center gap-1.5">
                                                <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                                {stats.unexpected} unexpected
                                            </span>
                                        )}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Scan input — keyboard wedge or manual */}
                        <Card>
                            <CardContent>
                                <label
                                    htmlFor="receiving-scan-input"
                                    className="mb-1.5 flex items-center gap-1.5 text-ui font-medium text-re-text-primary"
                                >
                                    <ScanLine className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                    Scan barcode or type GTIN/lot code
                                </label>
                                <div className="flex gap-2">
                                    <Input
                                        id="receiving-scan-input"
                                        ref={scanInputRef}
                                        type="text"
                                        mono
                                        value={scanInput}
                                        onChange={e => setScanInput(e.target.value)}
                                        onKeyDown={e => { if (e.key === 'Enter' && scanInput.trim()) handleScan(scanInput.trim()); }}
                                        placeholder="Scan or type barcode..."
                                        autoFocus
                                        className="min-w-0"
                                    />
                                    <Button
                                        onClick={() => { if (scanInput.trim()) handleScan(scanInput.trim()); }}
                                        disabled={!scanInput.trim()}
                                        className="shrink-0"
                                    >
                                        Scan
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Add expected items */}
                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>Expected Items</CardTitle>
                                </div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="shrink-0"
                                    aria-expanded={showAddExpected}
                                    onClick={() => setShowAddExpected(!showAddExpected)}
                                    leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                                >
                                    Add expected item
                                </Button>
                            </CardHeader>
                            <CardContent>
                                {showAddExpected && (
                                    <div className="mb-4 space-y-2 rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                        <div className="grid grid-cols-2 gap-2">
                                            <div className="min-w-0">
                                                <label htmlFor="receiving-manual-gtin" className="sr-only">Barcode / GTIN</label>
                                                <Input
                                                    id="receiving-manual-gtin"
                                                    type="text"
                                                    mono
                                                    placeholder="Barcode / GTIN"
                                                    value={manualGtin}
                                                    onChange={e => { setManualGtin(e.target.value); if (e.target.value.length >= 8) lookupGtin(e.target.value); }}
                                                />
                                            </div>
                                            <div className="min-w-0">
                                                <label htmlFor="receiving-manual-lot" className="sr-only">Lot Code</label>
                                                <Input
                                                    id="receiving-manual-lot"
                                                    type="text"
                                                    placeholder="Lot Code"
                                                    value={manualLot}
                                                    onChange={e => setManualLot(e.target.value)}
                                                />
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-3 gap-2">
                                            <div className="col-span-2 min-w-0">
                                                <label htmlFor="receiving-manual-product" className="sr-only">Product name</label>
                                                <Input
                                                    id="receiving-manual-product"
                                                    type="text"
                                                    placeholder="Product name"
                                                    value={manualProduct}
                                                    onChange={e => setManualProduct(e.target.value)}
                                                />
                                            </div>
                                            <div className="min-w-0">
                                                <label htmlFor="receiving-manual-qty" className="sr-only">Qty</label>
                                                <Input
                                                    id="receiving-manual-qty"
                                                    type="number"
                                                    placeholder="Qty"
                                                    min="1"
                                                    value={manualQty}
                                                    onChange={e => setManualQty(e.target.value)}
                                                />
                                            </div>
                                        </div>
                                        <Button
                                            size="sm"
                                            onClick={addExpectedItem}
                                            disabled={!manualGtin && !manualLot}
                                            leadingIcon={<Check strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            Add to Expected
                                        </Button>
                                    </div>
                                )}

                                {/* Expected items list */}
                                {session.expectedItems.length === 0 ? (
                                    <div className="rounded-lg border border-dashed border-re-border bg-re-surface-card p-5">
                                        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                                            <div className="min-w-0">
                                                <p className="text-subheading text-re-text-primary">No expected items added yet</p>
                                                <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                                                    Add the lots you expect from the PO to turn scans into pass/fail checks. If the shipment is unplanned, scan directly and the dock will capture the items as unexpected receiving records for review.
                                                </p>
                                            </div>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => setShowAddExpected(true)}
                                                className="shrink-0"
                                                leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                                            >
                                                Add expected item
                                            </Button>
                                        </div>
                                        <dl className="mt-4 grid gap-2 md:grid-cols-3">
                                            {EXPECTED_FIELD_HINTS.map(([label, detail]) => (
                                                <div key={label} className="rounded-md bg-re-surface-inset px-3 py-2">
                                                    <dt className="text-label text-re-text-muted">{label}</dt>
                                                    <dd className="mt-1 text-small text-re-text-tertiary">{detail}</dd>
                                                </div>
                                            ))}
                                        </dl>
                                    </div>
                                ) : (
                                    <ul className="divide-y divide-re-border-subtle rounded-md border border-re-border-subtle">
                                        {session.expectedItems.map(item => (
                                            <li key={item.id} className="flex items-center gap-3 px-3 py-3">
                                                {item.status === 'scanned' ? (
                                                    <CheckCircle2 className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                ) : (
                                                    <Package className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                )}
                                                <div className="min-w-0 flex-1">
                                                    <div className="truncate text-ui font-medium text-re-text-primary">{item.productName}</div>
                                                    <div className="font-mono text-[0.8125rem] text-re-text-tertiary">
                                                        {item.gtin && `Barcode: ${item.gtin}`}
                                                        {item.gtin && item.lotCode && ' · '}
                                                        {item.lotCode && `Lot: ${item.lotCode}`}
                                                    </div>
                                                </div>
                                                {item.status === 'scanned' ? (
                                                    <StatusBadge state="compliant" label="Verified" size="sm" className="shrink-0" />
                                                ) : (
                                                    <Badge size="sm" className="shrink-0">{`×${item.quantity}`}</Badge>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </CardContent>
                        </Card>

                        {/* Unexpected scans */}
                        {session.unexpectedScans.length > 0 && (
                            <Card>
                                <CardHeader>
                                    <div className="min-w-0">
                                        <CardTitle>
                                            Unexpected Items ({session.unexpectedScans.length})
                                        </CardTitle>
                                    </div>
                                    <StatusBadge state="at-risk" label="Not Expected" size="sm" className="shrink-0" />
                                </CardHeader>
                                <CardContent>
                                    <ul className="divide-y divide-re-border-subtle rounded-md border border-re-border-subtle">
                                        {session.unexpectedScans.map(item => (
                                            <li key={item.id} className="flex items-center gap-3 px-3 py-3">
                                                <AlertTriangle className="h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                                <div className="min-w-0 flex-1">
                                                    <div className="truncate text-ui font-medium text-re-text-primary">{item.productName}</div>
                                                    <div className="font-mono text-[0.8125rem] text-re-text-tertiary">
                                                        {item.lotCode}
                                                        {item.expiryDate && ` · Exp: ${item.expiryDate}`}
                                                    </div>
                                                </div>
                                                <StatusBadge state="at-risk" label="Not Expected" size="sm" className="shrink-0" />
                                            </li>
                                        ))}
                                    </ul>
                                </CardContent>
                            </Card>
                        )}

                        {/* Confirm & Ingest */}
                        <div className="flex gap-3">
                            <Button
                                onClick={confirmAll}
                                disabled={ingesting || (stats?.scanned === 0 && session.unexpectedScans.length === 0)}
                                className="flex-1"
                                size="lg"
                                loading={ingesting}
                                leadingIcon={ingesting ? undefined : <CheckCircle2 strokeWidth={1.75} aria-hidden="true" />}
                            >
                                {ingesting ? 'Ingesting...' : <>Confirm &amp; Ingest All ({(stats?.scanned || 0) + session.unexpectedScans.length} items)</>}
                            </Button>
                        </div>
                    </>
                )}

                {/* ─── Completed Session ─── */}
                {session && session.status === 'completed' && (() => {
                    const allItems = [
                        ...session.expectedItems.filter(i => i.status === 'scanned'),
                        ...session.unexpectedScans,
                    ];
                    const ts = new Date().toLocaleString();
                    return (
                        <Card className="print:border" id="receipt">
                            <CardContent className="space-y-5">
                                {/* Header */}
                                <div className="space-y-2 text-center">
                                    <h2 className="text-heading text-re-text-primary">Receiving Complete</h2>
                                    <p className="text-ui text-re-text-secondary">
                                        {session.supplier}, PO {session.poNumber}
                                    </p>
                                    <p className="font-mono text-small text-re-text-tertiary">{ts}</p>
                                </div>

                                {/* Summary stats */}
                                <div className="grid grid-cols-3 gap-3">
                                    <StatTile label="Items Ingested" value={allItems.length} />
                                    <StatTile label="Expected Verified" value={session.expectedItems.filter(i => i.status === 'scanned').length} />
                                    <StatTile label="Unexpected Added" value={session.unexpectedScans.length} />
                                </div>

                                {/* Item detail table */}
                                {allItems.length > 0 && (
                                    <DataTable
                                        caption="Items ingested in this receiving session"
                                        columns={RECEIPT_COLUMNS}
                                        data={allItems}
                                        rowKey={(item, i) => `${item.id}-${i}`}
                                        density="high"
                                        minWidth="560px"
                                        stickyFirstColumn
                                    />
                                )}

                                {/* Actions */}
                                <div className="flex flex-wrap justify-center gap-3 print:hidden">
                                    <Button
                                        variant="outline"
                                        size="lg"
                                        onClick={() => window.print()}
                                        leadingIcon={<ClipboardList strokeWidth={1.75} aria-hidden="true" />}
                                    >
                                        Print Receipt
                                    </Button>
                                    <Button
                                        size="lg"
                                        onClick={() => { setSession(null); setSupplier(''); setPoNumber(''); }}
                                        leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                                    >
                                        New Session
                                    </Button>
                                    <Link href="/dashboard/audit-log">
                                        <Button variant="outline" size="lg">
                                            View Audit Log
                                        </Button>
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>
                    );
                })()}
            </div>
        </PageContainer>
    );
}
