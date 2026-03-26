/**
 * Hook for gracefully handling disabled backend routers (H10).
 *
 * When DISABLED_ROUTERS env var is set on the backend, certain endpoints
 * return 404. This utility detects that pattern and provides a clear
 * "feature unavailable" state instead of a confusing error.
 */

/** Check if an API error indicates a disabled backend router */
export function isFeatureDisabled(error: unknown): boolean {
    if (error instanceof Error) {
        // Backend returns 404 when router is disabled via DISABLED_ROUTERS
        return error.message.includes('API error: 404');
    }
    return false;
}

/** Format a user-friendly message for disabled features */
export function featureDisabledMessage(featureName: string): string {
    return `${featureName} is not enabled in this environment. Contact your administrator to enable it.`;
}
