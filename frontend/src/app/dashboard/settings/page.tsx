'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useOrganizations } from '@/hooks/use-organizations';
import { useCurrentSubscription } from '@/hooks/use-billing';
import {
    AlertTriangle, Settings, Building2, Key, Database, Plug,
    Save, CheckCircle2, CreditCard,
    Shield, Clock, ExternalLink,
    Zap, Globe, ArrowRight, Lock, Loader2,
} from 'lucide-react';

/* ── Available Integrations Catalog ── */
// Integration catalog — status is updated from API if available
const INTEGRATIONS = [
    { id: 'sensitech', name: 'Sensitech TempTale', category: 'IoT', status: 'available', desc: 'Cold-chain temperature monitoring' },
    { id: 'tive', name: 'Tive Trackers', category: 'IoT', status: 'available', desc: 'Real-time shipment visibility' },
    { id: 'sap', name: 'SAP S/4HANA', category: 'ERP', status: 'available', desc: 'Enterprise resource planning' },
    { id: 'netsuite', name: 'Oracle NetSuite', category: 'ERP', status: 'available', desc: 'Cloud ERP and financials' },
    { id: 'walmart', name: 'Walmart GDSN', category: 'Retailer', status: 'coming_soon', desc: 'Global Data Synchronization' },
    { id: 'kroger', name: 'Kroger 84.51\u00b0', category: 'Retailer', status: 'coming_soon', desc: 'Retailer data exchange' },
    { id: 'epcis', name: 'EPCIS 2.0 Gateway', category: 'Standards', status: 'available', desc: 'GS1 event format bridge' },
    { id: 'webhook', name: 'Custom Webhooks', category: 'Custom', status: 'available', desc: 'Push events to your endpoints' },
];
const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
    connected: { color: '#10b981', bg: 'rgba(16,185,129,0.1)', label: 'Connected' },
    pending: { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', label: 'Pending Setup' },
    available: { color: '#6b7280', bg: 'rgba(107,114,128,0.1)', label: 'Available' },
    disconnected: { color: '#6b7280', bg: 'rgba(107,114,128,0.1)', label: 'Available' },
    coming_soon: { color: '#6b7280', bg: 'rgba(107,114,128,0.08)', label: 'Coming Soon' },
};

const TABS = [
    { id: 'profile' as const, label: 'Company', icon: Building2 },
    { id: 'api' as const, label: 'API Keys', icon: Key },
    { id: 'retention' as const, label: 'Data Retention', icon: Database },
    { id: 'integrations' as const, label: 'Integrations', icon: Plug },
];

type SettingsProfile = {
    company_name?: string;
    company_type?: string;
    primary_contact?: string;
    contact_email?: string;
    phone?: string;
    address?: string;
    fei_number?: string;
};

type SettingsResponse = {
    profile?: SettingsProfile;
};

export default function SettingsPage() {
    const { user, isAuthenticated } = useAuth();
    const { tenantId, isSystemTenant } = useTenant();
    const { organizations } = useOrganizations();
    const effectiveTenantId = isSystemTenant ? null : tenantId;
    const currentOrg = organizations.find(o => o.id === effectiveTenantId);
    const { data: subscriptionData, isLoading: subLoading, isError: subError } = useCurrentSubscription(effectiveTenantId ?? undefined);

    const [saved, setSaved] = useState(false);
    const [activeTab, setActiveTab] = useState<'profile' | 'api' | 'retention' | 'integrations'>('profile');

    const [profile, setProfile] = useState({
        company_name: '',
        company_type: 'distributor',
        primary_contact: '',
        contact_email: '',
        phone: '',
        address: '',
        fei_number: '',
    });

    const { data: settingsData } = useQuery({
        queryKey: ['settings', tenantId],
        queryFn: async (): Promise<SettingsResponse | null> => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const res = await fetchWithCsrf(`${base}/api/v1/settings/${effectiveTenantId}`, {
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) return null;
            return res.json();
        },
        enabled: !!effectiveTenantId && isAuthenticated,
        retry: false,
    });

    // Populate profile from org context / auth user when available
    useEffect(() => {
        const orgName = currentOrg?.name || '';
        const contactEmail = user?.email || '';

        if (orgName || contactEmail) {
            setProfile(prev => ({
                ...prev,
                company_name: orgName || prev.company_name,
                contact_email: contactEmail || prev.contact_email,
            }));
        }
    }, [currentOrg, user]);

    useEffect(() => {
        const savedProfile = settingsData?.profile;
        if (!savedProfile) return;
        if (!Object.values(savedProfile).some(value => Boolean(value))) return;
        setProfile(prev => ({
            ...prev,
            company_name: savedProfile.company_name ?? prev.company_name,
            company_type: savedProfile.company_type ?? prev.company_type,
            primary_contact: savedProfile.primary_contact ?? prev.primary_contact,
            contact_email: savedProfile.contact_email ?? prev.contact_email,
            phone: savedProfile.phone ?? prev.phone,
            address: savedProfile.address ?? prev.address,
            fei_number: savedProfile.fei_number ?? prev.fei_number,
        }));
    }, [settingsData]);

    // Fetch real integration status from backend
    const { data: integrationsData } = useQuery({
        queryKey: ['integrations', tenantId],
        queryFn: async () => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const res = await fetchWithCsrf(`${base}/api/v1/integrations/status/${effectiveTenantId}`, {
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) return null;
            const data = await res.json();
            if (data?.integrations && Array.isArray(data.integrations)) {
                const statusMap = new Map(data.integrations.map((i: { id: string; status: string }) => [i.id, i.status]));
                return INTEGRATIONS.map(i => ({
                    ...i,
                    status: (statusMap.get(i.id) as string) || i.status,
                }));
            }
            return null;
        },
        enabled: !!effectiveTenantId && isAuthenticated,
    });
    const integrations = integrationsData ?? INTEGRATIONS;

    // Derive plan display from subscription data
    // Distinguish between: API error (unavailable), API success with no plan, API success with plan
    const planName = subError
        ? 'Billing information unavailable'
        : subscriptionData?.plan && subscriptionData.plan !== 'none'
            ? subscriptionData.plan.charAt(0).toUpperCase() + subscriptionData.plan.slice(1) + ' Plan'
            : 'No Plan Selected';
    const billingCycle = subscriptionData?.billing_period || '';

    const saveProfileMutation = useMutation({
        mutationFn: async () => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const res = await fetchWithCsrf(`${base}/api/v1/settings/${effectiveTenantId}/profile`, {
                method: 'PUT',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(profile),
            });
            if (!res.ok) throw new Error(`Save failed: ${res.status} ${res.statusText}`);
            return res.json();
        },
        onSuccess: () => {
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        },
    });

    const saving = saveProfileMutation.isPending;
    const saveError = saveProfileMutation.error?.message ?? null;
    const handleSave = useCallback(() => {
        if (!effectiveTenantId || !isAuthenticated) return;
        saveProfileMutation.mutate();
    }, [effectiveTenantId, isAuthenticated, saveProfileMutation]);
    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-4xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Settings' },
                ]} />

                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-2 sm:gap-3">
                            <Settings className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Account Settings
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">Manage your organization, API keys, and integrations</p>
                    </div>
                    <Button onClick={handleSave} disabled={saving} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] w-full sm:w-auto active:scale-[0.97]">
                        {saving ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Saving...</> : saved ? <><CheckCircle2 className="h-4 w-4 mr-1" /> Saved</> : <><Save className="h-4 w-4 mr-1" /> Save Changes</>}
                    </Button>
                </div>
                {saveError && (
                    <div className="p-3 rounded-lg bg-re-danger-muted dark:bg-re-danger/20 border border-re-danger dark:border-re-danger flex items-center gap-2 text-re-danger dark:text-re-danger text-sm">
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        <span>{saveError}</span>
                    </div>
                )}

                {/* Plan Card */}
                <Card className={`overflow-hidden ${subError ? 'border-[var(--re-border-default)]' : 'border-[var(--re-brand)]'}`}>
                    <div className={`h-1 ${subError ? 'bg-muted-foreground/30' : 'bg-gradient-to-r from-[var(--re-brand)] to-blue-500'}`} />
                    <CardContent className="py-4">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                            <div className="flex items-center gap-3">
                                <CreditCard className={`h-5 w-5 flex-shrink-0 ${subError ? 'text-muted-foreground' : 'text-[var(--re-brand)]'}`} />
                                <div>
                                    {subLoading ? (
                                        <span className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Loader2 className="h-3 w-3 animate-spin" /> Loading plan...
                                        </span>
                                    ) : subError ? (
                                        <div>
                                            <span className="font-medium text-sm text-muted-foreground">{planName}</span>
                                            <p className="text-xs text-muted-foreground mt-0.5">Unable to reach the billing service. Your plan is not affected.</p>
                                        </div>
                                    ) : (
                                        <>
                                            <span className="font-medium text-sm">{planName}</span>
                                            {billingCycle && (
                                                <span className="text-xs text-muted-foreground ml-2">({billingCycle})</span>
                                            )}
                                        </>
                                    )}
                                </div>
                            </div>
                            <div className="flex items-center gap-3 sm:gap-4 text-xs text-muted-foreground flex-wrap">
                                <Link href="/pricing">
                                    <Button variant="outline" size="sm" className="rounded-xl text-xs min-h-[44px]">
                                        Manage Plan <ExternalLink className="h-3 w-3 ml-1" />
                                    </Button>
                                </Link>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                {/* Tabs */}
                <div className="flex gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar pb-1">
                    {TABS.map((tab) => {
                        const Icon = tab.icon;
                        return (
                            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-medium border transition-all whitespace-nowrap min-h-[44px] active:scale-[0.96] flex-shrink-0 ${activeTab === tab.id ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]' : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'}`}>
                                <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" /> {tab.label}
                                {tab.id === 'integrations' && (
                                    <span className="ml-1 text-[10px] bg-white/20 px-1.5 rounded-full">{integrations.filter(i => i.status === 'connected').length}</span>
                                )}
                            </button>
                        );
                    })}
                </div>

                {/* ── Company Profile Tab ── */}
                {activeTab === 'profile' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Company Profile</CardTitle>
                                <CardDescription>Organization details used in compliance records and FDA exports</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3 sm:space-y-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                                    {[
                                        { label: 'Company Name', key: 'company_name' as const, placeholder: '' },
                                        { label: 'Primary Contact', key: 'primary_contact' as const, placeholder: '' },
                                        { label: 'Email', key: 'contact_email' as const, placeholder: '' },
                                        { label: 'Phone', key: 'phone' as const, placeholder: '' },
                                    ].map((field) => (
                                        <div key={field.key}>
                                            <label className="text-xs font-medium text-muted-foreground mb-1 block">{field.label}</label>                                            <Input value={profile[field.key]} onChange={e => setProfile({ ...profile, [field.key]: e.target.value })} placeholder={field.placeholder} className="rounded-xl min-h-[44px]" />
                                        </div>
                                    ))}
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Company Type</label>
                                        <select value={profile.company_type} onChange={e => setProfile({ ...profile, company_type: e.target.value })} className="flex min-h-[44px] w-full rounded-xl border border-input bg-background px-3 text-sm">
                                            <option value="grower">Grower</option>
                                            <option value="manufacturer">Manufacturer</option>
                                            <option value="distributor">Distributor</option>
                                            <option value="retailer">Retailer</option>
                                            <option value="importer">Importer</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">FDA FEI Number</label>
                                        <Input value={profile.fei_number} onChange={e => setProfile({ ...profile, fei_number: e.target.value })} placeholder="Optional — used in FDA exports" className="rounded-xl min-h-[44px]" />
                                    </div>
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Address</label>
                                    <Input value={profile.address} onChange={e => setProfile({ ...profile, address: e.target.value })} className="rounded-xl min-h-[44px]" />
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
                {/* ── API Keys Tab ── */}
                {activeTab === 'api' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Key className="h-4 w-4 text-[var(--re-brand)]" />
                                    API Keys
                                </CardTitle>
                                <CardDescription>Credentials appear here only after API access is enabled for this workspace.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-4">
                                    <div className="flex items-start gap-3">
                                        <Key className="h-4 w-4 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                        <div>
                                            <h4 className="text-sm font-semibold">No API credentials shown</h4>
                                            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                                                RegEngine provisions API keys during developer preview or implementation onboarding. This workspace does not have tenant-visible credentials enabled yet.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    <Link href="/developers" className="flex-1">
                                        <Button variant="outline" className="w-full rounded-xl min-h-[48px]">
                                            <ExternalLink className="h-4 w-4 mr-1" /> Developer Preview
                                        </Button>
                                    </Link>
                                    <Link href="/contact" className="flex-1">
                                        <Button variant="outline" className="w-full rounded-xl min-h-[48px]">
                                            <ArrowRight className="h-4 w-4 mr-1" /> Request API Setup
                                        </Button>
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Clock className="h-4 w-4 text-[var(--re-brand)]" />
                                    API Usage Visibility
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground leading-relaxed">
                                    Request volume, latency, and delivery health only appear once telemetry is enabled for an active API integration. Until then, usage review is handled through onboarding and implementation support.
                                </p>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* ── Data Retention Tab ── */}
                {activeTab === 'retention' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Database className="h-4 w-4 text-[var(--re-brand)]" />
                                    Data Retention
                                </CardTitle>
                                <CardDescription>Retention and audit history depend on the active workspace agreement, storage path, and enabled services.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {[
                                    { label: 'Event Records', value: 'Agreement-defined', note: 'Must satisfy the customer and regulatory posture configured for this workspace', icon: Shield },
                                    { label: 'Audit Log', value: 'Workflow-defined', note: 'Visibility depends on which audit surfaces and storage paths are enabled', icon: Lock },
                                    { label: 'Chain Hashes', value: 'Implementation-defined', note: 'Integrity evidence depends on the active persistence and export workflow', icon: Shield },
                                    { label: 'Export History', value: 'Workspace-defined', note: 'History availability depends on enabled export and storage services', icon: Clock },
                                ].map((item) => (                                    <div key={item.label} className="flex items-start sm:items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2">
                                        <div className="min-w-0 flex items-start gap-3">
                                            <item.icon className="h-4 w-4 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                            <div>
                                                <div className="text-xs sm:text-sm font-medium">{item.label}</div>
                                                <div className="text-[11px] sm:text-xs text-muted-foreground">{item.note}</div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 flex-shrink-0">
                                            <span className="text-xs sm:text-sm font-medium text-[var(--re-brand)]">{item.value}</span>
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>

                        {/* What This Means */}
                        <Card className="border-[var(--re-border-default)] mt-4">
                            <CardContent className="py-4">
                                <div className="flex items-start gap-3">
                                    <Shield className="h-5 w-5 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                    <div>
                                        <h4 className="text-sm font-semibold mb-1">What This Means for Your Business</h4>
                                        <p className="text-xs text-muted-foreground leading-relaxed">
                                            This page reflects the current posture of your workspace, not a universal default for every customer. If you need fixed retention or evidence commitments for diligence, confirm them in your implementation scope or commercial terms.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
                {/* ── Integrations Tab ── */}
                {activeTab === 'integrations' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                        {/* Stats row */}
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3">
                            {[
                                { label: 'Connected', value: integrations.filter(i => i.status === 'connected').length, color: '#10b981' },
                                { label: 'Pending', value: integrations.filter(i => i.status === 'pending').length, color: '#f59e0b' },
                                { label: 'Available', value: integrations.filter(i => i.status === 'available' || i.status === 'disconnected').length, color: '#6b7280' },
                            ].map((s) => (
                                <div key={s.label} className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                    <div className="text-lg sm:text-xl font-bold" style={{ color: s.color }}>{s.value}</div>
                                    <div className="text-[10px] sm:text-xs text-muted-foreground mt-1">{s.label}</div>
                                </div>
                            ))}
                        </div>

                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Plug className="h-4 w-4 text-[var(--re-brand)]" />
                                    Integrations
                                </CardTitle>
                                <CardDescription>Available delivery modes and onboarding paths for this workspace.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {integrations.map((int) => {
                                    const cfg = STATUS_CONFIG[int.status];
                                    return (
                                        <div key={int.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 sm:p-4 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2 hover:border-[var(--re-brand)] transition-colors">                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs sm:text-sm font-medium">{int.name}</span>
                                                    <Badge variant="outline" className="text-[9px] py-0">{int.category}</Badge>
                                                </div>
                                                <div className="text-[11px] text-muted-foreground mt-0.5">{int.desc}</div>
                                            </div>
                                            <div className="flex items-center gap-2 flex-shrink-0">
                                                <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium" style={{ background: cfg.bg, color: cfg.color }}>
                                                    <div className="w-2 h-2 rounded-full" style={{ background: cfg.color }} />
                                                    {cfg.label}
                                                </div>
                                                {int.status === 'pending' && (
                                                    <Badge className="text-[9px] bg-re-warning-muted0/10 text-re-warning">Setup in progress</Badge>
                                                )}
                                                {int.status === 'coming_soon' && (
                                                    <Badge className="text-[9px] bg-re-surface-card0/10 text-re-text-tertiary">Coming Soon</Badge>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </CardContent>
                        </Card>
                        {/* What This Means */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardContent className="py-4">
                                <div className="flex items-start gap-3">
                                    <Zap className="h-5 w-5 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                    <div>
                                        <h4 className="text-sm font-semibold mb-1">What This Means for Your Business</h4>
                                        <p className="text-xs text-muted-foreground leading-relaxed">
                                            This catalog shows which delivery modes RegEngine can support, not a guarantee that every source is already live for this tenant. Connection status, automated ingest, and downstream scoring appear only after the relevant workflow is provisioned.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Request integration CTA */}
                        <div className="p-4 rounded-xl border border-dashed border-[var(--re-border-default)] text-center">
                            <p className="text-sm text-muted-foreground mb-3">Don&apos;t see your system? We build custom integrations for design partners.</p>
                            <Link href="/contact">
                                <Button variant="outline" className="rounded-xl min-h-[44px]">
                                    Request Integration <ArrowRight className="h-3.5 w-3.5 ml-1" />
                                </Button>
                            </Link>
                        </div>
                    </motion.div>
                )}
            </div>
        </div>
    );
}
