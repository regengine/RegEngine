'use client';

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
    Save, CheckCircle2, Copy, Eye, EyeOff, CreditCard, BarChart3,
    Shield, RefreshCw, Clock, ExternalLink, ChevronRight,
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

export default function SettingsPage() {
    const { user, apiKey } = useAuth();
    const { tenantId } = useTenant();
    const { organizations } = useOrganizations();
    const currentOrg = organizations.find(o => o.id === tenantId);
    const { data: subscriptionData, isLoading: subLoading, isError: subError } = useCurrentSubscription();

    const [saved, setSaved] = useState(false);
    const [showKey, setShowKey] = useState(false);
    const [copiedKey, setCopiedKey] = useState<string | null>(null);
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

    // Fetch real integration status from backend
    const { data: integrationsData } = useQuery({
        queryKey: ['integrations', tenantId],
        queryFn: async () => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const res = await fetch(`${base}/api/v1/integrations/${tenantId}`, {
                headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey! },
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
        enabled: !!tenantId && !!apiKey,
    });
    const integrations = integrationsData ?? INTEGRATIONS;

    // Derive plan display from subscription data
    // Distinguish between: API error (unavailable), API success with no plan, API success with plan
    const planName = subError
        ? 'Billing information unavailable'
        : subscriptionData?.subscription?.tier_id
            ? subscriptionData.subscription.tier_id.charAt(0).toUpperCase() + subscriptionData.subscription.tier_id.slice(1) + ' Plan'
            : 'No Plan Selected';
    const billingCycle = subscriptionData?.subscription?.billing_cycle || '';

    const saveProfileMutation = useMutation({
        mutationFn: async () => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const res = await fetch(`${base}/api/v1/settings/${tenantId}/profile`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-RegEngine-API-Key': apiKey || '',
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
        if (!tenantId) return;
        saveProfileMutation.mutate();
    }, [tenantId, saveProfileMutation]);
    const handleCopy = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopiedKey(id);
        setTimeout(() => setCopiedKey(null), 2000);
    };

    const API_KEYS = [
        { id: 'prod', name: 'Production API Key', prefix: 'rge_prod_', full: 'rge_prod_a1b2c3d4e5f6g7h8', status: 'active', created: 'Jan 15, 2026', lastUsed: '2 min ago' },
        { id: 'dev', name: 'Development Key', prefix: 'rge_dev_', full: 'rge_dev_x9y8z7w6v5u4t3s2', status: 'active', created: 'Feb 3, 2026', lastUsed: '1 hour ago' },
    ];

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
                                <CardDescription>Manage API access credentials. Keys are scoped per-tenant with role-based access control.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {API_KEYS.map((key) => (
                                    <div key={key.id} className="p-3 sm:p-4 rounded-xl border border-[var(--re-border-default)] space-y-2">
                                        <div className="flex items-start sm:items-center justify-between gap-2">
                                            <div className="min-w-0">
                                                <div className="text-xs sm:text-sm font-medium flex items-center gap-2">
                                                    {key.name}
                                                    <Badge className="text-[9px] bg-re-brand-muted text-re-brand">{key.status}</Badge>
                                                </div>
                                                <div className="font-mono text-[11px] sm:text-xs text-muted-foreground flex items-center gap-2 mt-1">
                                                    <span className="truncate">{showKey ? key.full : `${key.prefix}${'*'.repeat(16)}`}</span>
                                                    <button onClick={() => setShowKey(!showKey)} className="min-w-[24px] min-h-[24px] flex items-center justify-center hover:text-[var(--re-brand)] transition-colors">
                                                        {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                                                    </button>
                                                    <button onClick={() => handleCopy(key.full, key.id)} className="min-w-[24px] min-h-[24px] flex items-center justify-center hover:text-[var(--re-brand)] transition-colors">
                                                        {copiedKey === key.id ? <CheckCircle2 className="h-3.5 w-3.5 text-[var(--re-brand)]" /> : <Copy className="h-3.5 w-3.5" />}
                                                    </button>
                                                </div>
                                            </div>
                                        </div>                                        <div className="flex items-center gap-4 text-[10px] sm:text-xs text-muted-foreground">
                                            <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> Created {key.created}</span>
                                            <span className="flex items-center gap-1"><RefreshCw className="h-3 w-3" /> Last used {key.lastUsed}</span>
                                        </div>
                                    </div>
                                ))}
                                <div className="flex gap-2">
                                    <Button variant="outline" className="flex-1 rounded-xl min-h-[48px]">
                                        <Key className="h-4 w-4 mr-1" /> Generate New Key
                                    </Button>
                                    <Link href="/developers" className="flex-1">
                                        <Button variant="outline" className="w-full rounded-xl min-h-[48px]">
                                            <ExternalLink className="h-4 w-4 mr-1" /> API Docs
                                        </Button>
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Usage summary */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <BarChart3 className="h-4 w-4 text-[var(--re-brand)]" />
                                    API Usage This Month
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
                                    {[
                                        { label: 'Total Requests', value: '12,847' },
                                        { label: 'Avg Latency', value: '142ms' },                                        { label: 'Error Rate', value: '0.02%' },
                                        { label: 'Uptime', value: '99.98%' },
                                    ].map((s) => (
                                        <div key={s.label} className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                            <div className="text-lg sm:text-xl font-bold">{s.value}</div>
                                            <div className="text-[10px] sm:text-xs text-muted-foreground mt-1">{s.label}</div>
                                        </div>
                                    ))}
                                </div>
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
                                <CardDescription>FSMA 204 requires minimum 2-year event record retention. RegEngine exceeds all requirements.</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {[
                                    { label: 'Event Records', value: '3 years (1,095 days)', note: 'FSMA requires \u2265 2 years', icon: Shield, status: 'compliant' },
                                    { label: 'Audit Log', value: '7 years (2,555 days)', note: 'Industry best practice', icon: Lock, status: 'compliant' },
                                    { label: 'Chain Hashes', value: 'Indefinite', note: 'SHA-256 integrity proofs kept permanently', icon: Shield, status: 'compliant' },
                                    { label: 'Export History', value: '1 year (365 days)', note: 'Download history and FDA packages', icon: Clock, status: 'compliant' },
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
                                            <CheckCircle2 className="h-3.5 w-3.5 text-re-brand" />
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
                                            Your event records are retained 50% longer than the FSMA 204 minimum, and audit logs are kept for 7 years to cover any FDA investigation window. Chain integrity hashes are stored indefinitely, meaning you can prove data authenticity for any historical record at any time.
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
                                <CardDescription>Connect third-party systems for automated event ingestion and data sync</CardDescription>
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
                                                {int.status === 'disconnected' && (
                                                    <Button variant="outline" size="sm" className="rounded-xl text-xs min-h-[36px]">
                                                        Connect <ChevronRight className="h-3 w-3 ml-0.5" />
                                                    </Button>
                                                )}
                                                {int.status === 'connected' && (
                                                    <Button variant="ghost" size="sm" className="rounded-xl text-xs min-h-[36px] text-muted-foreground">
                                                        Configure
                                                    </Button>
                                                )}
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
                                            Connected integrations automatically ingest traceability events from your existing systems — no manual data entry. Each connected source feeds into your compliance score in real-time. The EPCIS 2.0 Gateway ensures interoperability with any industry-standard trading partner.
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