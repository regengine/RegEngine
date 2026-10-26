import { Suspense } from 'react';
import type { Metadata } from 'next';
import VerifyClient from './VerifyClient';

export const metadata: Metadata = {
    title: 'Verify your sign-in code | RegEngine',
};

export default async function VerifyPage({
    searchParams,
}: {
    searchParams: Promise<{ email?: string; challenge_id?: string }>;
}) {
    const params = await searchParams;

    return (
        <Suspense>
            <VerifyClient
                initialEmail={params.email ?? ''}
                initialChallengeId={params.challenge_id ?? ''}
            />
        </Suspense>
    );
}
