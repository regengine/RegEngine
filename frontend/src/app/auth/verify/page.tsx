import { Suspense } from 'react';
import type { Metadata } from 'next';
import { LOGIN_NEXT_DENY_PREFIXES, safeNextPath } from '@/lib/safe-redirect';
import VerifyClient from './VerifyClient';

export const metadata: Metadata = {
    title: 'Verify your sign-in code — RegEngine',
};

export default async function VerifyPage({
    searchParams,
}: {
    searchParams: Promise<{ email?: string; challenge_id?: string; next?: string | string[] }>;
}) {
    const params = await searchParams;
    // A repeated ?next= arrives as an array; use the first value, as
    // URLSearchParams.get() does on /login.
    const rawNext = Array.isArray(params.next) ? params.next[0] : params.next;

    return (
        <Suspense>
            <VerifyClient
                initialEmail={params.email ?? ''}
                initialChallengeId={params.challenge_id ?? ''}
                nextPath={safeNextPath(rawNext, '/dashboard', LOGIN_NEXT_DENY_PREFIXES)}
            />
        </Suspense>
    );
}
