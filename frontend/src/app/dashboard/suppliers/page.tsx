'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import {
    Users,
    Link2,
    CheckCircle2,
    AlertTriangle,
    XCircle,
    Clock,
    Plus,
    Package,
    Activity,
    Mail,
    RefreshCw,
    Download,
    Send,
    Copy,
    ExternalLink,
    Trash2,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { useDashboardRefresh } from '@/hooks/use-dashboard-refresh';
import type {
    SupplierFacility,
    SupplierComplianceScore,
    SupplierComplianceGapsResponse,
    SupplierTLC,
    PortalLink,
} from '@/types/api';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface FacilityRow extends SupplierFacility {
    complianceScore: number | null;
    gapCount: number;
    tlcCount: number;
    lastEvent: string | null;
}

/* ------------------------------------------------------------------ */
/*  Config                                                             */
/* ------------------------------------------------------------------ */

function complianceLabel(score: number | null): { color: string; bg: string; label: string; icon: typeof CheckCircle2 } {
    if (score === null) return { color: '#6b7280', bg: 'rgba(107,114,128,0.08)', label: 'No Data', icon: Clock };
    if (score >= 80) return { color: '#10b981', bg: 'rgba(16,185,129,0.08)', label: 'Compliant', icon: CheckCircle2 };
    if (score >= 50) return { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', label: 'Partial', icon: AlertTriangle };
    return { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', label: 'Non-Compliant', icon: XCircle };
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function SupplierDashboardPage() {
    const { isAuthenticated } = useAuth();
    const isLoggedIn = isAuthenticated;

    const [facilities, setFacilities] = useState<FacilityRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Portal link state
    const [portalLinks, setPortalLinks] = useState<PortalLink[]>([]);
    const [showInviteForm, setShowInviteForm] = useState(false);
    const [inviteSupplierName, setInviteSupplierName] = useState('');
    const [inviteSupplierEmail, setInviteSupplierEmail] = useState('');
    const [inviteExpiresDays, setInviteExpiresDays] = useState(90);
    const [creatingLink, setCreatingLink] = useState(false);
    const [copiedLinkId, setCopiedLinkId] = useState<string | null>(null);

    // Add-facility form state
    const [showAddForm, setShowAddForm] = useState(false);
    const [newName, setNewName] = useState('');
    const [newStreet, setNewStreet] = useState('');
    const [newCity, setNewCity] = useState('');
    const [newState, setNewState] = useState('');
    const [newPostalCode, setNewPostalCode] = useState('');
    const [adding, setAdding] = useState(false);

    /* ---------- Fetch all data ------------------------------------ */
    // Phase 1: Load facility list fast (1 API call)
    // Phase 2: Lazy-enrich with compliance data in background (batched, non-blocking)
    const loadData = useCallback(async () => {
        if (!isLoggedIn) {
            setFacilities([]);
            setLoading(false);
            setError('Sign in to view your supplier facilities.');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            // Load portal links in parallel with facilities
            apiClient.listPortalLinks()
                .then((res) => setPortalLinks(res.links || []))
                .catch(() => { /* portal links are optional */ });

            // Phase 1: Show facilities immediately
            const rawFacilities = await apiClient.listSupplierFacilities();
            const initial: FacilityRow[] = rawFacilities.map(f => ({
                ...f,
                complianceScore: null,
                gapCount: 0,
                tlcCount: 0,
                lastEvent: null,
            }));
            setFacilities(initial);
            setLoading(false);

            // Phase 2: Enrich in batches of 5 (avoids 100+ simultaneous requests)
            const BATCH_SIZE = 5;
            for (let i = 0; i < rawFacilities.length; i += BATCH_SIZE) {
                const batch = rawFacilities.slice(i, i + BATCH_SIZE);
                const enriched = await Promise.all(
                    batch.map(async (f) => {
                        let complianceScore: number | null = null;
                        let gapCount = 0;
                        let tlcCount = 0;
                        let lastEvent: string | null = null;

                        try {
                            const [score, gaps, tlcs] = await Promise.all([
                                apiClient.getSupplierComplianceScore(f.id).catch(() => null),
                                apiClient.getSupplierComplianceGaps(f.id).catch(() => null),
                                apiClient.listSupplierTLCs(f.id).catch(() => []),
                            ]);
                            if (score) complianceScore = score.score;
                            if (gaps) gapCount = gaps.total;
                            tlcCount = (tlcs || []).length;
                            if (tlcs && tlcs.length > 0) {
                                const sorted = [...tlcs].sort(
                                    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
                                );
                                lastEvent = sorted[0].created_at;
                            }
                        } catch { /* swallow per-facility errors */ }

                        return { id: f.id, complianceScore, gapCount, tlcCount, lastEvent };
                    })
                );

                // Merge enrichment into existing state
                setFacilities(prev => prev.map(f => {
                    const update = enriched.find(e => e.id === f.id);
                    return update ? { ...f, ...update } : f;
                }));
            }
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Failed to load supplier data';
            setError(message);
            setLoading(false);
        }
    }, [isLoggedIn]);

    useEffect(() => { loadData(); }, [loadData]);

    // Re-fetch when data changes elsewhere (upload, bulk import, tab refocus)
    useDashboardRefresh(loadData);

    /* ---------- Create facility ----------------------------------- */
    const handleAdd = async () => {
        if (!newName.trim() || !newStreet.trim() || !newCity.trim() || !newState.trim() || !newPostalCode.trim()) return;

        setAdding(true);
        try {
            await apiClient.createSupplierFacility({
                name: newName.trim(),
                street: newStreet.trim(),
                city: newCity.trim(),
                state: newState.trim(),
                postal_code: newPostalCode.trim(),
                roles: [],
            });
            setNewName('');
            setNewStreet('');
            setNewCity('');
            setNewState('');
            setNewPostalCode('');
            setShowAddForm(false);
            await loadData();
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Failed to create facility';
            setError(message);
        } finally {
            setAdding(false);
        }
    };

    /* ---------- Portal Link Management ----------------------------- */
    const handleCreatePortalLink = async () => {
        if (!inviteSupplierName.trim() || creatingLink) return;
        setCreatingLink(true);
        try {
            const newLink = await apiClient.createPortalLink({
                supplier_name: inviteSupplierName.trim(),
                supplier_email: inviteSupplierEmail.trim() || undefined,
                expires_days: inviteExpiresDays,
            });
            setPortalLinks((prev) => [newLink, ...prev]);
            setInviteSupplierName('');
            setInviteSupplierEmail('');
            setShowInviteForm(false);
            // Auto-copy the link
            await navigator.clipboard.writeText(newLink.portal_url);
            setCopiedLinkId(newLink.portal_id);
            setTimeout(() => setCopiedLinkId(null), 3000);
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Failed to create portal link';
            setError(message);
        } finally {
            setCreatingLink(false);
        }
    };

    const handleCopyLink = async (link: PortalLink) => {
        await navigator.clipboard.writeText(link.portal_url);
        setCopiedLinkId(link.portal_id);
        setTimeout(() => setCopiedLinkId(null), 3000);
    };

    const handleRevokeLink = async (portalId: string) => {
        try {
            await apiClient.revokePortalLink(portalId);
            setPortalLinks((prev) =>
                prev.map((l) => l.portal_id === portalId ? { ...l, status: 'revoked' } : l)
            );
        } catch {
            setError('Failed to revoke portal link');
        }
    };

    /* ---------- FDA Export ---------------------------------------- */
    const handleFDAExport = async (format: 'csv' | 'xlsx', facilityId?: string) => {
        try {
            const { blob, filename } = await apiClient.downloadSupplierFDARecords(format, facilityId);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
        } catch {
            setError('FDA export failed. Please try again.');
        }
    };

    /* ---------- Summary stats ------------------------------------- */
    const totalFacilities = facilities.length;
    const compliantCount = facilities.filter(f => f.complianceScore !== null && f.complianceScore >= 80).length;
    const totalTLCs = facilities.reduce((sum, f) => sum + f.tlcCount, 0);
    const complianceRate = totalFacilities > 0 ? Math.round((compliantCount / totalFacilities) * 100) : 0;

    /* ---------- Relative time helper ------------------------------ */
    function relativeTime(iso: string | null): string | null {
        if (!iso) return null;
        const diff = Date.now() - new Date(iso).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    }

    /* ---------- Render -------------------------------------------- */
    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-3">
                            <Users className="h-6 w-6 text-[var(--re-brand)]" />
                            Supplier Management
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            Track facilities, compliance & traceability across your supply chain
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl min-h-[44px]"
                            onClick={() => loadData()}
                            disabled={loading}
                        >
                            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
                        </Button>
                        <Button
                            onClick={() => setShowAddForm(!showAddForm)}
                            className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[44px] active:scale-[0.97]"
                            disabled={!isLoggedIn}
                        >
                            <Plus className="h-4 w-4 mr-1" /> Add Facility
                        </Button>
                    </div>
                </div>

                {/* Error Banner */}
                {error && (
                    <div className="p-3 bg-re-danger-muted dark:bg-re-danger border border-re-danger dark:border-re-danger rounded-xl text-sm text-re-danger dark:text-re-danger">
                        {error}
                    </div>
                )}

                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
                    {[
                        { label: 'Facilities', value: totalFacilities, icon: Users },
                        { label: 'Compliant', value: compliantCount, icon: CheckCircle2 },
                        { label: 'Locations Tracked', value: totalTLCs, icon: Package },
                        { label: 'Compliance Rate', value: `${complianceRate}%`, icon: Activity },
                    ].map((stat) => (
                        <Card key={stat.label} className="border-[var(--re-border-default)]">
                            <CardContent className="py-3 sm:py-4">
                                <div className="flex items-center gap-1.5 sm:gap-2 mb-1">
                                    <stat.icon className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)] flex-shrink-0" />
                                    <span className="text-[11px] sm:text-xs text-muted-foreground truncate">{stat.label}</span>
                                </div>
                                <div className="text-xl sm:text-2xl font-bold">{loading ? '—' : stat.value}</div>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                {/* Portal Links — Invite Suppliers */}
                <Card className="border-[var(--re-border-default)]">
                    <CardContent className="py-4">
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                                <Link2 className="h-4 w-4 text-[var(--re-brand)]" />
                                <h2 className="text-sm font-semibold">Supplier Portal Links</h2>
                                <Badge variant="outline" className="text-[10px] py-0">
                                    {portalLinks.filter(l => l.status === 'active').length} active
                                </Badge>
                            </div>
                            <Button
                                onClick={() => setShowInviteForm(!showInviteForm)}
                                size="sm"
                                className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[36px] text-xs active:scale-[0.97]"
                                disabled={!isLoggedIn}
                            >
                                <Send className="h-3.5 w-3.5 mr-1" /> Invite Supplier
                            </Button>
                        </div>

                        <p className="text-xs text-muted-foreground mb-3">
                            Generate portal links for your suppliers to submit shipment data directly — no account needed.
                        </p>

                        {/* Invite Form */}
                        {showInviteForm && (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                className="mb-3"
                            >
                                <div className="bg-[var(--re-surface-elevated)] rounded-xl p-4 border border-[var(--re-brand)] space-y-3">
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                        <Input
                                            value={inviteSupplierName}
                                            onChange={(e) => setInviteSupplierName(e.target.value)}
                                            placeholder="Supplier name *"
                                            className="rounded-xl min-h-[40px] text-sm"
                                        />
                                        <Input
                                            value={inviteSupplierEmail}
                                            onChange={(e) => setInviteSupplierEmail(e.target.value)}
                                            placeholder="Contact email (optional)"
                                            type="email"
                                            className="rounded-xl min-h-[40px] text-sm"
                                        />
                                        <div className="flex gap-2">
                                            <select
                                                value={inviteExpiresDays}
                                                onChange={(e) => setInviteExpiresDays(Number(e.target.value))}
                                                className="flex-1 px-3 py-2 rounded-xl border border-input bg-background text-sm"
                                            >
                                                <option value={30}>30 days</option>
                                                <option value={90}>90 days</option>
                                                <option value={180}>180 days</option>
                                                <option value={365}>1 year</option>
                                            </select>
                                            <Button
                                                onClick={handleCreatePortalLink}
                                                disabled={creatingLink || !inviteSupplierName.trim()}
                                                className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[40px] text-xs active:scale-[0.97]"
                                            >
                                                {creatingLink ? <Spinner size="sm" /> : 'Generate Link'}
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        )}

                        {/* Portal Links List */}
                        {portalLinks.length > 0 && (
                            <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                                {portalLinks.map((link) => {
                                    const isActive = link.status === 'active';
                                    const isCopied = copiedLinkId === link.portal_id;
                                    const expiresDate = link.expires_at
                                        ? new Date(link.expires_at).toLocaleDateString()
                                        : 'N/A';

                                    return (
                                        <div
                                            key={link.portal_id}
                                            className={`flex items-center justify-between py-2 px-3 rounded-lg text-xs ${
                                                isActive
                                                    ? 'bg-[var(--re-surface-elevated)]'
                                                    : 'bg-[var(--re-surface-base)] opacity-60'
                                            }`}
                                        >
                                            <div className="flex items-center gap-2 min-w-0 flex-1">
                                                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                                    isActive ? 'bg-[var(--re-brand)]' : 'bg-gray-400'
                                                }`} />
                                                <span className="font-medium text-[var(--re-text-primary)] truncate">
                                                    {link.supplier_name}
                                                </span>
                                                <span className="text-[var(--re-text-disabled)] flex-shrink-0">
                                                    expires {expiresDate}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                                                {isActive && (
                                                    <>
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="h-7 w-7 p-0"
                                                            onClick={() => handleCopyLink(link)}
                                                            title="Copy link"
                                                        >
                                                            {isCopied ? (
                                                                <CheckCircle2 className="h-3.5 w-3.5 text-[var(--re-brand)]" />
                                                            ) : (
                                                                <Copy className="h-3.5 w-3.5" />
                                                            )}
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="h-7 w-7 p-0"
                                                            onClick={() => window.open(link.portal_url, '_blank')}
                                                            title="Open portal"
                                                        >
                                                            <ExternalLink className="h-3.5 w-3.5" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="h-7 w-7 p-0 text-re-danger hover:text-re-danger"
                                                            onClick={() => handleRevokeLink(link.portal_id)}
                                                            title="Revoke link"
                                                        >
                                                            <Trash2 className="h-3.5 w-3.5" />
                                                        </Button>
                                                    </>
                                                )}
                                                {!isActive && (
                                                    <Badge variant="outline" className="text-[9px] py-0 text-[var(--re-text-disabled)]">
                                                        {link.status}
                                                    </Badge>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {portalLinks.length === 0 && !showInviteForm && (
                            <div className="text-center py-3">
                                <p className="text-xs text-muted-foreground">
                                    No portal links yet. Invite a supplier to start collecting traceability data.
                                </p>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Add Facility Form */}
                {showAddForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                        <Card className="border-[var(--re-brand)]">
                            <CardContent className="py-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 sm:gap-3">
                                    <Input
                                        value={newName}
                                        onChange={e => setNewName(e.target.value)}
                                        placeholder="Facility name"
                                        className="rounded-xl min-h-[44px]"
                                    />
                                    <Input
                                        value={newStreet}
                                        onChange={e => setNewStreet(e.target.value)}
                                        placeholder="Street address"
                                        className="rounded-xl min-h-[44px]"
                                    />
                                    <Input
                                        value={newCity}
                                        onChange={e => setNewCity(e.target.value)}
                                        placeholder="City"
                                        className="rounded-xl min-h-[44px]"
                                    />
                                    <Input
                                        value={newState}
                                        onChange={e => setNewState(e.target.value)}
                                        placeholder="State"
                                        className="rounded-xl min-h-[44px]"
                                    />
                                    <Input
                                        value={newPostalCode}
                                        onChange={e => setNewPostalCode(e.target.value)}
                                        placeholder="Postal code"
                                        className="rounded-xl min-h-[44px]"
                                    />
                                    <Button
                                        onClick={handleAdd}
                                        disabled={adding || !newName.trim() || !newStreet.trim()}
                                        className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] active:scale-[0.97]"
                                    >
                                        {adding ? <Spinner size="sm" /> : <><Plus className="h-4 w-4 mr-1" /> Create</>}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Loading State */}
                {loading && (
                    <div className="flex items-center justify-center py-12">
                        <Spinner size="lg" />
                    </div>
                )}

                {/* Empty State */}
                {!loading && facilities.length === 0 && !error && (
                    <Card className="border-dashed">
                        <CardContent className="py-12 text-center">
                            <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                            <p className="text-lg font-medium mb-1">No facilities yet</p>
                            <p className="text-sm text-muted-foreground mb-4">
                                Add your first supplier facility to start tracking FSMA 204 compliance.
                            </p>
                            <Button
                                onClick={() => setShowAddForm(true)}
                                className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] active:scale-[0.97]"
                            >
                                <Plus className="h-4 w-4 mr-1" /> Add Facility
                            </Button>
                        </CardContent>
                    </Card>
                )}

                {/* Facility List */}
                {!loading && (
                    <div className="space-y-3">
                        {facilities.map((facility, i) => {
                            const comp = complianceLabel(facility.complianceScore);
                            const CompIcon = comp.icon;

                            return (
                                <motion.div
                                    key={facility.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: i * 0.05 }}
                                >
                                    <Card className="border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all">
                                        <CardContent className="py-3 sm:py-4">
                                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-1.5 sm:gap-2 mb-1 flex-wrap">
                                                        <span className="font-medium text-sm sm:text-base">{facility.name}</span>
                                                        <Badge
                                                            className="text-[9px] px-1.5 py-0"
                                                            style={{ background: comp.bg, color: comp.color }}
                                                        >
                                                            <CompIcon className="h-2.5 w-2.5 mr-0.5 inline" />
                                                            {comp.label}
                                                            {facility.complianceScore !== null && ` (${facility.complianceScore})`}
                                                        </Badge>
                                                        {facility.gapCount > 0 && (
                                                            <Badge
                                                                className="text-[9px] px-1.5 py-0"
                                                                variant="outline"
                                                                style={{ color: '#f59e0b', borderColor: '#f59e0b' }}
                                                            >
                                                                {facility.gapCount} gap{facility.gapCount !== 1 ? 's' : ''}
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2 sm:gap-4 text-[11px] sm:text-xs text-muted-foreground flex-wrap">
                                                        <span className="flex items-center gap-1">
                                                            <Mail className="h-3 w-3 flex-shrink-0" />
                                                            {facility.city}, {facility.state} {facility.postal_code}
                                                        </span>
                                                        <span>{facility.tlcCount} location{facility.tlcCount !== 1 ? 's' : ''}</span>
                                                        {facility.lastEvent && (
                                                            <span className="flex items-center gap-1">
                                                                <Clock className="h-3 w-3" /> {relativeTime(facility.lastEvent)}
                                                            </span>
                                                        )}
                                                    </div>
                                                    {facility.roles && facility.roles.length > 0 && (
                                                        <div className="flex gap-1 mt-1.5 sm:mt-2 flex-wrap">
                                                            {facility.roles.map((role) => (
                                                                <Badge key={role} variant="outline" className="text-[9px] py-0">
                                                                    {role}
                                                                </Badge>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    className="rounded-xl flex-shrink-0 min-h-[44px] active:scale-[0.97] w-full sm:w-auto"
                                                    onClick={() => handleFDAExport('xlsx', facility.id)}
                                                >
                                                    <Download className="h-3.5 w-3.5 mr-1" />
                                                    FDA Export
                                                </Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            );
                        })}
                    </div>
                )}

                {/* Bulk FDA Export */}
                {!loading && facilities.length > 0 && (
                    <div className="flex flex-col sm:flex-row justify-end gap-2 pt-2">
                        <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl min-h-[44px] active:scale-[0.97]"
                            onClick={() => handleFDAExport('xlsx')}
                        >
                            <Download className="h-3.5 w-3.5 mr-1" /> Export All (XLSX)
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="rounded-xl min-h-[44px] active:scale-[0.97]"
                            onClick={() => handleFDAExport('csv')}
                        >
                            <Download className="h-3.5 w-3.5 mr-1" /> Export All (CSV)
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}
