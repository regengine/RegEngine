'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
    ArrowLeft,
    Check,
    CheckCircle2,
    ClipboardList,
    Loader2,
    Package,
    Plus,
    ScanLine,
    Trash2,
    Truck,
    X,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth-context';
import { getServiceURL } from '@/lib/api-config';
import { useToast } from '@/components/ui/use-toast';
import { parseGS1 } from '@/lib/gs1-parser';
import { notifyDashboardRefresh } from '@/hooks/use-dashboard-refresh';

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

/* ─── Component ─── */
export default function ReceivingDockPage() {
    const { apiKey, tenantId } = useAuth();
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
        const now = new Date().toISOString();

        // Try to match against expected items
        const updated = { ...session };
        let matched = false;

        for (const item of updated.expectedItems) {
            if (item.status !== 'pending') continue;
            const gtinMatch = item.gtin && scannedGtin && item.gtin === scannedGtin;
            const lotMatch = item.lotCode && scannedLot && item.lotCode === scannedLot;
            if (gtinMatch || lotMatch) {
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
        if (!apiKey || !tenantId || gtin.length < 8) return;
        try {
            const res = await fetchWithCsrf(
                `${getServiceURL('ingestion')}/api/v1/products/${tenantId}/lookup?gtin=${gtin}`,
                { headers: { 'X-RegEngine-API-Key': apiKey } },
            );
            if (!res.ok) return;
            const data = await res.json();
            if (data.found && data.product) {
                setManualProduct(data.product.name || data.product.description || '');
            }
        } catch { /* best-effort */ }
    }, [apiKey, tenantId]);

    /* ─── Confirm & Ingest all scanned items ─── */
    const confirmAll = useCallback(async () => {
        if (!session || !apiKey) return;
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
                headers: {
                    'Content-Type': 'application/json',
                    'X-RegEngine-API-Key': apiKey,
                    ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
                },
                body: JSON.stringify({
                    source: 'receiving_dock',
                    tenant_id: tenantId,
                    events,
                }),
            });

            if (!res.ok) throw new Error('Ingest failed');
            const data = await res.json();
            setSession({ ...session, status: 'completed' });
            notifyDashboardRefresh();
            toast({
                title: 'Receiving Complete',
                description: `${data.accepted} items ingested into trace pipeline`,
            });
        } catch (err) {
            toast({ title: 'Ingest Failed', description: String(err), variant: 'destructive' });
        } finally {
            setIngesting(false);
        }
    }, [session, apiKey, tenantId, toast]);

    /* ─── Stats ─── */
    const stats = session ? {
        total: session.expectedItems.length,
        scanned: session.expectedItems.filter(i => i.status === 'scanned').length,
        pending: session.expectedItems.filter(i => i.status === 'pending').length,
        unexpected: session.unexpectedScans.length,
    } : null;

    /* ─── Render ─── */
    return (
        <div className="space-y-6">
            <div className="flex items-center gap-4">
                <Link href="/dashboard">
                    <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
                </Link>
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Truck className="h-6 w-6" /> Receiving Dock
                    </h1>
                    <p className="text-sm text-muted-foreground">
                        Scan incoming shipments against expected items
                    </p>
                </div>
            </div>

            {/* ─── Session Setup ─── */}
            {!session && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg">Start Receiving Session</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                                <label className="text-xs font-medium text-muted-foreground mb-1 block">Supplier Name</label>
                                <input
                                    type="text" placeholder="e.g. Valley Fresh Farms"
                                    value={supplier} onChange={e => setSupplier(e.target.value)}
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-muted-foreground mb-1 block">PO / ASN Number</label>
                                <input
                                    type="text" placeholder="e.g. PO-2026-0042"
                                    value={poNumber} onChange={e => setPoNumber(e.target.value)}
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                />
                            </div>
                        </div>
                        <Button onClick={startSession} className="w-full sm:w-auto">
                            <Truck className="mr-2 h-4 w-4" /> Start Receiving
                        </Button>
                    </CardContent>
                </Card>
            )}

            {/* ─── Active Session ─── */}
            {session && session.status === 'active' && (
                <>
                    {/* Session header */}
                    <Card>
                        <CardContent className="pt-4 pb-3">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <div className="flex items-center gap-3">
                                    <Badge variant="secondary">{session.supplier}</Badge>
                                    <span className="text-xs text-muted-foreground font-mono">{session.poNumber}</span>
                                </div>
                                {stats && (
                                    <div className="flex items-center gap-4 text-xs">
                                        <span className="text-re-brand-dark font-medium">{stats.scanned} scanned</span>
                                        <span className="text-muted-foreground">{stats.pending} pending</span>
                                        {stats.unexpected > 0 && (
                                            <span className="text-re-warning font-medium">{stats.unexpected} unexpected</span>
                                        )}
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Scan input — keyboard wedge or manual */}
                    <Card>
                        <CardContent className="pt-4 pb-4">
                            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                                <ScanLine className="inline h-3 w-3 mr-1" />
                                Scan barcode or type GTIN/lot code
                            </label>
                            <div className="flex gap-2">
                                <input
                                    ref={scanInputRef}
                                    type="text"
                                    value={scanInput}
                                    onChange={e => setScanInput(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter' && scanInput.trim()) handleScan(scanInput.trim()); }}
                                    placeholder="Scan or type barcode..."
                                    className="flex h-10 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
                                    autoFocus
                                />
                                <Button
                                    onClick={() => { if (scanInput.trim()) handleScan(scanInput.trim()); }}
                                    disabled={!scanInput.trim()}
                                >
                                    Scan
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Add expected items */}
                    <Card>
                        <CardHeader className="pb-2">
                            <div className="flex items-center justify-between">
                                <CardTitle className="text-base">Expected Items</CardTitle>
                                <Button variant="outline" size="sm" onClick={() => setShowAddExpected(!showAddExpected)}>
                                    <Plus className="h-3 w-3 mr-1" /> Add Item
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {showAddExpected && (
                                <div className="mb-4 p-3 rounded-lg border bg-muted/30 space-y-2">
                                    <div className="grid grid-cols-2 gap-2">
                                        <input
                                            type="text" placeholder="Barcode / GTIN"
                                            value={manualGtin}
                                            onChange={e => { setManualGtin(e.target.value); if (e.target.value.length >= 8) lookupGtin(e.target.value); }}
                                            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm font-mono"
                                        />
                                        <input
                                            type="text" placeholder="Lot Code"
                                            value={manualLot} onChange={e => setManualLot(e.target.value)}
                                            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
                                        />
                                    </div>
                                    <div className="grid grid-cols-3 gap-2">
                                        <input
                                            type="text" placeholder="Product name"
                                            value={manualProduct} onChange={e => setManualProduct(e.target.value)}
                                            className="flex h-9 col-span-2 rounded-md border border-input bg-background px-3 py-1 text-sm"
                                        />
                                        <input
                                            type="number" placeholder="Qty" min="1"
                                            value={manualQty} onChange={e => setManualQty(e.target.value)}
                                            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
                                        />
                                    </div>
                                    <Button size="sm" onClick={addExpectedItem} disabled={!manualGtin && !manualLot}>
                                        <Check className="h-3 w-3 mr-1" /> Add to Expected
                                    </Button>
                                </div>
                            )}

                            {/* Expected items list */}
                            {session.expectedItems.length === 0 ? (
                                <p className="text-sm text-muted-foreground text-center py-6 italic">
                                    No expected items added yet. Add items from your PO or start scanning directly.
                                </p>
                            ) : (
                                <div className="space-y-2">
                                    {session.expectedItems.map(item => (
                                        <div
                                            key={item.id}
                                            className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                                                item.status === 'scanned'
                                                    ? 'bg-re-brand-muted border-re-brand dark:bg-re-brand/20 dark:border-re-brand'
                                                    : 'bg-background border-border'
                                            }`}
                                        >
                                            {item.status === 'scanned' ? (
                                                <CheckCircle2 className="h-5 w-5 text-re-brand flex-shrink-0" />
                                            ) : (
                                                <Package className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                                            )}
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium truncate">{item.productName}</div>
                                                <div className="text-xs text-muted-foreground font-mono">
                                                    {item.gtin && `Barcode: ${item.gtin}`}
                                                    {item.gtin && item.lotCode && ' · '}
                                                    {item.lotCode && `Lot: ${item.lotCode}`}
                                                </div>
                                            </div>
                                            <Badge variant={item.status === 'scanned' ? 'default' : 'secondary'} className="flex-shrink-0">
                                                {item.status === 'scanned' ? 'Verified' : `×${item.quantity}`}
                                            </Badge>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Unexpected scans */}
                    {session.unexpectedScans.length > 0 && (
                        <Card className="border-re-warning dark:border-re-warning">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base text-re-warning">
                                    Unexpected Items ({session.unexpectedScans.length})
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {session.unexpectedScans.map(item => (
                                        <div key={item.id} className="flex items-center gap-3 p-3 rounded-lg border border-re-warning bg-re-warning-muted dark:bg-re-warning/20 dark:border-re-warning">
                                            <X className="h-5 w-5 text-re-warning flex-shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium truncate">{item.productName}</div>
                                                <div className="text-xs text-muted-foreground font-mono">
                                                    {item.lotCode}
                                                    {item.expiryDate && ` · Exp: ${item.expiryDate}`}
                                                </div>
                                            </div>
                                            <Badge variant="outline" className="text-re-warning border-re-warning">
                                                Not Expected
                                            </Badge>
                                        </div>
                                    ))}
                                </div>
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
                        >
                            {ingesting ? (
                                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Ingesting...</>
                            ) : (
                                <><CheckCircle2 className="mr-2 h-4 w-4" /> Confirm &amp; Ingest All ({(stats?.scanned || 0) + session.unexpectedScans.length} items)</>
                            )}
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
                    <Card className="border-re-brand dark:border-re-brand print:border print:shadow-none" id="receipt">
                        <CardContent className="pt-6 space-y-5">
                            {/* Header */}
                            <div className="text-center space-y-2">
                                <CheckCircle2 className="h-12 w-12 text-re-brand mx-auto" />
                                <h2 className="text-xl font-bold">Receiving Complete</h2>
                                <p className="text-sm text-muted-foreground">
                                    {session.supplier} — PO {session.poNumber}
                                </p>
                                <p className="text-xs text-muted-foreground">{ts}</p>
                            </div>

                            {/* Summary stats */}
                            <div className="grid grid-cols-3 gap-3 text-center">
                                <div className="p-3 rounded-xl bg-re-brand/5 border border-re-brand/20">
                                    <div className="text-2xl font-bold text-re-brand-dark">{allItems.length}</div>
                                    <div className="text-[11px] text-muted-foreground">Items Ingested</div>
                                </div>
                                <div className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                    <div className="text-2xl font-bold">{session.expectedItems.filter(i => i.status === 'scanned').length}</div>
                                    <div className="text-[11px] text-muted-foreground">Expected Verified</div>
                                </div>
                                <div className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                    <div className="text-2xl font-bold">{session.unexpectedScans.length}</div>
                                    <div className="text-[11px] text-muted-foreground">Unexpected Added</div>
                                </div>
                            </div>

                            {/* Item detail table */}
                            {allItems.length > 0 && (
                                <div className="rounded-xl border border-[var(--re-border-default)] overflow-x-auto">
                                    <table className="w-full text-xs">
                                        <thead>
                                            <tr className="bg-[var(--re-surface-elevated)] text-left">
                                                <th className="p-2.5 font-medium">Product</th>
                                                <th className="p-2.5 font-medium">Barcode</th>
                                                <th className="p-2.5 font-medium">Lot</th>
                                                <th className="p-2.5 font-medium text-right">Qty</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {allItems.map((item, i) => (
                                                <tr key={i} className="border-t border-[var(--re-border-default)]">
                                                    <td className="p-2.5">{item.productName || '—'}</td>
                                                    <td className="p-2.5 font-mono text-[11px]">{item.gtin || '—'}</td>
                                                    <td className="p-2.5">{item.lotCode || '—'}</td>
                                                    <td className="p-2.5 text-right">{item.quantity}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}

                            {/* Actions */}
                            <div className="flex flex-wrap justify-center gap-3 print:hidden">
                                <Button
                                    variant="outline"
                                    onClick={() => window.print()}
                                    className="min-h-[48px] rounded-xl"
                                >
                                    <ClipboardList className="mr-2 h-4 w-4" /> Print Receipt
                                </Button>
                                <Button onClick={() => { setSession(null); setSupplier(''); setPoNumber(''); }} className="min-h-[48px] rounded-xl">
                                    <Plus className="mr-2 h-4 w-4" /> New Session
                                </Button>
                                <Link href="/dashboard/audit-log">
                                    <Button variant="outline" className="min-h-[48px] rounded-xl">
                                        View Audit Log
                                    </Button>
                                </Link>
                            </div>
                        </CardContent>
                    </Card>
                );
            })()}
        </div>
    );
}
