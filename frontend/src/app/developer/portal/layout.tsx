'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import {
    LayoutDashboard,
    Key,
    BarChart3,
    BookOpen,
    LogOut,
    ShieldCheck,
} from 'lucide-react';

const NAV_ITEMS = [
    { label: 'Dashboard', href: '/developer/portal', icon: LayoutDashboard },
    { label: 'API Keys', href: '/developer/portal/keys', icon: Key },
    { label: 'Usage', href: '/developer/portal/usage', icon: BarChart3 },
    { label: 'API Docs', href: '/developer/portal/docs', icon: BookOpen },
];

export default function DeveloperPortalLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const supabase = createSupabaseBrowserClient();

    async function handleLogout() {
        await supabase.auth.signOut();
        router.push('/developer/login');
        router.refresh();
    }

    return (
        <div className="min-h-screen flex" style={{ background: 'var(--re-surface-base)' }}>
            {/* Sidebar */}
            <aside className="w-56 flex-shrink-0 flex flex-col" style={{ borderRight: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.01)' }}>
                <div className="p-4 flex items-center gap-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <ShieldCheck className="w-5 h-5" style={{ color: 'var(--re-brand)' }} />
                    <span className="font-semibold text-sm" style={{ color: 'var(--re-text-primary)' }}>Dev Portal</span>
                </div>

                <nav className="flex-1 p-2 space-y-1">
                    {NAV_ITEMS.map((item) => {
                        const isActive = pathname === item.href || (item.href !== '/developer/portal' && pathname.startsWith(item.href));
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className="flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors"
                                style={{
                                    color: isActive ? 'var(--re-text-primary)' : 'var(--re-text-muted)',
                                    background: isActive ? 'rgba(16,185,129,0.1)' : 'transparent',
                                }}
                            >
                                <item.icon className="w-4 h-4" style={{ color: isActive ? 'var(--re-brand)' : 'var(--re-text-disabled)' }} />
                                {item.label}
                            </Link>
                        );
                    })}
                </nav>

                <div className="p-2" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <button
                        onClick={handleLogout}
                        className="flex items-center gap-3 px-3 py-2 rounded-md text-sm w-full transition-colors hover:bg-red-500/10"
                        style={{ color: 'var(--re-text-muted)' }}
                    >
                        <LogOut className="w-4 h-4" />
                        Sign Out
                    </button>
                    <Link
                        href="/"
                        className="flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors mt-1"
                        style={{ color: 'var(--re-text-disabled)' }}
                    >
                        regengine.co
                    </Link>
                </div>
            </aside>

            {/* Main content */}
            <main className="flex-1 overflow-auto">
                <div className="max-w-5xl mx-auto p-6">
                    {children}
                </div>
            </main>
        </div>
    );
}
