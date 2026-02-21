'use client';

import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';
import { WaitlistGate } from '@/components/ui/waitlist-gate';

export default function VerticalsLayout({ children }: { children: ReactNode }) {
    return <>{children}</>;
}
