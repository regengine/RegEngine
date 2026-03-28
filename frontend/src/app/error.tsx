'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import Link from 'next/link';

export default function RootError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
            Sentry.captureException(error);
        }
        console.error('Root error boundary:', error);
    }, [error]);

    const isBackendError = error.message?.includes('fetch') ||
        error.message?.includes('network') ||
        error.message?.includes('ECONNREFUSED') ||
        error.message?.includes('504') ||
        error.message?.includes('502');

    return (
        <div className="flex items-center justify-center min-h-[60vh] p-6">
            <div className="max-w-md w-full text-center space-y-6">
                <div className="mx-auto w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center">
                    <AlertTriangle className="h-8 w-8 text-red-400" />
                </div>

                <div>
                    <h2 className="text-xl font-semibold mb-2">
                        {isBackendError ? 'Service Unavailable' : 'Something went wrong'}
                    </h2>
                    <p className="text-sm text-muted-foreground">
                        {isBackendError
                            ? 'RegEngine is temporarily unavailable. This usually resolves in a few moments.'
                            : 'An unexpected error occurred. Our team has been notified.'}
                    </p>
                </div>

                {error.digest && (
                    <p className="text-xs text-muted-foreground font-mono">
                        Error ID: {error.digest}
                    </p>
                )}

                <div className="flex items-center justify-center gap-3">
                    <button
                        onClick={reset}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--re-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
                    >
                        <RefreshCw className="h-4 w-4" />
                        Try Again
                    </button>
                    <Link
                        href="/"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--re-border-default)] text-sm font-medium hover:bg-white/[0.03] transition-colors"
                    >
                        <Home className="h-4 w-4" />
                        Home
                    </Link>
                </div>
            </div>
        </div>
    );
}
