'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
    DollarSign,
    Users,
    FileText,
    Activity,
    TrendingUp,
    TrendingDown,
    ArrowUpRight,
    Clock,
    CheckCircle,
    AlertTriangle,
    XCircle,
    RefreshCw,
    MoreHorizontal,
    Eye,
    Trash2,
    Sparkles,
    Mail,
    ShieldAlert,
    Settings
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';

// Mock data for demo
const mockKPIs = {
    mrr: { value: 127500, change: 12.5, trend: 'up' },
    tenants: { value: 47, change: 8, trend: 'up' },
    documents: { value: 15420, change: 23.1, trend: 'up' },
    apiCalls: { value: 2340000, change: -2.3, trend: 'down' },
};

const mockTenants = [
    { id: '1', name: 'Acme Foods Inc.', plan: 'Enterprise', status: 'active', mrr: 12500, documents: 2340, lastActive: '2 hours ago' },
    { id: '2', name: 'GlobalTech Solutions', plan: 'Professional', status: 'active', mrr: 4999, documents: 890, lastActive: '5 mins ago' },
    { id: '3', name: 'MedSecure Health', plan: 'Enterprise', status: 'active', mrr: 15000, documents: 4200, lastActive: '1 hour ago' },
    { id: '4', name: 'EnergyFlow Corp', plan: 'Starter', status: 'trial', mrr: 0, documents: 45, lastActive: '3 days ago' },
    { id: '5', name: 'SafetyFirst Manufacturing', plan: 'Professional', status: 'active', mrr: 4999, documents: 1200, lastActive: '12 mins ago' },
];

const mockAuditLog = [
    { id: '1', action: 'API Key Created', user: 'admin@regengine.co', target: 'Production Key', time: '5 mins ago', type: 'key' },
    { id: '2', action: 'Tenant Created', user: 'owner@regengine.co', target: 'EnergyFlow Corp', time: '2 hours ago', type: 'tenant' },
    { id: '3', action: 'User Login', user: 'admin@regengine.co', target: 'Admin Console', time: '3 hours ago', type: 'auth' },
    { id: '4', action: 'API Key Revoked', user: 'admin@regengine.co', target: 'Legacy Key #4', time: '1 day ago', type: 'key' },
    { id: '5', action: 'Plan Upgraded', user: 'owner@regengine.co', target: 'MedSecure Health', time: '2 days ago', type: 'billing' },
];

const mockServices = [
    { name: 'Admin API', status: 'healthy', statusLabel: 'Operational' },
    { name: 'Ingestion Service', status: 'healthy', statusLabel: 'Operational' },
    { name: 'NLP Engine', status: 'healthy', statusLabel: 'Operational' },
    { name: 'Graph Database', status: 'healthy', statusLabel: 'Operational' },
];

function formatNumber(num: number): string {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
}

function formatCurrency(num: number): string {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(num);
}

interface KPICardProps {
    title: string;
    value: string;
    change: number;
    trend: 'up' | 'down';
    icon: React.ElementType;
    delay?: number;
}

function KPICard({ title, value, change, trend, icon: Icon, delay = 0 }: KPICardProps) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay, duration: 0.4 }}
        >
            <Card className="bg-white/5 backdrop-blur-xl border-white/10 hover:bg-white/10 transition-all duration-300 group">
                <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                        <div>
                            <p className="text-sm text-white/60 mb-1">{title}</p>
                            <p className="text-3xl font-bold text-white">{value}</p>
                            <div className={cn(
                                'flex items-center gap-1 mt-2 text-sm font-medium',
                                trend === 'up' ? 'text-emerald-400' : 'text-red-400'
                            )}>
                                {trend === 'up' ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                                <span>{Math.abs(change)}%</span>
                                <span className="text-white/40 ml-1">vs last month</span>
                            </div>
                        </div>
                        <div className={cn(
                            'p-3 rounded-xl transition-all duration-300',
                            'bg-gradient-to-br from-amber-500/20 to-orange-600/20',
                            'group-hover:from-amber-500/30 group-hover:to-orange-600/30'
                        )}>
                            <Icon className="h-6 w-6 text-amber-400" />
                        </div>
                    </div>
                </CardContent>
            </Card>
        </motion.div>
    );
}

function StatusBadge({ status }: { status: string }) {
    const variants: Record<string, { class: string; icon: React.ElementType }> = {
        healthy: { class: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', icon: CheckCircle },
        warning: { class: 'bg-amber-500/20 text-amber-400 border-amber-500/30', icon: AlertTriangle },
        error: { class: 'bg-red-500/20 text-red-400 border-red-500/30', icon: XCircle },
        active: { class: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', icon: CheckCircle },
        trial: { class: 'bg-blue-500/20 text-blue-400 border-blue-500/30', icon: Clock },
        churned: { class: 'bg-slate-500/20 text-slate-400 border-slate-500/30', icon: XCircle },
    };

    const variant = variants[status] || variants.active;
    const Icon = variant.icon;

    return (
        <Badge className={cn('border', variant.class)}>
            <Icon className="h-3 w-3 mr-1" />
            {status}
        </Badge>
    );
}

export default function OwnerDashboard() {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const { user, isHydrated } = useAuth();
    const router = useRouter();
    const [isAuthorized, setIsAuthorized] = useState(false);

    useEffect(() => {
        if (!isHydrated) return;

        // SEC-006 Mitigation: Restrict to explicit owner emails
        const AUTHORIZED_EMAILS = ['owner@regengine.co', 'chris.sellers@regengine.co'];

        if (!user || !user.email || !AUTHORIZED_EMAILS.includes(user.email)) {
            console.warn('[SECURITY] Unauthorized access attempt to Executive Dashboard');
            router.push('/tools');
        } else {
            setIsAuthorized(true);
        }
    }, [user, isHydrated, router]);

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1500);
    };

    if (!isHydrated || !isAuthorized) {
        return (
            <div className="min-h-screen bg-[#06090f] flex items-center justify-center">
                <div className="animate-pulse flex flex-col items-center">
                    <ShieldAlert className="h-10 w-10 text-[var(--re-brand)] mb-4" />
                    <p className="text-[var(--re-text-muted)] tracking-widest uppercase text-sm">Verifying Executive Clearance...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#06090f] p-8 text-slate-200">
            {/* Header */}
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white tracking-tight">Executive Dashboard</h1>
                    <p className="text-slate-400 mt-1">Welcome back. Here&apos;s your business overview.</p>
                </div>
                <Button
                    onClick={handleRefresh}
                    variant="outline"
                    className="bg-white/5 border-white/10 text-slate-300 hover:bg-white/10 hover:text-white transition-colors"
                >
                    <RefreshCw className={cn('h-4 w-4 mr-2', isRefreshing && 'animate-spin')} />
                    Refresh
                </Button>
            </motion.div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                <KPICard
                    title="Monthly Recurring Revenue"
                    value={formatCurrency(mockKPIs.mrr.value)}
                    change={mockKPIs.mrr.change}
                    trend={mockKPIs.mrr.trend as 'up' | 'down'}
                    icon={DollarSign}
                    delay={0}
                />
                <KPICard
                    title="Active Tenants"
                    value={mockKPIs.tenants.value.toString()}
                    change={mockKPIs.tenants.change}
                    trend={mockKPIs.tenants.trend as 'up' | 'down'}
                    icon={Users}
                    delay={0.1}
                />
                <KPICard
                    title="Documents Processed"
                    value={formatNumber(mockKPIs.documents.value)}
                    change={mockKPIs.documents.change}
                    trend={mockKPIs.documents.trend as 'up' | 'down'}
                    icon={FileText}
                    delay={0.2}
                />
                <KPICard
                    title="API Calls (30d)"
                    value={formatNumber(mockKPIs.apiCalls.value)}
                    change={mockKPIs.apiCalls.change}
                    trend={mockKPIs.apiCalls.trend as 'up' | 'down'}
                    icon={Activity}
                    delay={0.3}
                />
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Tenant Table */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 }}
                    className="lg:col-span-2"
                >
                    <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                        <CardHeader className="border-b border-white/10">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-white">Top Tenants</CardTitle>
                                    <CardDescription className="text-white/60">Your highest-value customers</CardDescription>
                                </div>
                                <Button variant="ghost" size="sm" className="text-amber-400 hover:text-amber-300 hover:bg-white/5">
                                    View All <ArrowUpRight className="h-4 w-4 ml-1" />
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="divide-y divide-white/10">
                                {mockTenants.map((tenant) => (
                                    <div key={tenant.id} className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors">
                                        <div className="flex items-center gap-4">
                                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-amber-500/20 to-orange-600/20 flex items-center justify-center">
                                                <span className="text-amber-400 font-bold">{tenant.name[0]}</span>
                                            </div>
                                            <div>
                                                <p className="font-medium text-white">{tenant.name}</p>
                                                <div className="flex items-center gap-2 mt-0.5">
                                                    <Badge variant="outline" className="bg-white/5 border-white/20 text-white/60 text-xs">
                                                        {tenant.plan}
                                                    </Badge>
                                                    <span className="text-xs text-white/40">{tenant.documents} docs</span>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <div className="text-right">
                                                <p className="font-semibold text-white">{formatCurrency(tenant.mrr)}</p>
                                                <p className="text-xs text-white/40">{tenant.lastActive}</p>
                                            </div>
                                            <StatusBadge status={tenant.status} />
                                            <Button variant="ghost" size="icon" className="text-white/40 hover:text-white hover:bg-white/10">
                                                <MoreHorizontal className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Right Column */}
                <div className="space-y-6">
                    {/* System Health */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.5 }}
                    >
                        <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                            <CardHeader className="border-b border-white/10">
                                <CardTitle className="text-white">System Health</CardTitle>
                            </CardHeader>
                            <CardContent className="p-4">
                                <div className="space-y-3">
                                    {mockServices.map((service) => (
                                        <div key={service.name} className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <div className={cn(
                                                    'w-2 h-2 rounded-full',
                                                    service.status === 'healthy' ? 'bg-emerald-400' :
                                                        service.status === 'warning' ? 'bg-amber-400' : 'bg-red-400'
                                                )} />
                                                <span className="text-white/80 text-sm">{service.name}</span>
                                            </div>
                                            <span className="text-emerald-400 text-sm">{service.statusLabel}</span>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>

                    {/* Audit Log */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.6 }}
                    >
                        <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                            <CardHeader className="border-b border-white/10">
                                <div className="flex items-center justify-between">
                                    <CardTitle className="text-white">Recent Activity</CardTitle>
                                    <Button variant="ghost" size="sm" className="text-amber-400 hover:text-amber-300 hover:bg-white/5">
                                        View All
                                    </Button>
                                </div>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="divide-y divide-white/10">
                                    {mockAuditLog.slice(0, 4).map((log) => (
                                        <div key={log.id} className="p-3 hover:bg-white/5 transition-colors">
                                            <div className="flex items-start gap-3">
                                                <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center mt-0.5">
                                                    {log.type === 'key' && <Settings className="h-4 w-4 text-amber-400" />}
                                                    {log.type === 'tenant' && <Users className="h-4 w-4 text-blue-400" />}
                                                    {log.type === 'auth' && <Eye className="h-4 w-4 text-emerald-400" />}
                                                    {log.type === 'billing' && <DollarSign className="h-4 w-4 text-purple-400" />}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm text-white font-medium">{log.action}</p>
                                                    <p className="text-xs text-white/40 truncate">{log.target}</p>
                                                </div>
                                                <span className="text-xs text-white/40 whitespace-nowrap">{log.time}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                </div>
            </div>

            {/* Alpha Waitlist Pipeline */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7 }}
                className="mt-8"
            >
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader className="border-b border-white/10">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-white flex items-center gap-2">
                                    <Sparkles className="h-5 w-5 text-purple-400" />
                                    Alpha Waitlist Pipeline
                                </CardTitle>
                                <CardDescription className="text-white/60">Track signups from /alpha</CardDescription>
                            </div>
                            <div className="flex items-center gap-3">
                                <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 border">
                                    12 total signups
                                </Badge>
                                <Button variant="ghost" size="sm" className="text-amber-400 hover:text-amber-300 hover:bg-white/5">
                                    Export CSV <ArrowUpRight className="h-4 w-4 ml-1" />
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="p-6">
                        {/* Pipeline Stats */}
                        <div className="grid grid-cols-4 gap-4 mb-6">
                            {[
                                { label: 'Pending', count: 7, color: 'text-blue-400', bg: 'bg-blue-500/20' },
                                { label: 'Contacted', count: 3, color: 'text-amber-400', bg: 'bg-amber-500/20' },
                                { label: 'Accepted', count: 2, color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
                                { label: 'Declined', count: 0, color: 'text-red-400', bg: 'bg-red-500/20' },
                            ].map((stage) => (
                                <div key={stage.label} className="text-center">
                                    <div className={cn('text-2xl font-bold', stage.color)}>{stage.count}</div>
                                    <div className="text-xs text-white/40 mt-1">{stage.label}</div>
                                </div>
                            ))}
                        </div>

                        {/* Recent Signups */}
                        <div className="divide-y divide-white/10 border border-white/10 rounded-lg overflow-hidden">
                            {[
                                { email: 'sarah@freshleaf.co', company: 'FreshLeaf Produce', role: 'VP Compliance', time: '2 hours ago', status: 'pending' },
                                { email: 'michael@seastar.com', company: 'SeaStar Foods', role: 'Quality Manager', time: '5 hours ago', status: 'contacted' },
                                { email: 'james@puremart.io', company: 'PureMart Inc.', role: 'Supply Chain Director', time: '1 day ago', status: 'accepted' },
                                { email: 'ana@greenvalley.com', company: 'Green Valley Farms', role: 'Operations', time: '1 day ago', status: 'pending' },
                                { email: 'david@oceancatch.net', company: 'OceanCatch Seafood', role: 'Founder / CEO', time: '2 days ago', status: 'accepted' },
                            ].map((signup, i) => (
                                <div key={i} className="p-3 flex items-center justify-between hover:bg-white/5 transition-colors">
                                    <div className="flex items-center gap-4">
                                        <div className="w-8 h-8 rounded-full bg-purple-500/20 flex items-center justify-center">
                                            <Mail className="h-4 w-4 text-purple-400" />
                                        </div>
                                        <div>
                                            <p className="text-sm text-white font-medium">{signup.email}</p>
                                            <div className="flex items-center gap-2 mt-0.5">
                                                <span className="text-xs text-white/40">{signup.company}</span>
                                                <span className="text-xs text-white/20">·</span>
                                                <span className="text-xs text-white/40">{signup.role}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className="text-xs text-white/40">{signup.time}</span>
                                        <StatusBadge status={signup.status === 'pending' ? 'trial' : signup.status === 'accepted' ? 'active' : 'warning'} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
