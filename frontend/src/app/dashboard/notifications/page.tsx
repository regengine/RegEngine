'use client';

import React, { useState, useEffect, useCallback } from 'react';
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

async function apiFetchPrefs(tenantId: string): Promise<NotificationPreferences> {
    const apiKey = typeof window !== 'undefined' ? localStorage.getItem('re-api-key') || '' : '';
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/notifications/${tenantId}/preferences`, {
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiSavePrefs(tenantId: string, prefs: Partial<NotificationPreferences>): Promise<void> {
    const apiKey = typeof window !== 'undefined' ? localStorage.getItem('re-api-key') || '' : '';
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
            className={`relative w-11 h-6 rounded-full transition-all ${enabled ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-elevated)]'}`}
        >
            <motion.div
                className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow"
                animate={{ left: enabled ? 22 : 2 }}
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            />
        </button>
    );
}

export default function NotificationPrefsPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = Boolean(apiKey);

    const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);

    const loadPrefs = useCallback(async () => {
        if (!isLoggedIn || !tenantId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await apiFetchPrefs(tenantId);
            setPrefs(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load preferences');
        } finally {
            setLoading(false);
        }
    }, [isLoggedIn, tenantId]);

    useEffect(() => { loadPrefs(); }, [loadPrefs]);

    const toggleChannel = (channelName: string) => {
        if (!prefs) return;
        setPrefs({
            ...prefs,
            channels: prefs.channels.map(c => c.channel === channelName ? { ...c, enabled: !c.enabled } : c),
        });
    };

    const toggleAlert = (ruleId: string) => {
        if (!prefs) return;
        setPrefs({
            ...prefs,
            alert_preferences: prefs.alert_preferences.map(a => a.rule_id === ruleId ? { ...a, enabled: !a.enabled } : a),
        });
    };

    const handleSave = async () => {
        if (!prefs || !tenantId) return;
        setSaving(true);
        try {
            await apiSavePrefs(tenantId, prefs);
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save preferences');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-3xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Settings className="h-6 w-6 text-[var(--re-brand)]" />
                            Notification Preferences
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Configure how and when you receive compliance alerts
                        </p>
                    </div>
                    <Button onClick={handleSave} disabled={saving || !prefs} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                        {saving ? <Spinner size="sm" /> : saved ? '✓ Saved' : 'Save Changes'}
                    </Button>
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

                {error && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <p className="text-sm">{error}</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {prefs && !loading && (
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
                            <CardContent className="space-y-3">
                                {prefs.channels.map((ch) => {
                                    const Icon = CHANNEL_ICONS[ch.channel] || Bell;
                                    return (
                                        <div key={ch.channel} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                            <div className="flex items-center gap-3">
                                                <Icon className="h-4 w-4 text-[var(--re-brand)]" />
                                                <div>
                                                    <div className="text-sm font-medium capitalize">{ch.channel}</div>
                                                    {ch.target && <div className="text-xs text-muted-foreground">{ch.target}</div>}
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
                                {prefs.alert_preferences.map((alert) => (
                                    <div key={alert.rule_id} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                        <div>
                                            <div className="text-sm font-medium">{alert.rule_name}</div>
                                            <div className="flex gap-1 mt-1">
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
                            <CardContent className="space-y-4">
                                <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                    <div>
                                        <div className="text-sm font-medium">Quiet Hours</div>
                                        <div className="text-xs text-muted-foreground">
                                            Suppress non-critical alerts {prefs.quiet_hours.start_hour}:00 – {prefs.quiet_hours.end_hour}:00
                                            {prefs.quiet_hours.override_critical && ' (critical alerts bypass)'}
                                        </div>
                                    </div>
                                    <Toggle
                                        enabled={prefs.quiet_hours.enabled}
                                        onToggle={() => setPrefs({ ...prefs, quiet_hours: { ...prefs.quiet_hours, enabled: !prefs.quiet_hours.enabled } })}
                                    />
                                </div>

                                <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                    <div>
                                        <div className="text-sm font-medium">Digest</div>
                                        <div className="text-xs text-muted-foreground">
                                            {prefs.digest_frequency} summary at {prefs.digest_time}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <select
                                            value={prefs.digest_frequency}
                                            onChange={e => setPrefs({ ...prefs, digest_frequency: e.target.value })}
                                            className="text-xs rounded-lg border border-[var(--re-border-default)] bg-background px-2 py-1"
                                        >
                                            <option value="daily">Daily</option>
                                            <option value="weekly">Weekly</option>
                                        </select>
                                        <Toggle
                                            enabled={prefs.digest_enabled}
                                            onToggle={() => setPrefs({ ...prefs, digest_enabled: !prefs.digest_enabled })}
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
                                <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                    <div>
                                        <div className="text-sm font-medium">Auto-escalate unacknowledged alerts</div>
                                        <div className="text-xs text-muted-foreground mt-1">
                                            If a critical alert isn&apos;t acknowledged within {prefs.escalation.escalate_after_minutes} minutes
                                            {prefs.escalation.escalate_to && `, escalate to ${prefs.escalation.escalate_to}`}
                                        </div>
                                    </div>
                                    <Toggle
                                        enabled={prefs.escalation.enabled}
                                        onToggle={() => setPrefs({ ...prefs, escalation: { ...prefs.escalation, enabled: !prefs.escalation.enabled } })}
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
