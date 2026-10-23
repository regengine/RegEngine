'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useId, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { ErrorState } from '@/components/ui/error-state';
import { Spinner } from '@/components/ui/spinner';
import { fieldControlClasses } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
    Bell,
    Mail,
    MessageSquare,
    Webhook,
    Smartphone,
    AlertTriangle,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';

/* ── Types matching NotificationPreferences ── */

interface NotificationChannel {
    channel: string;
    enabled: boolean;
    target: string;
}

interface AlertPreference {
    rule_id: string;
    rule_name: string;
    enabled: boolean;
    channels: string[];
    min_severity: string;
}

interface QuietHours {
    enabled: boolean;
    start_hour: number;
    end_hour: number;
    timezone: string;
    override_critical: boolean;
}

interface EscalationRule {
    enabled: boolean;
    escalate_after_minutes: number;
    escalate_to: string;
}

interface NotificationPreferences {
    tenant_id: string;
    channels: NotificationChannel[];
    alert_preferences: AlertPreference[];
    quiet_hours: QuietHours;
    escalation: EscalationRule;
    digest_enabled: boolean;
    digest_frequency: string;
    digest_time: string;
}

const CHANNEL_ICONS: Record<string, React.ElementType> = {
    email: Mail,
    slack: MessageSquare,
    webhook: Webhook,
    sms: Smartphone,
};

async function apiFetchPrefs(tenantId: string): Promise<NotificationPreferences> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/notifications/${tenantId}/preferences`, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiSavePrefs(tenantId: string, prefs: Partial<NotificationPreferences>): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/notifications/${tenantId}/preferences`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prefs),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
}

/**
 * A real switch: role, checked state and an accessible name bound to the row
 * label, with a 44px target around a 24px track.
 */
function Toggle({
    enabled,
    onToggle,
    labelledBy,
}: {
    enabled: boolean;
    onToggle: () => void;
    labelledBy: string;
}) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-labelledby={labelledBy}
            onClick={onToggle}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card"
        >
            <span
                className={cn(
                    'relative block h-6 w-11 rounded-full transition-colors duration-120 motion-reduce:transition-none',
                    enabled ? 'bg-re-brand' : 'bg-re-border-strong'
                )}
            >
                <span
                    className={cn(
                        'absolute left-0.5 top-0.5 block h-5 w-5 rounded-full transition-transform duration-120 motion-reduce:transition-none',
                        enabled ? 'translate-x-5 bg-re-brand-foreground' : 'translate-x-0 bg-re-surface-card'
                    )}
                />
            </span>
        </button>
    );
}

/** One label / description / control row — the shape repeated eight times here. */
function SettingRow({
    id,
    title,
    description,
    children,
}: {
    id: string;
    title: React.ReactNode;
    description?: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-3 px-5 py-3">
            <div className="min-w-0">
                <div id={id} className="text-ui font-medium text-re-text-primary">
                    {title}
                </div>
                {description && (
                    <div className="mt-0.5 text-small text-re-text-tertiary">{description}</div>
                )}
            </div>
            <div className="flex shrink-0 items-center gap-3">{children}</div>
        </div>
    );
}

export default function NotificationPrefsPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();
    const queryClient = useQueryClient();
    const isLoggedIn = isAuthenticated;
    const rowIdPrefix = useId();

    const { data: prefs = null, isLoading: loading, error: prefsError, refetch: refetchPrefs, isFetching } = useQuery({
        queryKey: ['notification-prefs', tenantId],
        queryFn: () => apiFetchPrefs(tenantId),
        enabled: isLoggedIn && !!tenantId,
        retry: 1,
    });

    const [localPrefs, setLocalPrefs] = useState<NotificationPreferences | null>(null);
    const [saved, setSaved] = useState(false);

    // Use local state for editing, initialize from query data
    const effectivePrefs = localPrefs ?? prefs;
    const fetchFailed = !!prefsError;

    const toggleChannel = (channelName: string) => {
        if (!effectivePrefs) return;
        setLocalPrefs({
            ...effectivePrefs,
            channels: effectivePrefs.channels.map(c => c.channel === channelName ? { ...c, enabled: !c.enabled } : c),
        });
    };

    const toggleAlert = (ruleId: string) => {
        if (!effectivePrefs) return;
        setLocalPrefs({
            ...effectivePrefs,
            alert_preferences: effectivePrefs.alert_preferences.map(a => a.rule_id === ruleId ? { ...a, enabled: !a.enabled } : a),
        });
    };

    const savePrefsMutation = useMutation({
        mutationFn: () => apiSavePrefs(tenantId, effectivePrefs!),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['notification-prefs', tenantId] });
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        },
    });

    const saving = savePrefsMutation.isPending;
    const saveError = savePrefsMutation.error?.message ?? null;

    const handleSave = () => {
        if (!effectivePrefs || !tenantId || fetchFailed) return;
        savePrefsMutation.mutate();
    };

    return (
        <PageContainer>
            <PageHeader
                title="Notification Preferences"
                description="Configure alert delivery for the channels currently enabled on this workspace"
                primaryAction={
                    !fetchFailed ? (
                        <Button
                            size="lg"
                            className="w-full sm:w-auto"
                            aria-live="polite"
                            onClick={handleSave}
                            disabled={saving || !effectivePrefs}
                        >
                            {saving ? <Spinner size="sm" /> : saved ? '✓ Saved' : 'Save Changes'}
                        </Button>
                    ) : undefined
                }
            />

            {/* Settings surfaces keep a readable form column inside the app width
                (SPEC §6.10) — a toggle 1,100px from its label is unusable. */}
            <div className="max-w-[760px] space-y-6">
                {loading && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {fetchFailed && <ErrorState message="We could not load this page." onRetry={() => refetchPrefs()} retrying={isFetching} />}

                {saveError && (
                    <Callout tone="danger" role="alert" icon={AlertTriangle}>
                        Failed to save preferences. Please try again.
                    </Callout>
                )}

                {effectivePrefs && !loading && !fetchFailed && (
                    <>
                        {/* Channels */}
                        <Card>
                            <CardHeader className="flex-col items-start gap-1">
                                <CardTitle>Delivery Channels</CardTitle>
                                <CardDescription>Only channels configured for this workspace appear here.</CardDescription>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="divide-y divide-re-border-subtle">
                                    {effectivePrefs.channels.map((ch) => {
                                        const Icon = CHANNEL_ICONS[ch.channel] || Bell;
                                        const rowId = `${rowIdPrefix}-channel-${ch.channel}`;
                                        return (
                                            <SettingRow
                                                key={ch.channel}
                                                id={rowId}
                                                title={
                                                    <span className="flex items-center gap-2 capitalize">
                                                        <Icon
                                                            className="h-4 w-4 shrink-0 text-re-text-tertiary"
                                                            strokeWidth={1.75}
                                                            aria-hidden="true"
                                                        />
                                                        {ch.channel}
                                                    </span>
                                                }
                                                description={ch.target ? <span className="truncate">{ch.target}</span> : undefined}
                                            >
                                                <Toggle
                                                    enabled={ch.enabled}
                                                    labelledBy={rowId}
                                                    onToggle={() => toggleChannel(ch.channel)}
                                                />
                                            </SettingRow>
                                        );
                                    })}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Alert Rules */}
                        <Card>
                            <CardHeader className="flex-col items-start gap-1">
                                <CardTitle>Alert Rules</CardTitle>
                                <CardDescription>Enable or disable notifications for each rule</CardDescription>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="divide-y divide-re-border-subtle">
                                    {effectivePrefs.alert_preferences.map((alert) => {
                                        const rowId = `${rowIdPrefix}-rule-${alert.rule_id}`;
                                        return (
                                            <SettingRow
                                                key={alert.rule_id}
                                                id={rowId}
                                                title={alert.rule_name}
                                                description={
                                                    <span className="flex flex-wrap gap-1">
                                                        {alert.channels.map(ch => (
                                                            <Badge key={ch} tone="neutral" size="sm">{ch}</Badge>
                                                        ))}
                                                        <Badge tone="neutral" size="sm">≥ {alert.min_severity}</Badge>
                                                    </span>
                                                }
                                            >
                                                <Toggle
                                                    enabled={alert.enabled}
                                                    labelledBy={rowId}
                                                    onToggle={() => toggleAlert(alert.rule_id)}
                                                />
                                            </SettingRow>
                                        );
                                    })}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Quiet Hours & Digest */}
                        <Card>
                            <CardHeader>
                                <CardTitle>Schedule</CardTitle>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="divide-y divide-re-border-subtle">
                                    <SettingRow
                                        id={`${rowIdPrefix}-quiet-hours`}
                                        title="Quiet Hours"
                                        description={
                                            <>
                                                Suppress non-critical {effectivePrefs.quiet_hours.start_hour}:00 – {effectivePrefs.quiet_hours.end_hour}:00
                                                {effectivePrefs.quiet_hours.override_critical && ' (critical bypass)'}
                                            </>
                                        }
                                    >
                                        <Toggle
                                            enabled={effectivePrefs.quiet_hours.enabled}
                                            labelledBy={`${rowIdPrefix}-quiet-hours`}
                                            onToggle={() => setLocalPrefs({ ...effectivePrefs, quiet_hours: { ...effectivePrefs.quiet_hours, enabled: !effectivePrefs.quiet_hours.enabled } })}
                                        />
                                    </SettingRow>

                                    <SettingRow
                                        id={`${rowIdPrefix}-digest`}
                                        title="Digest"
                                        description={`${effectivePrefs.digest_frequency} summary at ${effectivePrefs.digest_time}`}
                                    >
                                        <label htmlFor={`${rowIdPrefix}-digest-frequency`} className="sr-only">
                                            Digest frequency
                                        </label>
                                        <select
                                            id={`${rowIdPrefix}-digest-frequency`}
                                            value={effectivePrefs.digest_frequency}
                                            onChange={e => setLocalPrefs({ ...effectivePrefs, digest_frequency: e.target.value })}
                                            className={cn(fieldControlClasses, 'w-auto')}
                                        >
                                            <option value="daily">Daily</option>
                                            <option value="weekly">Weekly</option>
                                        </select>
                                        <Toggle
                                            enabled={effectivePrefs.digest_enabled}
                                            labelledBy={`${rowIdPrefix}-digest`}
                                            onToggle={() => setLocalPrefs({ ...effectivePrefs, digest_enabled: !effectivePrefs.digest_enabled })}
                                        />
                                    </SettingRow>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Escalation */}
                        <Card>
                            <CardHeader>
                                <CardTitle>Escalation</CardTitle>
                            </CardHeader>
                            <CardContent className="p-0">
                                <SettingRow
                                    id={`${rowIdPrefix}-escalation`}
                                    title="Auto-escalate unacknowledged alerts"
                                    description={
                                        <>
                                            If critical alert not acknowledged within {effectivePrefs.escalation.escalate_after_minutes} min
                                            {effectivePrefs.escalation.escalate_to && `, escalate to ${effectivePrefs.escalation.escalate_to}`}
                                        </>
                                    }
                                >
                                    <Toggle
                                        enabled={effectivePrefs.escalation.enabled}
                                        labelledBy={`${rowIdPrefix}-escalation`}
                                        onToggle={() => setLocalPrefs({ ...effectivePrefs, escalation: { ...effectivePrefs.escalation, enabled: !effectivePrefs.escalation.enabled } })}
                                    />
                                </SettingRow>
                            </CardContent>
                        </Card>
                    </>
                )}
            </div>
        </PageContainer>
    );
}
