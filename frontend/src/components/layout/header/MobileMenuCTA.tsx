'use client';

import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { User } from '@/types/api';

interface MobileMenuCTAProps {
    user: User | null;
    showLoggedIn: boolean;
    setMobileOpen: (open: boolean) => void;
}

/**
 * Drawer footer actions. Same CTA hierarchy as the desktop header (SPEC §6):
 * "Free Tools" is the one primary and "Log In" is ghost. `size="lg"` (44px) is
 * the mobile touch target.
 */
export function MobileMenuCTA({ user, showLoggedIn, setMobileOpen }: MobileMenuCTAProps) {
    const close = () => setMobileOpen(false);

    return (
        <div className="flex flex-col gap-2.5 border-t border-[var(--re-mobile-border)] px-5 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] pt-4">
            {showLoggedIn ? (
                <>
                    <div className="mb-3 flex items-center gap-3 border-b border-[var(--re-mobile-border)] pb-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-re-border bg-re-surface-inset text-ui font-semibold uppercase text-re-text-primary">
                            {user?.email?.[0] || 'U'}
                        </span>
                        <span className="min-w-0">
                            <span className="block truncate text-ui font-medium text-re-text-primary">
                                {user?.email || 'Account'}
                            </span>
                            <span className="block text-small text-re-text-muted">Logged in</span>
                        </span>
                    </div>
                    <Button asChild variant="primary" size="lg">
                        <Link href="/dashboard" onClick={close}>
                            <LayoutGrid aria-hidden="true" strokeWidth={1.75} />
                            Go to Dashboard
                        </Link>
                    </Button>
                </>
            ) : (
                <>
                    <Button asChild variant="primary" size="lg">
                        <Link href="/tools" onClick={close}>
                            Free Tools
                        </Link>
                    </Button>
                    <Button asChild variant="ghost" size="lg">
                        <Link href="/login" onClick={close}>
                            Log In
                        </Link>
                    </Button>
                </>
            )}
        </div>
    );
}
