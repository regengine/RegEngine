'use client';

import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';
import { WaitlistGate } from '@/components/ui/waitlist-gate';

export default function VerticalsLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();

    // Only allow food-safety and fsma related pages
    const isAllowed = pathname?.includes('/food-safety') || pathname?.includes('/fsma');
    const verticalMatch = pathname?.match(/\/verticals\/([^/]+)/);
    const verticalName = verticalMatch ? verticalMatch[1].charAt(0).toUpperCase() + verticalMatch[1].slice(1) : 'Industry';

    if (!isAllowed && pathname?.startsWith('/verticals')) {
        return <WaitlistGate featureName={verticalName} />;
    }

    // Wrap allowed verticals transparently
    return <>{children}</>;
}
