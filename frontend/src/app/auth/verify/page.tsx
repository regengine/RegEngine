import { Suspense } from 'react';
import type { Metadata } from 'next';
import VerifyClient from './VerifyClient';

export const metadata: Metadata = {
    title: 'Reset your password — RegEngine',
};

export default function VerifyPage({
    searchParams,
}: {
    searchParams: { token?: string; type?: string };
}) {
    const tokenHash = searchParams.token ?? '';
    const type = searchParams.type ?? 'recovery';

    return (
        <Suspense>
            <VerifyClient tokenHash={tokenHash} type={type} />
        </Suspense>
    );
}
