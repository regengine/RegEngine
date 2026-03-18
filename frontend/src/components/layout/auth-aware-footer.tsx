'use client';

import { useAuth } from '@/lib/auth-context';
import { usePathname } from 'next/navigation';
import { MarketingFooter } from './marketing-footer';

/**
 * Wraps MarketingFooter to hide it for authenticated users
 * on dashboard/onboarding routes, and show a minimal footer instead
 * on marketing pages when logged in.
 */
export function AuthAwareFooter() {
    const { user } = useAuth();
    const pathname = usePathname();

    // Dashboard and onboarding have their own chrome — no footer at all
    const isAppRoute =
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding');

    if (isAppRoute) {
        return null;
    }

    // Logged-in user on a marketing page: show a slim footer instead of the
    // full marketing footer with signup CTAs
    if (user) {
        return (
            <footer
                style={{
                    borderTop: '1px solid var(--re-surface-border)',
                    padding: '24px 16px',
                    textAlign: 'center',
                    fontSize: '12px',
                    color: 'var(--re-text-disabled)',
                    background: 'var(--re-surface-elevated)',
                }}
            >
                <div style={{ maxWidth: 1120, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                    <span>&copy; {new Date().getFullYear()} RegEngine Inc.</span>
                    <div style={{ display: 'flex', gap: '16px' }}>
                        <a href="/dashboard" style={{ color: 'var(--re-text-muted)', textDecoration: 'none' }}>Dashboard</a>
                        <a href="/privacy" style={{ color: 'var(--re-text-muted)', textDecoration: 'none' }}>Privacy</a>
                        <a href="/terms" style={{ color: 'var(--re-text-muted)', textDecoration: 'none' }}>Terms</a>
                        <a href="/contact" style={{ color: 'var(--re-text-muted)', textDecoration: 'none' }}>Contact</a>
                    </div>
                </div>
            </footer>
        );
    }

    // Not logged in: show the full marketing footer
    return <MarketingFooter />;
}
