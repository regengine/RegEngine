/**
 * Sentry Configuration for Frontend
 * 
 * Currently DISABLED — Sentry SDK is not installed.
 * 
 * To enable error tracking:
 *   1. npm install @sentry/nextjs
 *   2. Set NEXT_PUBLIC_SENTRY_DSN in your environment
 *   3. Uncomment the Sentry.init block below and remove the stubs
 */

// Stub exports — these are safe no-ops that prevent import errors
// from any code that references sentry utilities.
// They route errors to the browser console as a minimal fallback.

export const captureError = (error: Error, context?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
        console.error('[Error Tracking Disabled]', error.message, context);
    }
};

export const captureMessage = (message: string, level: string = 'info') => {
    if (process.env.NODE_ENV === 'development') {
        console.log(`[${level}] ${message}`);
    }
};

export const setUserContext = (_user: { id: string; email?: string; username?: string }) => {
    // No-op: Sentry not installed
};

export const clearUserContext = () => {
    // No-op: Sentry not installed
};
