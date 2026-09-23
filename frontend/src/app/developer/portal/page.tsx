'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/layout/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import {
    Key, BarChart3, BookOpen, ArrowRight, Terminal, Zap,
    CheckCircle2, Circle, Webhook,
} from 'lucide-react';

interface DeveloperProfile {
    id: string;
    email: string;
    display_name: string | null;
    company_name: string | null;
    created_at: string;
}

interface DashboardStats {
    totalKeys: number;
    activeKeys: number;
    totalRequests: number;
}

export default function DeveloperPortalDashboard() {
    const { user: authUser, isHydrated } = useAuth();
    const [profile, setProfile] = useState<DeveloperProfile | null>(null);
    const [stats, setStats] = useState<DashboardStats>({ totalKeys: 0, activeKeys: 0, totalRequests: 0 });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function load() {
            // The server verifies Supabase auth; hydration supplies the client profile.
            if (!isHydrated) return;
            if (!authUser) {
                setLoading(false);
                return;
            }

            try {
                const response = await fetch('/api/developer/portal/dashboard', { credentials: 'include' });
                if (response.ok) {
                    const data = await response.json();
                    setProfile(data.profile);
                    setStats(data.stats);
                }
            } catch {
                // Network failure: fall through to the zero-state rather than
                // hanging on the spinner.
            } finally {
                setLoading(false);
            }
        }
        load();
    }, [authUser, isHydrated]);

    const greeting = profile?.display_name || profile?.email?.split('@')[0] || 'Developer';

    // Onboarding checklist
    // `href: null` means the step has nowhere to go — it renders as static text rather
    // than a link, so clicking it can't push a `#` entry and jump the page to the top.
    const onboardingSteps: { label: string; done: boolean; href: string | null }[] = [
        { label: 'Create your account', done: true, href: null },
        { label: 'Generate an API key', done: stats.activeKeys > 0, href: '/developer/portal/keys' },
        { label: 'Send your first event', done: stats.totalRequests > 0, href: '/docs' },
        { label: 'Try the API Playground', done: false, href: '/developer/portal/playground' },
        { label: 'Set up webhook ingestion', done: false, href: '/docs/webhooks' },
    ];
    const completedSteps = onboardingSteps.filter(s => s.done).length;
    const progress = Math.round((completedSteps / onboardingSteps.length) * 100);

    // The skeleton mirrors the header + checklist + tiles below, so nothing
    // jumps when the dashboard payload lands.
    if (loading) {
        return (
            <div className="space-y-8">
                <div className="space-y-2 border-b border-re-border-subtle pb-5">
                    <Skeleton className="h-8 w-64" />
                    <Skeleton className="h-4 w-80" />
                </div>
                <Skeleton className="h-52 w-full rounded-lg" />
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <Skeleton className="h-24 w-full rounded-lg" />
                    <Skeleton className="h-24 w-full rounded-lg" />
                    <Skeleton className="h-24 w-full rounded-lg" />
                </div>
            </div>
        );
    }

    // Hydrated with no session: say so instead of rendering a fabricated
    // zero-state dashboard for nobody.
    if (!authUser) {
        return (
            <Card className="px-6 py-14 text-center">
                <h1 className="text-title text-re-text-primary">Your session has expired</h1>
                <p className="mx-auto mt-2 max-w-[48ch] text-ui text-re-text-tertiary">
                    Sign in again to open your developer dashboard.
                </p>
                <Button asChild size="lg" className="mt-6">
                    <Link href="/login?next=/developer/portal" className="no-underline">
                        Sign in
                    </Link>
                </Button>
            </Card>
        );
    }

    return (
        <div className="space-y-8">
            <PageHeader
                title={`Welcome back, ${greeting}`}
                description={`${profile?.company_name ? `${profile.company_name} · ` : ''}Your developer dashboard for RegEngine.`}
                className="mb-0"
            />

            {/* Onboarding checklist */}
            {completedSteps < onboardingSteps.length && (
                <Card>
                    <CardHeader className="items-center">
                        <div className="min-w-0">
                            <CardTitle>Getting Started</CardTitle>
                            <p className="mt-0.5 text-small text-re-text-tertiary">
                                {completedSteps} of {onboardingSteps.length} steps complete
                            </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                            <span className="h-1.5 w-24 overflow-hidden rounded-full bg-re-surface-inset" aria-hidden="true">
                                <span
                                    className="block h-full rounded-full bg-re-text-primary transition-[width] duration-240 motion-reduce:transition-none"
                                    style={{ width: `${progress}%` }}
                                />
                            </span>
                            <span className="text-small tabular-nums text-re-text-secondary">{progress}%</span>
                        </div>
                    </CardHeader>
                    <CardContent className="py-2">
                        <ul className="divide-y divide-re-border-subtle">
                            {onboardingSteps.map((step) => {
                                const content = (
                                    <>
                                        {step.done
                                            ? <CheckCircle2 className="h-4 w-4 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                            : <Circle className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                        }
                                        <span className={step.done ? 'text-ui text-re-text-muted line-through' : 'text-ui text-re-text-primary'}>
                                            {step.label}
                                        </span>
                                        {!step.done && (
                                            <ArrowRight
                                                className="ml-auto h-4 w-4 shrink-0 text-re-text-muted"
                                                strokeWidth={1.75}
                                                aria-hidden="true"
                                            />
                                        )}
                                    </>
                                );

                                return (
                                    <li key={step.label}>
                                        {step.href ? (
                                            <Link
                                                href={step.href}
                                                className="flex items-center gap-3 rounded-md py-2.5 no-underline transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                                            >
                                                {content}
                                            </Link>
                                        ) : (
                                            <div className="flex items-center gap-3 py-2.5">
                                                {content}
                                            </div>
                                        )}
                                    </li>
                                );
                            })}
                        </ul>
                    </CardContent>
                </Card>
            )}

            {/* Stats */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {[
                    { label: 'Active API Keys', value: stats.activeKeys, sub: `${stats.totalKeys} total` },
                    // Sandbox keys don't record traffic — say so instead of implying an all-time count of zero.
                    { label: 'Total Requests', value: stats.totalRequests.toLocaleString(), sub: 'sandbox telemetry not yet recorded' },
                    // A signed-in console user without a developer profile is NOT an
                    // active developer account — don't claim otherwise.
                    profile
                        ? { label: 'Account Status', value: 'Active', sub: `since ${new Date(profile.created_at).toLocaleDateString()}` }
                        : { label: 'Account Status', value: 'Not provisioned', sub: 'developer access is enabled during onboarding' },
                ].map((card) => (
                    <StatTile key={card.label} label={card.label} value={card.value}>
                        <p className="text-small text-re-text-tertiary">{card.sub}</p>
                    </StatTile>
                ))}
            </div>

            {/* Quick links */}
            <div>
                <h2 className="mb-3 text-label text-re-text-muted">
                    Quick Links
                </h2>
                <ul className="divide-y divide-re-border-subtle border-y border-re-border-subtle">
                    {[
                        { label: 'API Keys', desc: 'Generate, revoke, and rotate', href: '/developer/portal/keys', icon: Key },
                        { label: 'Usage & Logs', desc: 'Requests, latency, errors', href: '/developer/portal/usage', icon: BarChart3 },
                        { label: 'Quickstart', desc: '5-minute integration guide', href: '/docs', icon: Zap },
                        { label: 'API Reference', desc: 'All endpoints documented', href: '/docs/api', icon: BookOpen },
                        { label: 'Playground', desc: 'Test endpoints live', href: '/developer/portal/playground', icon: Terminal },
                        { label: 'Webhook Ingestion', desc: 'Send events into RegEngine', href: '/docs/webhooks', icon: Webhook },
                    ].map((item) => (
                        <li key={item.href}>
                            <Link
                                href={item.href}
                                className="flex items-center gap-3 py-3 no-underline transition-colors duration-120 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                            >
                                <item.icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <span className="min-w-0 flex-1">
                                    <span className="block truncate text-ui font-medium text-re-text-primary">{item.label}</span>
                                    <span className="block truncate text-small text-re-text-tertiary">{item.desc}</span>
                                </span>
                                <ArrowRight className="h-4 w-4 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}
