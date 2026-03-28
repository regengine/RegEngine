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

    // Dashboard and onboarding have their own chrome — no footer
    const isAppRoute =
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding');

    if (isAppRoute) {
        return null;
    }

    // Show full marketing footer on all public pages (logged in or not)
    return <MarketingFooter />;
}
