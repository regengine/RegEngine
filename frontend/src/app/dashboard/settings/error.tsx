'use client';

import { useEffect } from 'react';
import { ErrorState } from '@/components/ui/error-state';

export default function ErrorBoundary({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        if (process.env.NODE_ENV !== 'production') {
            console.error(error);
        }
    }, [error]);

    return (
        <div className="flex items-center justify-center min-h-[60vh] p-6">
            <ErrorState message="We could not load this page." onRetry={reset} requestId={error.digest} className="max-w-md w-full" />
        </div>
    );
}
