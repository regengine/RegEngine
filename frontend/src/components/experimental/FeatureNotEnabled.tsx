import Link from 'next/link';
import { FlaskConical } from 'lucide-react';

interface FeatureNotEnabledProps {
    /** Human-readable feature name, e.g. "Traceability Query Engine" */
    featureName: string;
    /** Where the back link points (default "/") */
    backHref?: string;
    /** Label for the back link (default "Back to home") */
    backLabel?: string;
}

/**
 * Clean placeholder for pages whose backend routers are auto-disabled in
 * production (see lib/experimental-features.ts). Server-component safe.
 */
export function FeatureNotEnabled({
    featureName,
    backHref = '/',
    backLabel = 'Back to home',
}: FeatureNotEnabledProps) {
    return (
        <div
            data-testid="feature-not-enabled"
            className="flex min-h-[60vh] items-center justify-center px-4 py-16"
        >
            <div className="w-full max-w-md rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-8 text-center shadow-sm">
                <FlaskConical className="mx-auto h-8 w-8 text-[var(--re-text-muted)]" aria-hidden="true" />
                <h1 className="mt-4 text-lg font-semibold text-[var(--re-text-primary)]">
                    {featureName} is not enabled
                </h1>
                <p className="mt-2 text-sm text-[var(--re-text-muted)]">
                    This feature is part of an experimental preview and is not
                    enabled in this environment.
                </p>
                <Link
                    href={backHref}
                    className="mt-6 inline-flex items-center text-sm font-semibold text-[var(--re-brand)] hover:underline"
                >
                    {backLabel}
                </Link>
            </div>
        </div>
    );
}
