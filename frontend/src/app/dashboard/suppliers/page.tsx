'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Users,
    Link2,
    CheckCircle2,
    Clock,
    Plus,
    Mail,
    RefreshCw,
    Download,
    Send,
    Copy,
    ExternalLink,
    Trash2,
    ArrowRight,
    SlidersHorizontal,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { NO_DATA_YET } from '@/lib/empty-values';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useDashboardRefresh } from '@/hooks/use-dashboard-refresh';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import { fetchWorkbenchReadinessSummary, type WorkbenchReadinessSnapshot } from '@/lib/api-hooks';
import type {
    SupplierFacility,
    PortalLink,
    IntegrationProfile,
    FacilityRemovalCheck,
} from '@/types/api';
import {
    NO_COMPLIANCE_DATA,
    countOrNull,
    deriveFacilityCompliance,
    gapRequirement,
    sumKnownCounts,
    type FacilityCompliance,
} from './supplier-metrics';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface FacilityRow extends SupplierFacility {
    compliance: FacilityCompliance;
    /** null until the lot-code list has loaded for this facility. */
    tlcCount: number | null;
    lastEvent: string | null;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Sanitise API / network errors into a user-friendly string. */
function friendlyError(err: unknown, fallback: string): string {
    if (!(err instanceof Error)) return fallback;
    const msg = err.message || '';
    // Suppress raw Axios / fetch messages that leak status codes or internals
    if (/status code \d{3}/i.test(msg) || /network error/i.test(msg) || /timeout/i.test(msg)) {
        return fallback;
    }
    return fallback;
}

/* ------------------------------------------------------------------ */
/*  Config                                                             */
/* ------------------------------------------------------------------ */

/**
 * Compliance state, not colour. The previous version returned raw hexes that
 * were applied through inline `style`, which put four ad-hoc greens/ambers/reds
 * outside the token layer and made the badge colour the *only* carrier of
 * meaning. A StatusBadge ships the icon and the label together (SPEC §1.6).
 */
function complianceLabel(score: number | null): { state: ComplianceState; label: string } {
    if (score === null) return { state: 'unknown', label: 'No Data' };
    if (score >= 80) return { state: 'compliant', label: 'Compliant' };
    if (score >= 50) return { state: 'at-risk', label: 'Partial' };
    return { state: 'non-compliant', label: 'Non-Compliant' };
}

const SUPPLIER_SETUP_STEPS = [
    {
        title: 'Add a facility',
        detail: 'Create the supplier or distribution location you need to track for FSMA 204 readiness.',
        icon: Users,
    },
    {
        title: 'Invite data owners',
        detail: 'Generate portal links so suppliers can submit shipment data without needing full dashboard access.',
        icon: Link2,
    },
    {
        title: 'Validate before evidence',
        detail: 'Use Inflow Lab to test CSVs, fix missing KDEs, and save a preflight run before production import.',
        icon: SlidersHorizontal,
    },
];

const POST_SETUP_ROWS = [
    { label: 'Facility rows', value: 'score + gaps' },
    { label: 'Portal links', value: 'active / revoked' },
    { label: 'FDA exports', value: 'per facility' },
] as const;

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function SupplierDashboardPage() {
    const { isAuthenticated, user } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = isAuthenticated;
    const isOwner = user?.role_name?.toLowerCase() === 'owner';

    const [facilities, setFacilities] = useState<FacilityRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [workbenchSummary, setWorkbenchSummary] = useState<WorkbenchReadinessSnapshot | null>(null);
    const [now, setNow] = useState(Date.now);

    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 60_000);
        return () => clearInterval(timer);
    }, []);

    // Remove facility state (Linear SEL-421)
    const [checkingFacilityId, setCheckingFacilityId] = useState<string | null>(null);
    const [removalTarget, setRemovalTarget] = useState<{
        facility: FacilityRow;
        check: FacilityRemovalCheck;
    } | null>(null);
    const [isRemoving, setIsRemoving] = useState(false);
    const [removalError, setRemovalError] = useState<string | null>(null);

    const handleOpenRemoval = async (facility: FacilityRow) => {
        setCheckingFacilityId(facility.id);
        setRemovalError(null);
        try {
            const check = await apiClient.checkFacilityRemoval(facility.id);
            setRemovalTarget({ facility, check });
        } catch (err: unknown) {
            setError(friendlyError(err, 'Failed to check facility removal.'));
        } finally {
            setCheckingFacilityId(null);
        }
    };

    const handleConfirmRemoval = async (facilityId: string) => {
        setIsRemoving(true);
        setRemovalError(null);
        try {
            await apiClient.deleteSupplierFacility(facilityId);
            setFacilities((prev) => prev.filter((f) => f.id !== facilityId));
            setRemovalTarget(null);
        } catch (err: unknown) {
            setRemovalError(friendlyError(err, 'Failed to remove facility.'));
        } finally {
            setIsRemoving(false);
        }
    };

    // Portal link state
    const [portalLinks, setPortalLinks] = useState<PortalLink[]>([]);
    const [showInviteForm, setShowInviteForm] = useState(false);
    const [inviteSupplierName, setInviteSupplierName] = useState('');
    const [inviteSupplierEmail, setInviteSupplierEmail] = useState('');
    const [inviteExpiresDays, setInviteExpiresDays] = useState(90);
    const [inviteProfileId, setInviteProfileId] = useState('');
    const [creatingLink, setCreatingLink] = useState(false);
    const [copiedLinkId, setCopiedLinkId] = useState<string | null>(null);
    const [integrationProfiles, setIntegrationProfiles] = useState<IntegrationProfile[]>([]);

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
            setWorkbenchSummary(null);
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
            apiClient.listIntegrationProfiles()
                .then((res) => setIntegrationProfiles(res.profiles || []))
                .catch(() => setIntegrationProfiles([]));

            if (tenantId) {
                fetchWorkbenchReadinessSummary(tenantId)
                    .then(setWorkbenchSummary)
                    .catch(() => setWorkbenchSummary(null));
            }

            // Phase 1: Show facilities immediately
            const rawFacilities = await apiClient.listSupplierFacilities();
            const initial: FacilityRow[] = rawFacilities.map(f => ({
                ...f,
                compliance: NO_COMPLIANCE_DATA,
                tlcCount: null,
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
                        let compliance: FacilityCompliance = NO_COMPLIANCE_DATA;
                        let tlcCount: number | null = null;
                        let lastEvent: string | null = null;

                        try {
                            const [score, gaps, tlcs] = await Promise.all([
                                apiClient.getSupplierComplianceScore(f.id).catch(() => null),
                                apiClient.getSupplierComplianceGaps(f.id).catch(() => null),
                                apiClient.listSupplierTLCs(f.id).catch(() => null),
                            ]);
                            compliance = deriveFacilityCompliance(score, gaps);
                            if (tlcs) {
                                tlcCount = countOrNull(tlcs.total);
                                const sorted = [...tlcs.items].sort(
                                    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
                                );
                                lastEvent = sorted[0]?.created_at ?? null;
                            }
                        } catch { /* swallow per-facility errors */ }

                        return { id: f.id, compliance, tlcCount, lastEvent };
                    })
                );

                // Merge enrichment into existing state
                setFacilities(prev => prev.map(f => {
                    const update = enriched.find(e => e.id === f.id);
                    return update ? { ...f, ...update } : f;
                }));
            }
        } catch (err: unknown) {
            setError(friendlyError(err, 'Unable to load supplier data. Please try again.'));
            setLoading(false);
        }
    }, [isLoggedIn, tenantId]);

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
            setError(friendlyError(err, 'Unable to create facility. Please try again.'));
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
                integration_profile_id: inviteProfileId || undefined,
            });
            setPortalLinks((prev) => [newLink, ...prev]);
            setInviteSupplierName('');
            setInviteSupplierEmail('');
            setInviteProfileId('');
            setShowInviteForm(false);
            // Auto-copy the link - best-effort only. clipboard.writeText
            // rejects whenever the document is unfocused or permission is
            // denied; sharing the API call's catch made a SUCCESSFUL link
            // creation render as "Unable to create portal link", inviting
            // retries that mint duplicate live links. The link row's Copy
            // button remains the fallback.
            try {
                await navigator.clipboard.writeText(newLink.portal_url);
                setCopiedLinkId(newLink.portal_id);
                setTimeout(() => setCopiedLinkId(null), 3000);
            } catch {
                /* copy manually from the list */
            }
        } catch (err: unknown) {
            setError(friendlyError(err, 'Unable to create portal link. Please try again.'));
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
    // Same derived state as each row's badge, so the tile and rows agree.
    const compliantCount = facilities.filter(f => f.compliance.state === 'compliant').length;
    const totalTLCs = sumKnownCounts(facilities.map(f => f.tlcCount));
    const complianceRate = totalFacilities > 0 ? Math.round((compliantCount / totalFacilities) * 100) : 0;

    /* ---------- Relative time helper ------------------------------ */
    function relativeTime(iso: string | null): string | null {
        if (!iso) return null;
        const diff = now - new Date(iso).getTime();
        if (!Number.isFinite(diff)) return null;
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    }

    /* ---------- Render -------------------------------------------- */
    const workbenchState = complianceLabel(workbenchSummary?.score ?? null);
    const openFixCount = workbenchSummary?.unresolved_fix_count ?? 0;
    const activePortalLinks = portalLinks.filter(l => l.status === 'active').length;

    return (
        <PageContainer>
            <PageHeader
                title="Supplier Management"
                description="Track facilities, compliance & traceability across your supply chain"
                secondaryActions={
                    <Button
                        variant="outline"
                        onClick={() => loadData()}
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
                primaryAction={
                    <Button
                        onClick={() => setShowAddForm(!showAddForm)}
                        aria-expanded={showAddForm}
                        disabled={!isLoggedIn}
                        leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                    >
                        Add Facility
                    </Button>
                }
            />

            <div className="space-y-6">
                {/* Error Banner */}
                {error && (
                    <Callout
                        tone="danger"
                        role="alert"
                        action={
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => { setError(null); loadData(); }}
                                leadingIcon={<RefreshCw strokeWidth={1.75} aria-hidden="true" />}
                            >
                                Retry
                            </Button>
                        }
                    >
                        {error}
                    </Callout>
                )}

                {/* Summary Cards */}
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                    <StatTile label="Facilities" value={totalFacilities} loading={loading} />
                    <StatTile label="Compliant" value={compliantCount} loading={loading} />
                    <StatTile label="Lot Codes Tracked" value={totalTLCs ?? 'No data yet'} loading={loading} />
                    <StatTile label="Compliance Rate" value={`${complianceRate}%`} loading={loading} />
                </div>

                {/* Inflow Workbench readiness */}
                <Card>
                    <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex min-w-0 items-center gap-4">
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-re-border bg-re-surface-inset text-subheading tabular-nums text-re-text-primary">
                                {workbenchSummary?.score ?? NO_DATA_YET}
                            </div>
                            <div className="min-w-0">
                                <div className="text-ui font-medium text-re-text-primary">Inflow Workbench readiness</div>
                                <p className="mt-0.5 text-small text-re-text-tertiary">
                                    {workbenchSummary?.label ?? 'No supplier preflight run saved yet'}
                                </p>
                            </div>
                        </div>
                        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center">
                            <StatusBadge state={workbenchState.state} label={workbenchState.label} size="sm" />
                            <Badge tone={openFixCount > 0 ? 'warning' : 'neutral'} size="sm">
                                {openFixCount} open fix{openFixCount === 1 ? '' : 'es'}
                            </Badge>
                            {experimentalFeaturesEnabled() && (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => { window.location.href = '/dashboard/inflow-lab'; }}
                                    trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                                >
                                    Open Workbench
                                </Button>
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Portal Links - Invite Suppliers */}
                <Card>
                    <CardHeader>
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <h2 className="text-subheading text-re-text-primary">Supplier Portal Links</h2>
                            <Badge size="sm">{activePortalLinks} active</Badge>
                        </div>
                        <Button
                            onClick={() => setShowInviteForm(!showInviteForm)}
                            aria-expanded={showInviteForm}
                            size="sm"
                            variant="outline"
                            className="shrink-0"
                            disabled={!isLoggedIn}
                            leadingIcon={<Send strokeWidth={1.75} aria-hidden="true" />}
                        >
                            Invite Supplier
                        </Button>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <p className="max-w-[70ch] text-ui text-re-text-secondary">
                            Generate portal links for your suppliers to submit shipment data directly. Attach a saved mapping profile when a source already has known field names.
                        </p>

                        {/* Invite Form */}
                        {showInviteForm && (
                            <div className="space-y-3 rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
                                    <div className="min-w-0">
                                        <label htmlFor="invite-supplier-name" className="sr-only">Supplier name</label>
                                        <Input
                                            id="invite-supplier-name"
                                            value={inviteSupplierName}
                                            onChange={(e) => setInviteSupplierName(e.target.value)}
                                            placeholder="Supplier name *"
                                        />
                                    </div>
                                    <div className="min-w-0">
                                        <label htmlFor="invite-supplier-email" className="sr-only">Contact email (optional)</label>
                                        <Input
                                            id="invite-supplier-email"
                                            value={inviteSupplierEmail}
                                            onChange={(e) => setInviteSupplierEmail(e.target.value)}
                                            placeholder="Contact email (optional)"
                                            type="email"
                                        />
                                    </div>
                                    <select
                                        value={inviteProfileId}
                                        onChange={(e) => setInviteProfileId(e.target.value)}
                                        className={fieldControlClasses}
                                        aria-label="Saved integration profile"
                                    >
                                        <option value="">No saved profile</option>
                                        {integrationProfiles
                                            .filter((profile) => profile.status !== 'archived')
                                            .map((profile) => (
                                                <option key={profile.profile_id} value={profile.profile_id}>
                                                    {profile.display_name}
                                                </option>
                                            ))}
                                    </select>
                                    <div className="flex min-w-0 gap-2">
                                        <select
                                            value={inviteExpiresDays}
                                            onChange={(e) => setInviteExpiresDays(Number(e.target.value))}
                                            className={`${fieldControlClasses} flex-1`}
                                            aria-label="Portal link expiry"
                                        >
                                            <option value={30}>30 days</option>
                                            <option value={90}>90 days</option>
                                            <option value={180}>180 days</option>
                                            <option value={365}>1 year</option>
                                        </select>
                                        <Button
                                            onClick={handleCreatePortalLink}
                                            disabled={creatingLink || !inviteSupplierName.trim()}
                                            loading={creatingLink}
                                            className="shrink-0"
                                        >
                                            Generate Link
                                        </Button>
                                    </div>
                                </div>
                                {integrationProfiles.length === 0 && (
                                    <p className="text-small text-re-text-tertiary">
                                        Create reusable mapping profiles from the Integrations dashboard to preconfigure supplier portal links.
                                    </p>
                                )}
                            </div>
                        )}

                        {/* Portal Links List */}
                        {portalLinks.length > 0 && (
                            <ul className="max-h-[200px] divide-y divide-re-border-subtle overflow-y-auto rounded-md border border-re-border-subtle">
                                {portalLinks.map((link) => {
                                    const isActive = link.status === 'active';
                                    const isCopied = copiedLinkId === link.portal_id;
                                    const expiresDate = link.expires_at
                                        ? new Date(link.expires_at).toLocaleDateString()
                                        : 'N/A';

                                    return (
                                        <li
                                            key={link.portal_id}
                                            className="flex items-center justify-between gap-2 px-3 py-2 text-small"
                                        >
                                            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                                                <StatusBadge
                                                    state={isActive ? 'compliant' : 'blocked'}
                                                    label={link.status}
                                                    size="sm"
                                                    className="capitalize"
                                                />
                                                <span className="truncate font-medium text-re-text-primary">
                                                    {link.supplier_name}
                                                </span>
                                                <span className="shrink-0 text-re-text-tertiary">
                                                    expires {expiresDate}
                                                </span>
                                                {link.integration_profile_id && (
                                                    <span className="inline-flex shrink-0 items-center gap-1 text-re-text-tertiary">
                                                        <SlidersHorizontal className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                                                        {integrationProfiles.find((profile) => profile.profile_id === link.integration_profile_id)?.display_name ?? 'Saved profile'}
                                                    </span>
                                                )}
                                            </div>
                                            {isActive && (
                                                <div className="ml-2 flex shrink-0 items-center gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => handleCopyLink(link)}
                                                        title="Copy link"
                                                        aria-label="Copy link"
                                                    >
                                                        {isCopied ? (
                                                            <CheckCircle2 className="h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                        ) : (
                                                            <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                        )}
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => window.open(link.portal_url, '_blank', 'noopener,noreferrer')}
                                                        title="Open portal"
                                                        aria-label="Open portal"
                                                    >
                                                        <ExternalLink className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-re-danger hover:text-re-danger"
                                                        onClick={() => handleRevokeLink(link.portal_id)}
                                                        title="Revoke link"
                                                        aria-label="Revoke link"
                                                    >
                                                        <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    </Button>
                                                </div>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        )}

                        {portalLinks.length === 0 && !showInviteForm && (
                            <p className="py-3 text-center text-small text-re-text-tertiary">
                                No portal links yet. Invite a supplier to start collecting traceability data.
                            </p>
                        )}
                    </CardContent>
                </Card>

                {/* Add Facility Form */}
                {showAddForm && (
                    <Card>
                        <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
                            <div className="min-w-0">
                                <label htmlFor="new-facility-name" className="sr-only">Facility name</label>
                                <Input
                                    id="new-facility-name"
                                    size="lg"
                                    value={newName}
                                    onChange={e => setNewName(e.target.value)}
                                    placeholder="Facility name"
                                />
                            </div>
                            <div className="min-w-0">
                                <label htmlFor="new-facility-street" className="sr-only">Street address</label>
                                <Input
                                    id="new-facility-street"
                                    size="lg"
                                    value={newStreet}
                                    onChange={e => setNewStreet(e.target.value)}
                                    placeholder="Street address"
                                />
                            </div>
                            <div className="min-w-0">
                                <label htmlFor="new-facility-city" className="sr-only">City</label>
                                <Input
                                    id="new-facility-city"
                                    size="lg"
                                    value={newCity}
                                    onChange={e => setNewCity(e.target.value)}
                                    placeholder="City"
                                />
                            </div>
                            <div className="min-w-0">
                                <label htmlFor="new-facility-state" className="sr-only">State</label>
                                <Input
                                    id="new-facility-state"
                                    size="lg"
                                    value={newState}
                                    onChange={e => setNewState(e.target.value)}
                                    placeholder="State"
                                />
                            </div>
                            <div className="min-w-0">
                                <label htmlFor="new-facility-postal-code" className="sr-only">Postal code</label>
                                <Input
                                    id="new-facility-postal-code"
                                    size="lg"
                                    value={newPostalCode}
                                    onChange={e => setNewPostalCode(e.target.value)}
                                    placeholder="Postal code"
                                />
                            </div>
                            <Button
                                size="lg"
                                onClick={handleAdd}
                                disabled={adding || !newName.trim() || !newStreet.trim()}
                                loading={adding}
                                leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                            >
                                Create
                            </Button>
                        </CardContent>
                    </Card>
                )}

                {/* Loading State */}
                {loading && (
                    <Card aria-busy="true">
                        <CardContent>
                            <p className="text-ui font-medium text-re-text-primary">Loading supplier network</p>
                            <p className="mt-1 max-w-[70ch] text-small text-re-text-tertiary">
                                Checking facilities, portal links, saved mapping profiles, compliance gaps, and latest lot activity.
                            </p>
                            <div className="mt-5 grid gap-3 md:grid-cols-3">
                                {[1, 2, 3].map((item) => (
                                    <Skeleton key={item} className="h-20 w-full" />
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Empty State */}
                {!loading && facilities.length === 0 && !error && (
                    <Card className="border-dashed">
                        <CardContent>
                            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
                                <div className="min-w-0">
                                    <p className="text-subheading text-re-text-primary">No supplier facilities yet</p>
                                    <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                                        Supplier Management is where each facility, portal link, mapping profile, and supplier-specific readiness signal comes together. Add one facility or invite a supplier to begin collecting traceability data.
                                    </p>
                                    <div className="mt-5 grid gap-3 md:grid-cols-3">
                                        {SUPPLIER_SETUP_STEPS.map((step) => (
                                            <div key={step.title} className="rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                                <step.icon className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                                <p className="mt-3 text-ui font-medium text-re-text-primary">{step.title}</p>
                                                <p className="mt-1 text-small text-re-text-tertiary">{step.detail}</p>
                                            </div>
                                        ))}
                                    </div>
                                    <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                                        <Button
                                            size="lg"
                                            onClick={() => setShowAddForm(true)}
                                            leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            Add Facility
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="lg"
                                            onClick={() => setShowInviteForm(true)}
                                            leadingIcon={<Send strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            Invite Supplier
                                        </Button>
                                    </div>
                                </div>
                                <div className="min-w-0 rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                                    <p className="text-ui font-medium text-re-text-primary">What will populate after setup</p>
                                    <dl className="mt-3 space-y-2 text-small text-re-text-tertiary">
                                        {POST_SETUP_ROWS.map((row) => (
                                            <div key={row.label} className="flex items-center justify-between gap-2 rounded-md bg-re-surface-card px-3 py-2">
                                                <dt>{row.label}</dt>
                                                <dd className="font-medium text-re-text-primary">{row.value}</dd>
                                            </div>
                                        ))}
                                    </dl>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Facility List - hairline ledger rows */}
                {!loading && facilities.length > 0 && (
                    <Card>
                        <ul className="divide-y divide-re-border-subtle">
                            {facilities.map((facility) => {
                                const comp = facility.compliance;

                                return (
                                    <li
                                        key={facility.id}
                                        className="flex flex-col gap-3 px-4 py-4 transition-colors duration-120 hover:bg-re-surface-inset/60 motion-reduce:transition-none sm:flex-row sm:items-center sm:justify-between sm:px-5"
                                    >
                                        <div className="min-w-0 flex-1">
                                            <div className="mb-1 flex flex-wrap items-center gap-2">
                                                <span className="text-ui font-medium text-re-text-primary">{facility.name}</span>
                                                <StatusBadge
                                                    state={comp.state}
                                                    size="sm"
                                                    label={`${comp.label}${comp.score !== null ? ` · score ${comp.score}` : ''}`}
                                                />
                                                {comp.gapCount > 0 && (
                                                    <Badge tone="warning" size="sm">
                                                        {comp.gapCount} gap{comp.gapCount !== 1 ? 's' : ''}
                                                    </Badge>
                                                )}
                                            </div>
                                            <div className="flex flex-wrap items-center gap-3 text-small text-re-text-tertiary sm:gap-4">
                                                <span className="flex items-center gap-1">
                                                    <Mail className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                    {facility.city}, {facility.state} {facility.postal_code}
                                                </span>
                                                <span>
                                                    {facility.tlcCount === null
                                                        ? 'No lot code data yet'
                                                        : `${facility.tlcCount} lot code${facility.tlcCount !== 1 ? 's' : ''}`}
                                                </span>
                                                {facility.lastEvent && (
                                                    <span className="flex items-center gap-1">
                                                        <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" /> {relativeTime(facility.lastEvent)}
                                                    </span>
                                                )}
                                            </div>
                                            {comp.gaps.length > 0 && (
                                                <ul className="mt-2 space-y-1 text-small text-re-text-secondary" aria-label={`Compliance gaps for ${facility.name}`}>
                                                    {comp.gaps.map((gap, index) => {
                                                        const requirement = gapRequirement(gap);
                                                        return (
                                                            <li key={`${gap.reason}-${gap.cte_type ?? 'none'}-${index}`} className="flex flex-wrap items-center gap-x-2">
                                                                <span>{gap.issue}</span>
                                                                <a
                                                                    href={requirement.href}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="inline-flex items-center gap-1 text-re-text-tertiary underline underline-offset-2 hover:text-re-text-primary"
                                                                >
                                                                    {requirement.label}
                                                                    <ExternalLink className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                                                                </a>
                                                            </li>
                                                        );
                                                    })}
                                                </ul>
                                            )}
                                            {facility.roles && facility.roles.length > 0 && (
                                                <div className="mt-2 flex flex-wrap gap-1">
                                                    {facility.roles.map((role) => (
                                                        <Badge key={role} size="sm">
                                                            {role}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="w-full shrink-0 sm:w-auto"
                                                onClick={() => handleFDAExport('xlsx', facility.id)}
                                                leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
                                            >
                                                FDA Export
                                            </Button>
                                            {isOwner && (
                                                <Button
                                                    variant="secondary"
                                                    size="sm"
                                                    className="w-full shrink-0 text-re-danger hover:text-re-danger sm:w-auto"
                                                    onClick={() => handleOpenRemoval(facility)}
                                                    disabled={checkingFacilityId === facility.id}
                                                    leadingIcon={<Trash2 strokeWidth={1.75} className="h-4 w-4" aria-hidden="true" />}
                                                >
                                                    {checkingFacilityId === facility.id ? 'Checking...' : 'Remove'}
                                                </Button>
                                            )}
                                        </div>
                                    </li>
                                );
                            })}
                        </ul>
                    </Card>
                )}

                {/* Bulk FDA Export */}
                {!loading && facilities.length > 0 && (
                    <div className="flex flex-col justify-end gap-2 pt-2 sm:flex-row">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleFDAExport('xlsx')}
                            leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
                        >
                            Export All (XLSX)
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleFDAExport('csv')}
                            leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
                        >
                            Export All (CSV)
                        </Button>
                    </div>
                )}
            </div>

            {/* Remove Facility Dialog (Linear SEL-421) */}
            <Dialog open={removalTarget !== null} onOpenChange={(open) => { if (!open && !isRemoving) setRemovalTarget(null); }}>
                <DialogContent>
                    {removalTarget && (
                        <>
                            <DialogHeader>
                                <DialogTitle>
                                    {removalTarget.check.allowed ? 'Remove facility?' : 'Facility Cannot Be Removed'}
                                </DialogTitle>
                                <DialogDescription>
                                    {removalTarget.check.allowed
                                        ? 'Review the facility details and configuration that will be permanently removed.'
                                        : 'This facility has linked records and cannot be removed until all referencing records are resolved.'}
                                </DialogDescription>
                            </DialogHeader>

                            {removalError && (
                                <Callout tone="danger">
                                    {removalError}
                                </Callout>
                            )}

                            {removalTarget.check.allowed ? (
                                <div className="space-y-3 text-small text-re-text-secondary">
                                    <p>The following will be permanently removed:</p>
                                    <div className="rounded-lg border border-re-border bg-re-surface-card p-3 space-y-2">
                                        <div>
                                            <span className="font-semibold text-re-text-primary">Facility Name: </span>
                                            <span>{removalTarget.check.facility_name}</span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-re-text-primary">Address: </span>
                                            <span>
                                                {removalTarget.check.address.street}, {removalTarget.check.address.city}, {removalTarget.check.address.state} {removalTarget.check.address.postal_code}
                                            </span>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-re-text-primary">Scoping Configuration: </span>
                                            <span>
                                                {removalTarget.check.scoping_config_count > 0
                                                    ? `${removalTarget.check.scoping_config_count} FTL scoping category configuration(s)`
                                                    : 'No FTL category scoping configurations'}
                                            </span>
                                        </div>
                                    </div>
                                    <p className="text-re-text-tertiary">
                                        This action cannot be undone. Zero traceability lots, CTE events, or other records reference this facility.
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-3 text-small text-re-text-secondary">
                                    <p>
                                        Facilities with active or historical records cannot be deleted. The facility is referenced by:
                                    </p>
                                    <div className="rounded-lg border border-re-border bg-re-surface-card p-3 space-y-2">
                                        <div className="flex justify-between">
                                            <span className="text-re-text-primary">Traceability lots (TLCs):</span>
                                            <span className="font-mono font-medium">{removalTarget.check.lots_count}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-re-text-primary">CTE events:</span>
                                            <span className="font-mono font-medium">{removalTarget.check.cte_events_count}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-re-text-primary">Other records:</span>
                                            <span className="font-mono font-medium">{removalTarget.check.funnel_events_count}</span>
                                        </div>
                                    </div>
                                    <p className="text-re-text-tertiary">
                                        All referencing records must be removed before this facility can be deleted.
                                    </p>
                                </div>
                            )}

                            <DialogFooter className="gap-2 sm:gap-0">
                                <Button
                                    variant="secondary"
                                    onClick={() => setRemovalTarget(null)}
                                    disabled={isRemoving}
                                >
                                    {removalTarget.check.allowed ? 'Cancel' : 'Done'}
                                </Button>
                                {removalTarget.check.allowed && (
                                    <Button
                                        variant="danger"
                                        onClick={() => handleConfirmRemoval(removalTarget.facility.id)}
                                        disabled={isRemoving}
                                    >
                                        {isRemoving ? 'Removing...' : 'Remove facility'}
                                    </Button>
                                )}
                            </DialogFooter>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </PageContainer>
    );
}
