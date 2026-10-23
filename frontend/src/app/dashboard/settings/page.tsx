'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import Link from 'next/link';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useCurrentSubscription } from '@/hooks/use-billing';
import {
    Building2, Key, Database, Plug,
    Save, CheckCircle2, CreditCard,
    Shield, Clock, ExternalLink,
    Zap, ArrowRight, Lock,
    User, UserCog, Bell, LifeBuoy,
} from 'lucide-react';

/* ── Account & workspace quick links ── */
// Single settings hub: these link out to the account-level pages that live
// under /settings/* plus the live notification preferences page.
const ACCOUNT_LINKS = [
    { label: 'Profile', desc: 'Name, email, and account details', href: '/settings/profile', icon: User },
    { label: 'Sign-in & Security', desc: 'Passkeys, sign-in codes, and sessions', href: '/settings/security', icon: Lock },
    { label: 'Team Management', desc: 'Invite teammates and manage roles', href: '/dashboard/settings/users', icon: UserCog },
    { label: 'Notifications', desc: 'Alert channels and delivery preferences', href: '/dashboard/notifications', icon: Bell },
    { label: 'Support', desc: 'Response windows and recall escalation', href: '/settings/support', icon: LifeBuoy },
];

/* ── Available Integrations Catalog ── */
// Integration catalog - status is updated from API if available
const INTEGRATIONS = [
    { id: 'sensitech', name: 'Sensitech TempTale', category: 'IoT', status: 'available', desc: 'Cold-chain temperature monitoring' },
    { id: 'tive', name: 'Tive Trackers', category: 'IoT', status: 'available', desc: 'Real-time shipment visibility' },
    { id: 'sap', name: 'SAP S/4HANA', category: 'ERP', status: 'available', desc: 'Enterprise resource planning' },
    { id: 'netsuite', name: 'Oracle NetSuite', category: 'ERP', status: 'available', desc: 'Cloud ERP and financials' },
    { id: 'walmart', name: 'Walmart GDSN', category: 'Retailer', status: 'coming_soon', desc: 'Global Data Synchronization' },
    { id: 'kroger', name: 'Kroger 84.51\u00b0', category: 'Retailer', status: 'coming_soon', desc: 'Retailer data exchange' },
    { id: 'epcis', name: 'EPCIS 2.0 Gateway', category: 'Standards', status: 'epcis_preview', desc: 'GS1 event format bridge; ingest in Preview' },
    { id: 'webhook', name: 'Custom Webhooks', category: 'Custom', status: 'preview', desc: 'Push events to your endpoints' },
];
/**
 * Integration status. `state` promotes the operational statuses to the
 * StatusBadge vocabulary (icon + label); the catalogue states stay neutral
 * pills, because "Available" and "Coming Soon" are not compliance states.
 */
const STATUS_CONFIG: Record<string, { state?: ComplianceState; label: string }> = {
    connected: { state: 'compliant', label: 'Connected' },
    pending: { state: 'pending', label: 'Pending Setup' },
    available: { label: 'Available' },
    disconnected: { label: 'Available' },
    coming_soon: { label: 'Coming Soon' },
    preview: { label: 'Preview / contact us' },
    epcis_preview: { label: 'Preview' },
};

const TABS = [
    { id: 'profile' as const, label: 'Company', icon: Building2 },
    { id: 'api' as const, label: 'API Keys', icon: Key },
    { id: 'retention' as const, label: 'Data Retention', icon: Database },
    { id: 'integrations' as const, label: 'Integrations', icon: Plug },
];

const PROFILE_FIELDS = [
    { label: 'Company Name', key: 'company_name' as const, placeholder: '' },
    { label: 'Primary Contact', key: 'primary_contact' as const, placeholder: '' },
    { label: 'Email', key: 'contact_email' as const, placeholder: '' },
    { label: 'Phone', key: 'phone' as const, placeholder: '' },
];

const RETENTION_ROWS = [
    { label: 'Event Records', value: 'Agreement-defined', note: 'Must satisfy the customer and regulatory posture configured for this workspace', icon: Shield },
    { label: 'Audit Log', value: 'Workflow-defined', note: 'Visibility depends on which audit surfaces and storage paths are enabled', icon: Lock },
    { label: 'Chain Hashes', value: 'Implementation-defined', note: 'Integrity evidence depends on the active persistence and export workflow', icon: Shield },
    { label: 'Export History', value: 'Workspace-defined', note: 'History availability depends on enabled export and storage services', icon: Clock },
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
    const effectiveTenantId = isSystemTenant ? null : tenantId;
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

    // Seed contact email from the authenticated user until the authoritative
    // settings response below hydrates the full profile.
    useEffect(() => {
        const contactEmail = user?.email || '';
        if (contactEmail) {
            setProfile(prev => ({
                ...prev,
                contact_email: contactEmail || prev.contact_email,
            }));
        }
    }, [user]);

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
        <PageContainer>
            {/* The dashboard shell owns the breadcrumb and the service-health
                badge: this page only renders its own header. */}
            <PageHeader
                title="Account Settings"
                description="Manage your organization, account, team, and integrations"
                primaryAction={
                    <Button
                        onClick={handleSave}
                        disabled={saving}
                        loading={saving}
                        size="lg"
                        className="w-full sm:w-auto"
                        leadingIcon={
                            saving ? undefined : saved
                                ? <CheckCircle2 strokeWidth={1.75} aria-hidden="true" />
                                : <Save strokeWidth={1.75} aria-hidden="true" />
                        }
                    >
                        {saving ? 'Saving...' : saved ? 'Saved' : 'Save Changes'}
                    </Button>
                }
            />

            <div className="space-y-6">
                {saveError && (
                    <Callout tone="danger" role="alert">
                        {saveError}
                    </Callout>
                )}

                {/* Plan Card */}
                <Card>
                    <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex min-w-0 items-center gap-3">
                            <CreditCard className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <div className="min-w-0">
                                {subLoading ? (
                                    <span className="flex items-center gap-2 text-ui text-re-text-tertiary">
                                        <Skeleton className="h-4 w-24" /> Loading plan...
                                    </span>
                                ) : subError ? (
                                    <div className="min-w-0">
                                        <span className="text-ui font-medium text-re-text-secondary">{planName}</span>
                                        <p className="mt-0.5 text-small text-re-text-tertiary">Unable to reach the billing service. Your plan is not affected.</p>
                                    </div>
                                ) : (
                                    <>
                                        <span className="text-ui font-medium text-re-text-primary">{planName}</span>
                                        {billingCycle && (
                                            <span className="ml-2 text-small text-re-text-tertiary">({billingCycle})</span>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>
                        <Link href="/pricing" className="shrink-0">
                            <Button
                                variant="outline"
                                size="sm"
                                trailingIcon={<ExternalLink strokeWidth={1.75} aria-hidden="true" />}
                            >
                                Manage Plan
                            </Button>
                        </Link>
                    </CardContent>
                </Card>

                {/* Account & workspace quick links */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {ACCOUNT_LINKS.map((item) => (
                        <Link key={item.href} href={item.href} className="block h-full no-underline">
                            <Card variant="interactive" padding="compact" className="flex h-full items-start gap-3">
                                <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <div className="min-w-0">
                                    <div className="text-ui font-medium text-re-text-primary">{item.label}</div>
                                    <div className="mt-0.5 text-small text-re-text-tertiary">{item.desc}</div>
                                </div>
                            </Card>
                        </Link>
                    ))}
                </div>

                {/* Tabs */}
                <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)}>
                    <TabsList className="w-full overflow-x-auto no-scrollbar">
                        {TABS.map((tab) => {
                            const Icon = tab.icon;
                            return (
                                <TabsTrigger key={tab.id} value={tab.id} className="shrink-0">
                                    <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" /> {tab.label}
                                    {tab.id === 'integrations' && (
                                        <Badge size="sm" className="ml-1">{integrations.filter(i => i.status === 'connected').length}</Badge>
                                    )}
                                </TabsTrigger>
                            );
                        })}
                    </TabsList>

                    {/* ── Company Profile Tab ── */}
                    <TabsContent value="profile">
                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>Company Profile</CardTitle>
                                    <CardDescription>Organization details used in compliance records and FDA exports</CardDescription>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    {PROFILE_FIELDS.map((field) => (
                                        <Field key={field.key} label={field.label} htmlFor={`settings-${field.key}`}>
                                            <Input
                                                id={`settings-${field.key}`}
                                                size="lg"
                                                value={profile[field.key]}
                                                onChange={e => setProfile({ ...profile, [field.key]: e.target.value })}
                                                placeholder={field.placeholder}
                                            />
                                        </Field>
                                    ))}
                                </div>
                                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                    <Field label="Company Type" htmlFor="settings-company-type">
                                        <select
                                            id="settings-company-type"
                                            value={profile.company_type}
                                            onChange={e => setProfile({ ...profile, company_type: e.target.value })}
                                            className={`${fieldControlClasses} h-11`}
                                        >
                                            <option value="grower">Grower</option>
                                            <option value="manufacturer">Manufacturer</option>
                                            <option value="distributor">Distributor</option>
                                            <option value="retailer">Retailer</option>
                                            <option value="importer">Importer</option>
                                        </select>
                                    </Field>
                                    <Field label="FDA FEI Number" htmlFor="settings-fei-number">
                                        <Input
                                            id="settings-fei-number"
                                            size="lg"
                                            value={profile.fei_number}
                                            onChange={e => setProfile({ ...profile, fei_number: e.target.value })}
                                            placeholder="Optional, used in FDA exports"
                                        />
                                    </Field>
                                </div>
                                <Field label="Address" htmlFor="settings-address">
                                    <Input
                                        id="settings-address"
                                        size="lg"
                                        value={profile.address}
                                        onChange={e => setProfile({ ...profile, address: e.target.value })}
                                    />
                                </Field>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ── API Keys Tab ── */}
                    <TabsContent value="api" className="space-y-4">
                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>API Keys</CardTitle>
                                    <CardDescription>Live API keys are issued by RegEngine for this workspace.</CardDescription>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                                    <div className="flex items-start gap-3">
                                        <Key className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <div className="min-w-0">
                                            <h4 className="text-subheading text-re-text-primary">Request a live API key</h4>
                                            <p className="mt-1 max-w-[70ch] text-small text-re-text-tertiary">
                                                API credentials are provisioned with your agreement. Contact us to enable API access; RegEngine issues the key for this workspace and sends it to you directly.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex flex-col gap-2 sm:flex-row">
                                    <Link href="/developer/portal" className="flex-1">
                                        <Button
                                            variant="outline"
                                            size="lg"
                                            className="w-full"
                                            leadingIcon={<ExternalLink strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            Developer Portal
                                        </Button>
                                    </Link>
                                    <Link href="/developer/portal/keys" className="flex-1">
                                        <Button
                                            variant="outline"
                                            size="lg"
                                            className="w-full"
                                            leadingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            About API Keys
                                        </Button>
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>API Usage Visibility</CardTitle>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="max-w-[70ch] text-ui text-re-text-secondary">
                                    Request volume, latency, and delivery health only appear once telemetry is enabled for an active API integration. Until then, usage review is handled through onboarding and implementation support.
                                </p>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ── Data Retention Tab ── */}
                    <TabsContent value="retention" className="space-y-4">
                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>Data Retention</CardTitle>
                                    <CardDescription>Retention and audit history depend on the active workspace agreement, storage path, and enabled services.</CardDescription>
                                </div>
                            </CardHeader>
                            <CardContent className="p-0">
                                <dl className="divide-y divide-re-border-subtle">
                                    {RETENTION_ROWS.map((item) => (
                                        <div key={item.label} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                                            <div className="flex min-w-0 items-start gap-3">
                                                <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                <div className="min-w-0">
                                                    <dt className="text-ui font-medium text-re-text-primary">{item.label}</dt>
                                                    <dd className="text-small text-re-text-tertiary">{item.note}</dd>
                                                </div>
                                            </div>
                                            <span className="shrink-0 font-mono text-[0.8125rem] text-re-text-primary">{item.value}</span>
                                        </div>
                                    ))}
                                </dl>
                            </CardContent>
                        </Card>

                        {/* What This Means */}
                        <Card>
                            <CardContent>
                                <div className="flex items-start gap-3">
                                    <Shield className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <div className="min-w-0">
                                        <h4 className="text-subheading text-re-text-primary">What This Means for Your Business</h4>
                                        <p className="mt-1 max-w-[70ch] text-small text-re-text-tertiary">
                                            This page reflects the current posture of your workspace, not a universal default for every customer. If you need fixed retention or evidence commitments for diligence, confirm them in your implementation scope or commercial terms.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ── Integrations Tab ── */}
                    <TabsContent value="integrations" className="space-y-4">
                        {/* Stats row */}
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                            <StatTile label="Connected" value={integrations.filter(i => i.status === 'connected').length} />
                            <StatTile label="Pending" value={integrations.filter(i => i.status === 'pending').length} />
                            <StatTile label="Available" value={integrations.filter(i => i.status === 'available' || i.status === 'disconnected').length} />
                        </div>

                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>Integrations</CardTitle>
                                    <CardDescription>Available delivery modes and onboarding paths for this workspace.</CardDescription>
                                </div>
                            </CardHeader>
                            <CardContent className="p-0">
                                <ul className="divide-y divide-re-border-subtle">
                                    {integrations.map((int) => {
                                        const cfg = STATUS_CONFIG[int.status];
                                        return (
                                            <li key={int.id} className="flex flex-col justify-between gap-2 px-5 py-4 sm:flex-row sm:items-center">
                                                <div className="min-w-0">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="text-ui font-medium text-re-text-primary">{int.name}</span>
                                                        <Badge size="sm">{int.category}</Badge>
                                                    </div>
                                                    <div className="mt-0.5 text-small text-re-text-tertiary">{int.desc}</div>
                                                </div>
                                                <div className="flex shrink-0 flex-wrap items-center gap-2">
                                                    {cfg.state ? (
                                                        <StatusBadge state={cfg.state} label={cfg.label} size="sm" />
                                                    ) : (
                                                        <Badge size="sm">{cfg.label}</Badge>
                                                    )}
                                                    {int.status === 'pending' && (
                                                        <Badge tone="warning" size="sm">Setup in progress</Badge>
                                                    )}
                                                    {int.status === 'coming_soon' && (
                                                        <Badge size="sm">Coming Soon</Badge>
                                                    )}
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </CardContent>
                        </Card>

                        {/* What This Means */}
                        <Card>
                            <CardContent>
                                <div className="flex items-start gap-3">
                                    <Zap className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <div className="min-w-0">
                                        <h4 className="text-subheading text-re-text-primary">What This Means for Your Business</h4>
                                        <p className="mt-1 max-w-[70ch] text-small text-re-text-tertiary">
                                            This catalog shows which delivery modes RegEngine can support, not a promise that every source is already live for this workspace. Connection status, automated ingest, and downstream scoring appear only after the relevant workflow is provisioned.
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Request integration CTA */}
                        <div className="rounded-lg border border-dashed border-re-border p-4 text-center">
                            <p className="mb-3 text-ui text-re-text-secondary">Don&apos;t see your system? We build custom integrations for design partners.</p>
                            <Link href="/contact">
                                <Button
                                    variant="outline"
                                    size="lg"
                                    trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                                >
                                    Request Integration
                                </Button>
                            </Link>
                        </div>
                    </TabsContent>
                </Tabs>
            </div>
        </PageContainer>
    );
}
