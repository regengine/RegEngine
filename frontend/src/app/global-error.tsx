"use client";

/**
 * Global Error Handler — App Router
 *
 * Captures unhandled React rendering errors and reports them to Sentry.
 * This is the last line of defense for client-side crashes.
 *
 * See: https://nextjs.org/docs/app/building-your-application/routing/error-handling
 */

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        // Report to Sentry if configured
        if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
            Sentry.captureException(error);
        }
    }, [error]);

    return (
        <html>
            <body className="min-h-screen bg-re-surface-base flex items-center justify-center">
                <div className="text-center max-w-md p-8">
                    <div className="p-4 rounded-2xl bg-re-danger-muted border border-re-danger/20 inline-flex mb-6">
                        <svg className="h-10 w-10 text-re-danger" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                        </svg>
                    </div>
                    <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">Something went wrong</h1>
                    <p className="text-[var(--re-text-muted)] mb-6">
                        An unexpected error occurred. Our team has been notified.
                    </p>
                    <button
                        onClick={reset}
                        className="px-6 py-3 rounded-lg bg-re-brand text-white font-medium hover:bg-re-brand-dark transition-all"
                    >
                        Try Again
                    </button>
                </div>
            </body>
        </html>
    );
}
