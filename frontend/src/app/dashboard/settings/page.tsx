'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    AlertTriangle,
    Settings,
    Building2,
    Key,
    Database,
    Plug,
    Save,
    CheckCircle2,
    Copy,
    Eye,
    EyeOff,
    CreditCard,
    BarChart3,
} from 'lucide-react';

export default function SettingsPage() {
    const [saved, setSaved] = useState(false);
    const [showKey, setShowKey] = useState(false);
    const [activeTab, setActiveTab] = useState<'profile' | 'api' | 'retention' | 'integrations'>('profile');

    const [profile, setProfile] = useState({
        company_name: 'Acme Food Distribution',
        company_type: 'distributor',
        primary_contact: 'Jordan Smith',
        contact_email: 'jsmith@example.com',
        phone: '+1 (555) 012-3456',
        address: '123 Commerce Way, Salinas, CA 93901',
        fei_number: '',
    });

    const handleSave = () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const TABS = [
        { id: 'profile' as const, label: 'Company', icon: Building2 },
        { id: 'api' as const, label: 'API Keys', icon: Key },
        { id: 'retention' as const, label: 'Data Retention', icon: Database },
        { id: 'integrations' as const, label: 'Integrations', icon: Plug },
    ];

    const INTEGRATIONS = [
        { id: 'sensitech', name: 'Sensitech TempTale', category: 'IoT', status: 'connected' },
        { id: 'tive', name: 'Tive Trackers', category: 'IoT', status: 'disconnected' },
        { id: 'sap', name: 'SAP S/4HANA', category: 'ERP', status: 'disconnected' },
        { id: 'netsuite', name: 'Oracle NetSuite', category: 'ERP', status: 'disconnected' },
        { id: 'walmart', name: 'Walmart GDSN', category: 'Retailer', status: 'pending' },
        { id: 'kroger', name: 'Kroger 84.51°', category: 'Retailer', status: 'disconnected' },
    ];

    const STATUS_COLOR: Record<string, string> = {
        connected: '#10b981',
        pending: '#f59e0b',
        disconnected: '#6b7280',
    };

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Settings className="h-6 w-6 text-[var(--re-brand)]" />
                            Account Settings
                        </h1>
                    </div>
                    <Button onClick={handleSave} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                        {saved ? <><CheckCircle2 className="h-4 w-4 mr-1" /> Saved</> : <><Save className="h-4 w-4 mr-1" /> Save Changes</>}
                    </Button>
                </div>

                <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
                </div>

                {/* Plan Card */}
                <Card className="border-[var(--re-brand)] overflow-hidden">
                    <div className="h-1 bg-gradient-to-r from-[var(--re-brand)] to-blue-500" />
                    <CardContent className="py-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <CreditCard className="h-5 w-5 text-[var(--re-brand)]" />
                                <div>
                                    <span className="font-medium">Professional Plan</span>
                                    <span className="text-xs text-muted-foreground ml-2">$499/mo</span>
                                </div>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                <div className="flex items-center gap-1">
                                    <BarChart3 className="h-3 w-3" /> 2/5 facilities
                                </div>
                                <div>12,847/50K events</div>
                                <Button disabled title="Coming Soon" variant="outline" size="sm" className="rounded-xl text-xs">Manage Plan</Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Tabs */}
                <div className="flex gap-2">
                    {TABS.map((tab) => {
                        const Icon = tab.icon;
                        return (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium border transition-all ${activeTab === tab.id
                                        ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                        : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                    }`}
                            >
                                <Icon className="h-4 w-4" /> {tab.label}
                            </button>
                        );
                    })}
                </div>

                {/* Tab Content */}
                {activeTab === 'profile' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Company Profile</CardTitle>
                                <CardDescription>Your organization details for compliance records</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Company Name</label>
                                        <Input value={profile.company_name} onChange={e => setProfile({ ...profile, company_name: e.target.value })} className="rounded-xl" />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Type</label>
                                        <select value={profile.company_type} onChange={e => setProfile({ ...profile, company_type: e.target.value })} className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm">
                                            <option value="grower">Grower</option>
                                            <option value="manufacturer">Manufacturer</option>
                                            <option value="distributor">Distributor</option>
                                            <option value="retailer">Retailer</option>
                                            <option value="importer">Importer</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Primary Contact</label>
                                        <Input value={profile.primary_contact} onChange={e => setProfile({ ...profile, primary_contact: e.target.value })} className="rounded-xl" />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Email</label>
                                        <Input value={profile.contact_email} onChange={e => setProfile({ ...profile, contact_email: e.target.value })} className="rounded-xl" />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Phone</label>
                                        <Input value={profile.phone} onChange={e => setProfile({ ...profile, phone: e.target.value })} className="rounded-xl" />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">FDA FEI Number</label>
                                        <Input value={profile.fei_number} onChange={e => setProfile({ ...profile, fei_number: e.target.value })} placeholder="Optional" className="rounded-xl" />
                                    </div>
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">Address</label>
                                    <Input value={profile.address} onChange={e => setProfile({ ...profile, address: e.target.value })} className="rounded-xl" />
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {activeTab === 'api' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">API Keys</CardTitle>
                                <CardDescription>Manage your API access credentials</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {[
                                    { name: 'Production API Key', prefix: 'rge_prod_****', status: 'active' },
                                    { name: 'Development Key', prefix: 'rge_dev_****', status: 'active' },
                                ].map((key) => (
                                    <div key={key.name} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                        <div>
                                            <div className="text-sm font-medium">{key.name}</div>
                                            <div className="font-mono text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                                                {showKey ? 'rge_prod_a1b2c3d4e5f6' : key.prefix}
                                                <button onClick={() => setShowKey(!showKey)}>
                                                    {showKey ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                                </button>
                                                <button disabled title="Coming Soon"><Copy className="h-3 w-3" /></button>
                                            </div>
                                        </div>
                                        <Badge className="text-[9px] bg-emerald-500/10 text-emerald-500">{key.status}</Badge>
                                    </div>
                                ))}
                                <Button disabled title="Coming Soon" variant="outline" className="w-full rounded-xl">
                                    <Key className="h-4 w-4 mr-1" /> Generate New Key
                                </Button>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {activeTab === 'retention' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Data Retention</CardTitle>
                                <CardDescription>FSMA 204 requires minimum 2-year CTE retention</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {[
                                    { label: 'CTE Records', value: '3 years (1,095 days)', note: 'FSMA requires ≥ 2 years' },
                                    { label: 'Audit Log', value: '7 years (2,555 days)', note: 'Industry best practice' },
                                    { label: 'Exports', value: '1 year (365 days)', note: 'Download history' },
                                ].map((item) => (
                                    <div key={item.label} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                        <div>
                                            <div className="text-sm font-medium">{item.label}</div>
                                            <div className="text-xs text-muted-foreground">{item.note}</div>
                                        </div>
                                        <span className="text-sm font-medium text-[var(--re-brand)]">{item.value}</span>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {activeTab === 'integrations' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Integrations</CardTitle>
                                <CardDescription>Connect third-party systems</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {INTEGRATIONS.map((int) => (
                                    <div key={int.id} className="flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)]">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-sm font-medium">{int.name}</span>
                                                <Badge variant="outline" className="text-[9px] py-0">{int.category}</Badge>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <div className="w-2 h-2 rounded-full" style={{ background: STATUS_COLOR[int.status] }} />
                                            <span className="text-xs capitalize" style={{ color: STATUS_COLOR[int.status] }}>{int.status}</span>
                                            {int.status === 'disconnected' && (
                                                <Button disabled title="Coming Soon" variant="outline" size="sm" className="rounded-xl text-xs ml-2">Connect</Button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </div>
        </div>
    );
}
