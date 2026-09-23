'use client';

import { Menu, X } from 'lucide-react';

interface MobileHamburgerProps {
    mobileOpen: boolean;
    setMobileOpen: (open: boolean) => void;
}

/**
 * The `.marketing-mobile-toggle` class hook stays — globals.css forces it to
 * `display: flex` under 768px with `!important`. The `xl:hidden` here extends
 * it upward: between 769 and 1279 the eleven-item desktop row did not fit the
 * viewport and the body's `overflow-x: hidden` clipped the overflow away, so
 * the drawer now carries the nav at those widths too.
 */
export function MobileHamburger({ mobileOpen, setMobileOpen }: MobileHamburgerProps) {
    return (
        <button
            type="button"
            className="marketing-mobile-toggle flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-[var(--re-mobile-toggle-border)] bg-transparent p-0 text-re-text-primary transition-colors duration-120 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none xl:hidden"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={mobileOpen}
        >
            {mobileOpen ? (
                <X aria-hidden="true" size={20} strokeWidth={1.75} />
            ) : (
                <Menu aria-hidden="true" size={20} strokeWidth={1.75} />
            )}
        </button>
    );
}
