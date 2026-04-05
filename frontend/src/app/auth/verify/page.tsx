import { Suspense } from 'react';
import type { Metadata } from 'next';
import VerifyClient from './VerifyClient';

export const metadata: Metadata = {
    title: 'Reset your password — RegEngine',
};

export default async function VerifyPage({
    searchParams,
}: {
    searchParams: Promise<{ token?: string; type?: string }>;
}) {
    const params = await searchParams;
    const tokenHash = params.token ?? '';
    const type = params.type ?? 'recovery';

    return (
        <Suspense>
            <VerifyClient tokenHash={tokenHash} type={type} />
        </Suspense>
    );
}
