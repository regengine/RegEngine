'use client';

import { filterExperimentalLinks } from '@/lib/experimental-features';
import Link from 'next/link';
import { X } from 'lucide-react';
import { MARKETING_ALL_TOOLS_LINK, MARKETING_PRIMARY_NAV, MARKETING_FREE_TOOLS } from '@/components/layout/marketing-nav';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { ThemeToggle } from '@/components/layout/theme-toggle';
import { cn } from '@/lib/utils';
import { MobileMenuCTA } from './MobileMenuCTA';
import type { MobileMenuProps } from './types';

/**
 * Mobile navigation drawer.
 *
 * Every one of the seventeen inline style objects this file used to carry is
 * now a token utility. The contract kept intact: `role="dialog"` +
 * `aria-label="Navigation menu"`, the `.marketing-mobile-drawer` class hook,
 * the safe-area insets, and the parent's `re:mobile-menu-state` CustomEvent
 * (AccessibilityWidget and CookieBanner both listen for it).
 */
const LOGGED_IN_LINKS = [
    { label: 'Dashboard', href: '/dashboard' },
    { label: 'Heartbeat', href: '/dashboard/heartbeat' },
    { label: 'Compliance', href: '/dashboard/compliance' },
    { label: 'Alerts', href: '/dashboard/alerts' },
    { label: 'Suppliers', href: '/dashboard/suppliers' },
    { label: 'Products', href: '/dashboard/products' },
    { label: 'Settings', href: '/dashboard/settings' },
];

export function MobileMenu({ user, showLoggedIn, pathname, mobileOpen, setMobileOpen }: MobileMenuProps) {
    return (
        <>
            {/* Drawer scrim */}
            <div
                className={cn(
                    'fixed inset-0 z-[var(--re-z-sticky)] bg-re-surface-overlay backdrop-blur-[4px] transition-[opacity,visibility] duration-240 motion-reduce:transition-none',
                    mobileOpen ? 'visible opacity-100' : 'invisible opacity-0 pointer-events-none'
                )}
                onClick={() => setMobileOpen(false)}
                aria-hidden="true"
            />

            {/* Drawer panel */}
            <div
                className={cn(
                    'marketing-mobile-drawer fixed bottom-0 right-0 top-0 z-[var(--re-z-modal)] flex w-[min(320px,85vw)] flex-col overflow-y-auto border-l border-[var(--re-mobile-border)] bg-[var(--re-mobile-menu-bg)] pb-[env(safe-area-inset-bottom,0px)] pt-[env(safe-area-inset-top,0px)] transition-[transform,visibility] duration-240 motion-reduce:transition-none',
                    mobileOpen ? 'visible translate-x-0' : 'invisible translate-x-full pointer-events-none'
                )}
                role="dialog"
                aria-modal={mobileOpen ? true : undefined}
                aria-hidden={!mobileOpen}
                aria-label="Navigation menu"
            >
                {/* Drawer header */}
                <div className="flex min-h-[56px] items-center justify-between border-b border-[var(--re-mobile-border)] px-5 py-4">
                    <RegEngineWordmark size="sm" />
                    <button
                        type="button"
                        onClick={() => setMobileOpen(false)}
                        aria-label="Close menu"
                        className="-mr-2 flex h-11 w-11 items-center justify-center rounded-md border-0 bg-transparent p-0 text-re-text-muted transition-colors duration-120 hover:bg-re-surface-inset hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                    >
                        <X aria-hidden="true" size={20} strokeWidth={1.75} />
                    </button>
                </div>

                {/* Primary nav links */}
                <div className="px-3 py-2">
                    {filterExperimentalLinks(user ? LOGGED_IN_LINKS : MARKETING_PRIMARY_NAV).map((item) => (
                        <Link
                            key={item.label}
                            href={item.href}
                            onClick={() => setMobileOpen(false)}
                            aria-current={pathname === item.href ? 'page' : undefined}
                            className={cn(
                                'relative flex min-h-[48px] items-center rounded-md px-3 py-3.5 text-ui no-underline transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none',
                                pathname === item.href
                                    ? 'bg-re-surface-inset font-medium text-re-text-primary'
                                    : 'emphasis' in item && item.emphasis === 'brand'
                                        ? 'font-medium text-re-brand'
                                        : 'text-re-text-secondary'
                            )}
                        >
                            {pathname === item.href && (
                                <span
                                    aria-hidden="true"
                                    className="absolute bottom-2 left-0 top-2 w-0.5 rounded-full bg-re-brand"
                                />
                            )}
                            {item.label}
                        </Link>
                    ))}
                </div>

                <div aria-hidden="true" className="mx-5 h-px bg-[var(--re-mobile-border)]" />

                {/* Free tools */}
                <div className="px-3 py-2">
                    <div className="px-3 pb-1 pt-2 text-label uppercase text-re-text-muted">
                        FSMA 204 Compliance Tools
                    </div>
                    {[...MARKETING_FREE_TOOLS, MARKETING_ALL_TOOLS_LINK].map((tool) => (
                        <Link
                            key={tool.href}
                            href={tool.href}
                            onClick={() => setMobileOpen(false)}
                            className="flex min-h-[48px] items-start gap-3 rounded-md p-3 no-underline transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                        >
                            <tool.icon
                                aria-hidden="true"
                                size={16}
                                strokeWidth={1.75}
                                className="mt-0.5 shrink-0 text-re-text-tertiary"
                            />
                            <span className="min-w-0">
                                <span className="block text-ui font-medium text-re-text-primary">
                                    {tool.href === '/tools' ? `${tool.label} →` : tool.label}
                                </span>
                                <span className="mt-0.5 block text-small text-re-text-tertiary">{tool.desc}</span>
                            </span>
                        </Link>
                    ))}
                </div>

                <div aria-hidden="true" className="mx-5 h-px bg-[var(--re-mobile-border)]" />

                {/* Theme */}
                <div className="flex items-center justify-between px-6 py-3">
                    <span className="text-ui text-re-text-secondary">Theme</span>
                    <ThemeToggle />
                </div>

                <div className="flex-1" />

                <MobileMenuCTA user={user} showLoggedIn={showLoggedIn} setMobileOpen={setMobileOpen} />
            </div>
        </>
    );
}
