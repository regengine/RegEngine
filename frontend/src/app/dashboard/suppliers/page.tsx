'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    Users,
    Link2,
    Send,
    CheckCircle2,
    AlertTriangle,
    XCircle,
    Clock,
    Plus,
    Package,
    Activity,
    Mail,
} from 'lucide-react';

interface Supplier {
    id: string;
    name: string;
    email: string;
    portalStatus: 'active' | 'expired' | 'no_link';
    submissions: number;
    lastSubmission: string | null;
    compliance: 'compliant' | 'partial' | 'non_compliant';
    products: string[];
}

const SUPPLIERS: Supplier[] = [
    {
        id: 'sup-001', name: 'Valley Fresh Farms', email: 'ops@valleyfresh.com',
        portalStatus: 'active' as const, submissions: 12, lastSubmission: '6 hours ago',
        compliance: 'compliant' as const, products: ['Romaine Lettuce', 'Roma Tomatoes'],
    },
    {
        id: 'sup-002', name: 'Pacific Seafood Inc.', email: 'trace@pacseafood.com',
        portalStatus: 'active' as const, submissions: 8, lastSubmission: '2 days ago',
        compliance: 'compliant' as const, products: ['Atlantic Salmon', 'Pacific Cod'],
    },
    {
        id: 'sup-003', name: 'Sunrise Produce Co.', email: 'quality@sunriseproduce.com',
        portalStatus: 'expired' as const, submissions: 3, lastSubmission: '35 days ago',
        compliance: 'partial' as const, products: ['English Cucumbers'],
    },
    {
        id: 'sup-004', name: 'Green Valley Organics', email: 'farm@greenvalley.org',
        portalStatus: 'no_link' as const, submissions: 0, lastSubmission: null,
        compliance: 'non_compliant' as const, products: ['Mixed Salad Greens'],
    },
    {
        id: 'sup-005', name: 'Cold Express Logistics', email: 'dispatch@coldexpress.com',
        portalStatus: 'active' as const, submissions: 22, lastSubmission: '1 hour ago',
        compliance: 'compliant' as const, products: ['3PL — Temperature Monitoring'],
    },
];

const COMPLIANCE_CONFIG = {
    compliant: { color: '#10b981', bg: 'rgba(16,185,129,0.08)', label: 'Compliant', icon: CheckCircle2 },
    partial: { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', label: 'Partial', icon: AlertTriangle },
    non_compliant: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', label: 'Non-Compliant', icon: XCircle },
};

const PORTAL_CONFIG = {
    active: { color: '#10b981', label: 'Active' },
    expired: { color: '#ef4444', label: 'Expired' },
    no_link: { color: '#6b7280', label: 'No Link' },
};

export default function SupplierDashboardPage() {
    const [showAddForm, setShowAddForm] = useState(false);
    const [newName, setNewName] = useState('');
    const [newEmail, setNewEmail] = useState('');
    const [suppliers, setSuppliers] = useState(SUPPLIERS);

    const activeLinks = suppliers.filter(s => s.portalStatus === 'active').length;
    const compliantCount = suppliers.filter(s => s.compliance === 'compliant').length;
    const totalSubs = suppliers.reduce((s, sup) => s + sup.submissions, 0);
    const complianceRate = Math.round((compliantCount / suppliers.length) * 100);

    const handleAdd = () => {
        if (!newName || !newEmail) return;
        const newSup: typeof SUPPLIERS[number] = {
            id: `sup-new-${Date.now()}`,
            name: newName,
            email: newEmail,
            portalStatus: 'no_link',
            submissions: 0,
            lastSubmission: null,
            compliance: 'non_compliant',
            products: [],
        };
        setSuppliers([...suppliers, newSup]);
        setNewName('');
        setNewEmail('');
        setShowAddForm(false);
    };

    const handleSendLink = (supplierId: string) => {
        setSuppliers(prev => prev.map(s =>
            s.id === supplierId ? { ...s, portalStatus: 'active' as const } : s
        ));
    };

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Users className="h-6 w-6 text-[var(--re-brand)]" />
                            Supplier Management
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Track portal links, submissions & compliance across your supply chain
                        </p>
                    </div>
                    <Button onClick={() => setShowAddForm(!showAddForm)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                        <Plus className="h-4 w-4 mr-1" /> Add Supplier
                    </Button>
                </div>

                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                        { label: 'Total Suppliers', value: suppliers.length, icon: Users },
                        { label: 'Active Portal Links', value: activeLinks, icon: Link2 },
                        { label: 'Total Submissions', value: totalSubs, icon: Package },
                        { label: 'Compliance Rate', value: `${complianceRate}%`, icon: Activity },
                    ].map((stat) => (
                        <Card key={stat.label} className="border-[var(--re-border-default)]">
                            <CardContent className="py-4">
                                <div className="flex items-center gap-2 mb-1">
                                    <stat.icon className="h-4 w-4 text-[var(--re-brand)]" />
                                    <span className="text-xs text-muted-foreground">{stat.label}</span>
                                </div>
                                <div className="text-2xl font-bold">{stat.value}</div>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                {/* Add Form */}
                {showAddForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                        <Card className="border-[var(--re-brand)]">
                            <CardContent className="py-4">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Supplier name" className="rounded-xl" />
                                    <Input value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="Contact email" type="email" className="rounded-xl" />
                                    <Button onClick={handleAdd} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                                        <Plus className="h-4 w-4 mr-1" /> Add
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Supplier List */}
                <div className="space-y-3">
                    {suppliers.map((supplier, i) => {
                        const compConfig = COMPLIANCE_CONFIG[supplier.compliance];
                        const portalConfig = PORTAL_CONFIG[supplier.portalStatus];
                        const CompIcon = compConfig.icon;

                        return (
                            <motion.div key={supplier.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                                <Card className="border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all">
                                    <CardContent className="py-4">
                                        <div className="flex items-center justify-between flex-wrap gap-3">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="font-medium">{supplier.name}</span>
                                                    <Badge className="text-[9px] px-1.5 py-0" style={{ background: compConfig.bg, color: compConfig.color }}>
                                                        <CompIcon className="h-2.5 w-2.5 mr-0.5 inline" />
                                                        {compConfig.label}
                                                    </Badge>
                                                    <Badge className="text-[9px] px-1.5 py-0" variant="outline" style={{ color: portalConfig.color, borderColor: portalConfig.color }}>
                                                        <Link2 className="h-2.5 w-2.5 mr-0.5 inline" />
                                                        {portalConfig.label}
                                                    </Badge>
                                                </div>
                                                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                                    <span className="flex items-center gap-1"><Mail className="h-3 w-3" /> {supplier.email}</span>
                                                    <span>{supplier.submissions} submissions</span>
                                                    {supplier.lastSubmission && (
                                                        <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {supplier.lastSubmission}</span>
                                                    )}
                                                </div>
                                                {supplier.products.length > 0 && (
                                                    <div className="flex gap-1 mt-2">
                                                        {supplier.products.map((p) => (
                                                            <Badge key={p} variant="outline" className="text-[9px] py-0">{p}</Badge>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                            {supplier.portalStatus !== 'active' && (
                                                <Button variant="outline" size="sm" className="rounded-xl flex-shrink-0" onClick={() => handleSendLink(supplier.id)}>
                                                    <Send className="h-3 w-3 mr-1" />
                                                    {supplier.portalStatus === 'expired' ? 'Resend Link' : 'Send Link'}
                                                </Button>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
