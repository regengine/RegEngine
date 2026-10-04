'use client';

import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';
import { MARKETING_PRIMARY_NAV } from '@/components/layout/marketing-nav';
import { ThemeToggle } from '@/components/layout/theme-toggle';
import { Button } from '@/components/ui/button';
import { NavDropdown } from './NavDropdown';
import type { DesktopNavProps } from './types';

/**
 * Desktop marketing nav — SPEC §3.3 / §6.
 *
 * Nav links are sentence-case `text-ui` chrome links, not 12px uppercase
 * monospace: `text-label` is the only uppercase step in the system, and it is
 * reserved for eyebrows and table heads. The label strings themselves are
 * untouched (unit and e2e specs match on them) — only the type changes.
 *
 * CTA hierarchy (SPEC §6): exactly one primary per region. "Free Tools" keeps
 * that slot — it is the CTA this header has always carried — and "Log In" is a
 * ghost chrome link. Adding a new call-to-action is a marketing decision, not a
 * restyle, so this redesign does not introduce one.
 *
 * The `.marketing-desktop-nav` class hook stays: globals.css hides it under
 * 768px with `!important` and shows `.marketing-mobile-toggle` instead. The
 * `xl:` step here is additive — between 769 and 1279 the drawer now carries
 * the nav, where previously eleven items overflowed the viewport and the
 * body's `overflow-x: hidden` clipped them away unreachably.
 */

/** Chrome link recipe — no underline, secondary → primary on hover (SPEC §2.3). */
const NAV_LINK =
    'whitespace-nowrap rounded-sm text-ui font-medium normal-case text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none';

const LOGGED_IN_NAV = [
    { label: 'Compliance', href: '/dashboard/compliance' },
    { label: 'Suppliers', href: '/dashboard/suppliers' },
    { label: 'Products', href: '/dashboard/products' },
];

export function DesktopNav({
    user,
    showLoggedIn,
    toolsOpen,
    setToolsOpen,
    toolsWrapperRef,
    toolsButtonRef,
    handleToolsEnter,
    handleToolsLeave,
    handleToolsKeyDown,
    focusFirstToolsItem,
}: DesktopNavProps) {
    return (
        <div className="marketing-desktop-nav hidden xl:flex items-center gap-3">
            {(showLoggedIn ? LOGGED_IN_NAV : MARKETING_PRIMARY_NAV).map((item) => (
                <Link key={item.label} href={item.href} className={NAV_LINK}>
                    {item.label}
                </Link>
            ))}

            <NavDropdown
                toolsOpen={toolsOpen}
                setToolsOpen={setToolsOpen}
                toolsWrapperRef={toolsWrapperRef}
                toolsButtonRef={toolsButtonRef}
                handleToolsEnter={handleToolsEnter}
                handleToolsLeave={handleToolsLeave}
                handleToolsKeyDown={handleToolsKeyDown}
                focusFirstToolsItem={focusFirstToolsItem}
            />

            {/* Developer & Docs links */}
            <Link href="/developers" className={NAV_LINK}>
                Developers
            </Link>
            <Link href="/docs" className={NAV_LINK}>
                Docs
            </Link>

            <span className="ml-1 flex items-center">
                <ThemeToggle />
            </span>

            {/* Auth-aware actions — exactly one primary (SPEC §4). */}
            {showLoggedIn ? (
                <div className="flex items-center gap-3">
                    <Button asChild variant="primary" size="sm">
                        <Link href="/dashboard">
                            <LayoutGrid aria-hidden="true" strokeWidth={1.75} />
                            Dashboard
                        </Link>
                    </Button>
                    <span
                        title={user?.email || 'Account'}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-re-border bg-re-surface-inset text-small font-semibold uppercase text-re-text-primary"
                    >
                        {user?.email?.[0] || 'U'}
                    </span>
                </div>
            ) : (
                <div className="flex items-center gap-2">
                    <Link href="/login" className={NAV_LINK}>
                        Log In
                    </Link>
                    <Button asChild variant="primary" size="sm">
                        <Link href="/tools">Free Tools</Link>
                    </Button>
                </div>
            )}
        </div>
    );
}
