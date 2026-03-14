'use client';

import { motion } from 'framer-motion';
import { AlertTriangle, Users, Search, Plus, Filter } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

const mockTenants = [
    { id: '1', name: 'Acme Foods Inc.', plan: 'Enterprise', status: 'active', mrr: 12500, documents: 2340, users: 24, createdAt: '2024-01-15' },
    { id: '2', name: 'FreshLeaf Produce', plan: 'Scale', status: 'active', mrr: 4999, documents: 890, users: 8, createdAt: '2024-02-20' },
    { id: '3', name: 'Northstar Cold Chain', plan: 'Enterprise', status: 'active', mrr: 15000, documents: 4200, users: 45, createdAt: '2023-11-10' },
    { id: '4', name: 'Riverbend Packers', plan: 'Growth', status: 'trial', mrr: 0, documents: 45, users: 2, createdAt: '2024-03-01' },
    { id: '5', name: 'Harvest Table Foods', plan: 'Scale', status: 'active', mrr: 4999, documents: 1200, users: 12, createdAt: '2024-01-28' },
    { id: '6', name: 'Blue Harbor Seafood', plan: 'Enterprise', status: 'active', mrr: 25000, documents: 8900, users: 67, createdAt: '2023-08-05' },
    { id: '7', name: 'Summit Fresh Logistics', plan: 'Scale', status: 'churned', mrr: 0, documents: 560, users: 5, createdAt: '2023-12-01' },
];

function formatCurrency(num: number): string {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(num);
}

export default function TenantsPage() {
    return (
        <div className="p-8">
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white">Tenant Management</h1>
                    <p className="text-white/60 mt-1">Manage all customer accounts and subscriptions</p>
                </div>
                <Button className="bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white">
                    <Plus className="h-4 w-4 mr-2" />
                    Add Tenant
                </Button>
            </motion.div>

            <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
            </div>

            {/* Search and Filters */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="flex gap-4 mb-6"
            >
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                    <Input
                        placeholder="Search tenants..."
                        className="pl-10 bg-white/5 border-white/10 text-white placeholder:text-white/40"
                    />
                </div>
                <Button variant="outline" className="bg-white/5 border-white/10 text-white hover:bg-white/10">
                    <Filter className="h-4 w-4 mr-2" />
                    Filters
                </Button>
            </motion.div>

            {/* Tenants Table */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
            >
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardContent className="p-0">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-white/10">
                                    <th className="text-left p-4 text-white/60 font-medium">Tenant</th>
                                    <th className="text-left p-4 text-white/60 font-medium">Plan</th>
                                    <th className="text-left p-4 text-white/60 font-medium">Status</th>
                                    <th className="text-right p-4 text-white/60 font-medium">MRR</th>
                                    <th className="text-right p-4 text-white/60 font-medium">Documents</th>
                                    <th className="text-right p-4 text-white/60 font-medium">Users</th>
                                    <th className="text-right p-4 text-white/60 font-medium">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {mockTenants.map((tenant) => (
                                    <tr key={tenant.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                                        <td className="p-4">
                                            <div className="flex items-center gap-3">
                                                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-500/20 to-orange-600/20 flex items-center justify-center">
                                                    <span className="text-amber-400 font-bold">{tenant.name[0]}</span>
                                                </div>
                                                <div>
                                                    <p className="font-medium text-white">{tenant.name}</p>
                                                    <p className="text-xs text-white/40">Since {tenant.createdAt}</p>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="p-4">
                                            <Badge variant="outline" className="bg-white/5 border-white/20 text-white/80">
                                                {tenant.plan}
                                            </Badge>
                                        </td>
                                        <td className="p-4">
                                            <Badge className={
                                                tenant.status === 'active' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
                                                    tenant.status === 'trial' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                                                        'bg-slate-500/20 text-slate-400 border-slate-500/30'
                                            }>
                                                {tenant.status}
                                            </Badge>
                                        </td>
                                        <td className="p-4 text-right text-white font-medium">{formatCurrency(tenant.mrr)}</td>
                                        <td className="p-4 text-right text-white/60">{tenant.documents.toLocaleString()}</td>
                                        <td className="p-4 text-right text-white/60">{tenant.users}</td>
                                        <td className="p-4 text-right">
                                            <Button variant="ghost" size="sm" className="text-amber-400 hover:text-amber-300 hover:bg-white/5">
                                                Manage
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
