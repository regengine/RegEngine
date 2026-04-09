'use client';

import { usePathname } from 'next/navigation';
import { MarketingFooter } from './marketing-footer';

/**
 * Wraps MarketingFooter and hides it on dashboard/onboarding routes
 * that supply their own chrome.
 */
export function AuthAwareFooter() {
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
