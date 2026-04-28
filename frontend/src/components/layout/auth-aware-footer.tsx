'use client';

import { usePathname } from 'next/navigation';
import { shouldHideMarketingChrome } from '@/lib/app-routes';
import { MarketingFooter } from './marketing-footer';

/**
 * Wraps MarketingFooter and hides it on authenticated app routes.
 */
export function AuthAwareFooter() {
    const pathname = usePathname();

    if (shouldHideMarketingChrome(pathname)) {
        return null;
    }

    // Show full marketing footer on all public pages (logged in or not)
    return <MarketingFooter />;
}
