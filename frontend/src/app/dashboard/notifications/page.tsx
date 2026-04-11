'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import {
    Bell,
    Mail,
    MessageSquare,
    Webhook,
    Smartphone,
    Clock,
    ArrowUp,
    Settings,
    Shield,
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

async function apiFetchPrefs(tenantId: string, apiKey: string): Promise<NotificationPreferences> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/notifications/${tenantId}/preferences`, {
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiSavePrefs(tenantId: string, apiKey: string, prefs: Partial<NotificationPreferences>): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/notifications/${tenantId}/preferences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
        body: JSON.stringify(prefs),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
}

function Toggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
    return (
        <button
            onClick={onToggle}
            className={`relative w-11 h-6 rounded-full transition-all flex-shrink-0 ${enabled ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-elevated)]'}`}
            style={{ minWidth: 44, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: enabled ? 'flex-end' : 'flex-start', padding: '0 2px' }}
        >
            <motion.div
                className="w-5 h-5 rounded-full bg-white shadow"
                layout
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            />
        </button>
    );
}

export default function NotificationPrefsPage() {
    const { isAuthenticated, apiKey } = useAuth();
    const { tenantId } = useTenant();
    const queryClient = useQueryClient();
    const isLoggedIn = isAuthenticated;

    const { data: prefs = null, isLoading: loading, error: prefsError } = useQuery({
        queryKey: ['notification-prefs', tenantId],
        queryFn: () => apiFetchPrefs(tenantId, apiKey || ''),
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
        mutationFn: () => apiSavePrefs(tenantId, apiKey || '', effectivePrefs!),
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
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-3xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <Settings className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Notification Preferences
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            Configure how and when you receive compliance alerts
                        </p>
                    </div>
                    {!fetchFailed && (
                        <Button onClick={handleSave} disabled={saving || !effectivePrefs} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] w-full sm:w-auto active:scale-[0.97]">
                            {saving ? <Spinner size="sm" /> : saved ? '✓ Saved' : 'Save Changes'}
                        </Button>
                    )}
                </div>

                {!isLoggedIn && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to manage notification preferences.
                        </CardContent>
                    </Card>
                )}

                {loading && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {fetchFailed && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6">
                            <div className="flex flex-col items-center gap-3 text-center">
                                <AlertTriangle className="h-8 w-8 text-orange-500 flex-shrink-0" />
                                <div>
                                    <p className="text-sm font-medium text-foreground">
                                        Notification preferences are currently unavailable.
                                    </p>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Please try again later. If this persists, contact support.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {saveError && (
                    <Card className="border-red-300 dark:border-red-700">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <p className="text-sm">Failed to save preferences. Please try again.</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {effectivePrefs && !loading && !fetchFailed && (
                    <>
                        {/* Channels */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Bell className="h-4 w-4 text-[var(--re-brand)]" />
                                    Delivery Channels
                                </CardTitle>
                                <CardDescription>Choose how alerts reach you</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-2 sm:space-y-3">
                                {effectivePrefs.channels.map((ch) => {
                                    const Icon = CHANNEL_ICONS[ch.channel] || Bell;
                                    return (
                                        <div key={ch.channel} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2">
                                            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                                                <Icon className="h-4 w-4 text-[var(--re-brand)] flex-shrink-0" />
                                                <div className="min-w-0">
                                                    <div className="text-sm font-medium capitalize">{ch.channel}</div>
                                                    {ch.target && <div className="text-[11px] sm:text-xs text-muted-foreground truncate">{ch.target}</div>}
                                                </div>
                                            </div>
                                            <Toggle enabled={ch.enabled} onToggle={() => toggleChannel(ch.channel)} />
                                        </div>
                                    );
                                })}
                            </CardContent>
                        </Card>

                        {/* Alert Rules */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Shield className="h-4 w-4 text-[var(--re-brand)]" />
                                    Alert Rules
                                </CardTitle>
                                <CardDescription>Enable or disable notifications for each rule</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {effectivePrefs.alert_preferences.map((alert) => (
                                    <div key={alert.rule_id} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2">
                                        <div className="min-w-0">
                                            <div className="text-xs sm:text-sm font-medium truncate">{alert.rule_name}</div>
                                            <div className="flex gap-1 mt-1 flex-wrap">
                                                {alert.channels.map(ch => (
                                                    <Badge key={ch} variant="outline" className="text-[9px] py-0">{ch}</Badge>
                                                ))}
                                                <Badge variant="outline" className="text-[9px] py-0">≥ {alert.min_severity}</Badge>
                                            </div>
                                        </div>
                                        <Toggle enabled={alert.enabled} onToggle={() => toggleAlert(alert.rule_id)} />
                                    </div>
                                ))}
                            </CardContent>
                        </Card>

                        {/* Quiet Hours & Digest */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Clock className="h-4 w-4 text-[var(--re-brand)]" />
                                    Schedule
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3 sm:space-y-4">
                                <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2">
                                    <div className="min-w-0">
                                        <div className="text-xs sm:text-sm font-medium">Quiet Hours</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground">
                                            Suppress non-critical {effectivePrefs.quiet_hours.start_hour}:00 – {effectivePrefs.quiet_hours.end_hour}:00
                                            {effectivePrefs.quiet_hours.override_critical && ' (critical bypass)'}
                                        </div>
                                    </div>
                                    <Toggle
                                        enabled={effectivePrefs.quiet_hours.enabled}
                                        onToggle={() => setLocalPrefs({ ...effectivePrefs, quiet_hours: { ...effectivePrefs.quiet_hours, enabled: !effectivePrefs.quiet_hours.enabled } })}
                                    />
                                </div>

                                <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2">
                                    <div className="min-w-0">
                                        <div className="text-xs sm:text-sm font-medium">Digest</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground">
                                            {effectivePrefs.digest_frequency} summary at {effectivePrefs.digest_time}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
                                        <select
                                            value={effectivePrefs.digest_frequency}
                                            onChange={e => setLocalPrefs({ ...effectivePrefs, digest_frequency: e.target.value })}
                                            className="text-xs rounded-lg border border-[var(--re-border-default)] bg-background px-2 py-1.5 min-h-[44px]"
                                        >
                                            <option value="daily">Daily</option>
                                            <option value="weekly">Weekly</option>
                                        </select>
                                        <Toggle
                                            enabled={effectivePrefs.digest_enabled}
                                            onToggle={() => setLocalPrefs({ ...effectivePrefs, digest_enabled: !effectivePrefs.digest_enabled })}
                                        />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Escalation */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <ArrowUp className="h-4 w-4 text-[var(--re-brand)]" />
                                    Escalation
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] min-h-[48px] gap-2">
                                    <div className="min-w-0">
                                        <div className="text-xs sm:text-sm font-medium">Auto-escalate unacknowledged alerts</div>
                                        <div className="text-[11px] sm:text-xs text-muted-foreground mt-1">
                                            If critical alert not acknowledged within {effectivePrefs.escalation.escalate_after_minutes} min
                                            {effectivePrefs.escalation.escalate_to && `, escalate to ${effectivePrefs.escalation.escalate_to}`}
                                        </div>
                                    </div>
                                    <Toggle
                                        enabled={effectivePrefs.escalation.enabled}
                                        onToggle={() => setLocalPrefs({ ...effectivePrefs, escalation: { ...effectivePrefs.escalation, enabled: !effectivePrefs.escalation.enabled } })}
                                    />
                                </div>
                            </CardContent>
                        </Card>
                    </>
                )}
            </div>
        </div>
    );
}
