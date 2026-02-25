'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
} from 'lucide-react';

interface Channel {
    id: string;
    name: string;
    icon: typeof Mail;
    enabled: boolean;
    target: string;
}

interface AlertPref {
    ruleId: string;
    name: string;
    enabled: boolean;
    channels: string[];
}

const INITIAL_CHANNELS: Channel[] = [
    { id: 'email', name: 'Email', icon: Mail, enabled: true, target: 'compliance@example.com' },
    { id: 'slack', name: 'Slack', icon: MessageSquare, enabled: false, target: '#compliance-alerts' },
    { id: 'webhook', name: 'Webhook', icon: Webhook, enabled: false, target: '' },
    { id: 'sms', name: 'SMS', icon: Smartphone, enabled: false, target: '' },
];

const INITIAL_ALERTS: AlertPref[] = [
    { ruleId: 'kde-missing', name: 'Missing Key Data Elements', enabled: true, channels: ['email'] },
    { ruleId: 'cte-overdue', name: 'Overdue CTE Entry', enabled: true, channels: ['email'] },
    { ruleId: 'temp-excursion', name: 'Temperature Excursion', enabled: true, channels: ['email', 'slack'] },
    { ruleId: 'chain-integrity', name: 'Hash Chain Break', enabled: true, channels: ['email', 'slack'] },
    { ruleId: 'portal-expiry', name: 'Supplier Portal Expiring', enabled: true, channels: ['email'] },
    { ruleId: 'fda-deadline', name: 'FDA Records Deadline', enabled: true, channels: ['email', 'slack', 'sms'] },
    { ruleId: 'compliance-drop', name: 'Compliance Score Drop', enabled: true, channels: ['email'] },
    { ruleId: 'event-volume-spike', name: 'Event Volume Anomaly', enabled: false, channels: ['email'] },
];

export default function NotificationPrefsPage() {
    const [channels, setChannels] = useState(INITIAL_CHANNELS);
    const [alerts, setAlerts] = useState(INITIAL_ALERTS);
    const [quietHours, setQuietHours] = useState(false);
    const [digest, setDigest] = useState(true);
    const [digestFreq, setDigestFreq] = useState('daily');
    const [saved, setSaved] = useState(false);

    const toggleChannel = (id: string) => {
        setChannels(prev => prev.map(c => c.id === id ? { ...c, enabled: !c.enabled } : c));
    };

    const toggleAlert = (ruleId: string) => {
        setAlerts(prev => prev.map(a => a.ruleId === ruleId ? { ...a, enabled: !a.enabled } : a));
    };

    const handleSave = () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
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
                    <Button onClick={handleSave} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                        {saved ? '✓ Saved' : 'Save Changes'}
                    </Button>
                </div>

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
                        {channels.map((ch) => {
                            const Icon = ch.icon;
                            return (
                                <div key={ch.id} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                    <div className="flex items-center gap-3">
                                        <Icon className="h-4 w-4 text-[var(--re-brand)]" />
                                        <div>
                                            <div className="text-sm font-medium">{ch.name}</div>
                                            {ch.target && <div className="text-xs text-muted-foreground">{ch.target}</div>}
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => toggleChannel(ch.id)}
                                        className={`relative w-11 h-6 rounded-full transition-all ${ch.enabled ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-elevated)]'
                                            }`}
                                    >
                                        <motion.div
                                            className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow"
                                            animate={{ left: ch.enabled ? 22 : 2 }}
                                            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                                        />
                                    </button>
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
                        {alerts.map((alert) => (
                            <div key={alert.ruleId} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                <div>
                                    <div className="text-sm font-medium">{alert.name}</div>
                                    <div className="flex gap-1 mt-1">
                                        {alert.channels.map(ch => (
                                            <Badge key={ch} variant="outline" className="text-[9px] py-0">{ch}</Badge>
                                        ))}
                                    </div>
                                </div>
                                <button
                                    onClick={() => toggleAlert(alert.ruleId)}
                                    className={`relative w-11 h-6 rounded-full transition-all ${alert.enabled ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-elevated)]'
                                        }`}
                                >
                                    <motion.div
                                        className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow"
                                        animate={{ left: alert.enabled ? 22 : 2 }}
                                        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                                    />
                                </button>
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
                                <div className="text-xs text-muted-foreground">Suppress non-critical alerts 10 PM – 7 AM</div>
                            </div>
                            <button
                                onClick={() => setQuietHours(!quietHours)}
                                className={`relative w-11 h-6 rounded-full transition-all ${quietHours ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-elevated)]'
                                    }`}
                            >
                                <motion.div
                                    className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow"
                                    animate={{ left: quietHours ? 22 : 2 }}
                                    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                                />
                            </button>
                        </div>

                        <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                            <div>
                                <div className="text-sm font-medium">Daily Digest</div>
                                <div className="text-xs text-muted-foreground">Summary email at 8:00 AM</div>
                            </div>
                            <div className="flex items-center gap-3">
                                <select value={digestFreq} onChange={e => setDigestFreq(e.target.value)}
                                    className="text-xs rounded-lg border border-[var(--re-border-default)] bg-background px-2 py-1">
                                    <option value="daily">Daily</option>
                                    <option value="weekly">Weekly</option>
                                </select>
                                <button
                                    onClick={() => setDigest(!digest)}
                                    className={`relative w-11 h-6 rounded-full transition-all ${digest ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-elevated)]'
                                        }`}
                                >
                                    <motion.div
                                        className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow"
                                        animate={{ left: digest ? 22 : 2 }}
                                        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                                    />
                                </button>
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
                        <div className="p-3 rounded-xl border border-[var(--re-border-default)]">
                            <div className="text-sm font-medium">Auto-escalate unacknowledged alerts</div>
                            <div className="text-xs text-muted-foreground mt-1">
                                If a critical alert isn&apos;t acknowledged within 60 minutes, escalate to manager@example.com
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
