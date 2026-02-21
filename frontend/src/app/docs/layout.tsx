'use client';

import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';
import { WaitlistGate } from '@/components/ui/waitlist-gate';

export default function DocsLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();

    // Allowed docs paths: generic docs, api, authentication, errors, rate-limits, sdks, webhooks, fsma-204, changelog
    // and standard tools like quickstart. Anything explicitly aligned to a vertical is checked.
    const allowedDocsPatterns = [
        /^\/docs$/,
        /^\/docs\/api/,
        /^\/docs\/authentication/,
        /^\/docs\/changelog/,
        /^\/docs\/errors/,
        /^\/docs\/fsma-204/,
        /^\/docs\/quickstart/,
        /^\/docs\/rate-limits/,
        /^\/docs\/sdks/,
        /^\/docs\/webhooks/
    ];

    const isAllowed = allowedDocsPatterns.some(pattern => pattern.test(pathname || ''));

    // Extract vertical name if it's a specific vertical doc
    const docsMatch = pathname?.match(/\/docs\/([^/]+)/);
    const featureName = docsMatch ? docsMatch[1].charAt(0).toUpperCase() + docsMatch[1].slice(1) : 'Documentation';

    if (!isAllowed && pathname?.startsWith('/docs/')) {
        return <WaitlistGate featureName={`${featureName} Documentation`} />;
    }

    // Wrap allowed docs transparently
    return <>{children}</>;
}
