'use client';

import { useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
    LayoutDashboard,
    Users,
    BarChart3,
    Shield,
    Settings,
    ChevronRight,
    Building2,
    DollarSign,
    FileSignature,
    Receipt,
    Handshake,
    AlertTriangle,
    Calculator,
    RefreshCw,
    Bell,
    Activity,
    Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth-context';

interface OwnerLayoutProps {
    children: ReactNode;
}

const navItems = [
    { href: '/owner', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/owner/billing', label: 'Revenue', icon: DollarSign },
    { href: '/owner/contracts', label: 'Deals', icon: FileSignature },
    { href: '/owner/invoices', label: 'Invoices', icon: Receipt },
    { href: '/owner/partners', label: 'Partners', icon: Handshake },
    { href: '/owner/dunning', label: 'Collections', icon: AlertTriangle },
    { href: '/owner/tax', label: 'Tax', icon: Calculator },
    { href: '/owner/lifecycle', label: 'Subscriptions', icon: RefreshCw },
    { href: '/owner/alerts', label: 'Alerts', icon: Bell },
    { href: '/owner/forecasting', label: 'Analytics', icon: Activity },
    { href: '/owner/optimization', label: 'Intelligence', icon: Sparkles },
    { href: '/owner/tenants', label: 'Tenants', icon: Users },
    { href: '/owner/analytics', label: 'Usage', icon: BarChart3 },
    { href: '/owner/security', label: 'Security', icon: Shield },
    { href: '/owner/settings', label: 'Settings', icon: Settings },
];

export default function OwnerLayout({ children }: OwnerLayoutProps) {
    const { adminKey } = useAuth();
    const router = useRouter();
    const [currentPath, setCurrentPath] = useState('/owner');
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    useEffect(() => {
        setCurrentPath(window.location.pathname);
    }, []);

    // Check auth state — require admin key for owner dashboard access
    useEffect(() => {
        setIsAuthenticated(!!adminKey);
    }, [adminKey]);

    // Auth gate: show locked screen if no admin key
    if (!isAuthenticated) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
                <div className="text-center max-w-md p-8">
                    <div className="p-4 rounded-2xl bg-gradient-to-br from-amber-500/20 to-orange-600/20 border border-amber-500/30 inline-flex mb-6">
                        <Shield className="h-10 w-10 text-amber-400" />
                    </div>
                    <h1 className="text-2xl font-bold text-white mb-3">Owner Console Access Required</h1>
                    <p className="text-white/60 mb-6">
                        This dashboard requires an Admin Master Key. Please authenticate via the
                        Settings page or contact the system administrator.
                    </p>
                    <Link href="/settings">
                        <button className="px-6 py-3 rounded-lg bg-gradient-to-r from-amber-500 to-orange-600 text-white font-medium hover:from-amber-600 hover:to-orange-700 transition-all">
                            Go to Settings
                        </button>
                    </Link>
                </div>
            </div>
        );
    }

    return (

        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
            {/* Sidebar */}
            <aside className="fixed left-0 top-0 h-full w-64 bg-black/20 backdrop-blur-xl border-r border-white/10 z-50">
                <div className="p-6">
                    <Link href="/owner" className="flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 shadow-lg shadow-amber-500/20">
                            <Building2 className="h-6 w-6 text-white" />
                        </div>
                        <div>
                            <h1 className="font-bold text-white text-lg">RegEngine</h1>
                            <p className="text-xs text-white/60">Owner Console</p>
                        </div>
                    </Link>
                </div>

                <nav className="px-3 mt-4">
                    {navItems.map((item) => {
                        const isActive = currentPath === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    'flex items-center gap-3 px-4 py-3 rounded-lg mb-1 transition-all duration-200 group',
                                    isActive
                                        ? 'bg-white/10 text-white shadow-lg'
                                        : 'text-white/60 hover:text-white hover:bg-white/5'
                                )}
                            >
                                <item.icon className={cn(
                                    'h-5 w-5 transition-colors',
                                    isActive ? 'text-amber-400' : 'text-white/40 group-hover:text-white/60'
                                )} />
                                <span className="font-medium">{item.label}</span>
                                {isActive && (
                                    <ChevronRight className="h-4 w-4 ml-auto text-amber-400" />
                                )}
                            </Link>
                        );
                    })}
                </nav>

                <div className="absolute bottom-6 left-3 right-3">
                    <div className="p-4 rounded-xl bg-gradient-to-br from-amber-500/10 to-orange-600/10 border border-amber-500/20">
                        <p className="text-xs text-white/60 mb-1">Authenticated as</p>
                        <p className="text-sm font-medium text-white truncate">System Owner</p>
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="ml-64 min-h-screen">
                {children}
            </main>
        </div>
    );
}
