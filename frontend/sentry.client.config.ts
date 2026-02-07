/**
 * Sentry Configuration for Frontend
 * 
 * DISABLED: Install @sentry/nextjs to enable error tracking
 * Run: npm install @sentry/nextjs
 */

// Uncomment below after installing @sentry/nextjs
/*
import * as Sentry from '@sentry/nextjs';

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN;

Sentry.init({
    dsn: SENTRY_DSN,
    environment: process.env.NEXT_PUBLIC_ENV || process.env.NODE_ENV || 'production',
    release: process.env.NEXT_PUBLIC_VERSION || 'unknown',
    tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    integrations: [
        new Sentry.BrowserTracing({
            routingInstrumentation: Sentry.nextRouterInstrumentation,
        }),
        new Sentry.Replay({
            maskAllText: true,
            blockAllMedia: true,
        }),
    ],
    ignoreErrors: [
        'top.GLOBALS',
        'canvas.contentDocument',
        'MyApp_RemoveAllHighlights',
        'atomicFindClose',
        'Network request failed',
        'NetworkError',
        'Failed to fetch',
        'ResizeObserver loop limit exceeded',
        'ResizeObserver loop completed with undelivered notifications',
        'Non-Error promise rejection captured',
    ],
    beforeSend(event, hint) {
        if (process.env.NODE_ENV === 'development') {
            console.error('Sentry would send:', event);
            return null;
        }
        if (event.request?.url?.includes('localhost')) {
            return null;
        }
        return event;
    },
    initialScope: {
        tags: {
            'app.name': 'RegEngine',
            'app.component': 'frontend',
        },
    },
});

export const captureError = (error: Error, context?: Record<string, any>) => {
    Sentry.captureException(error, { contexts: { custom: context } });
};

export const captureMessage = (message: string, level: Sentry.SeverityLevel = 'info') => {
    Sentry.captureMessage(message, level);
};

export const setUserContext = (user: { id: string; email?: string; username?: string }) => {
    Sentry.setUser(user);
};

export const clearUserContext = () => {
    Sentry.setUser(null);
};
*/

// Stub exports until Sentry is installed
export const captureError = (error: Error, context?: Record<string, any>) => {
    console.error('Error (Sentry disabled):', error, context);
};

export const captureMessage = (message: string, level: string = 'info') => {
    console.log(`[${level}] ${message}`);
};

export const setUserContext = (user: { id: string; email?: string; username?: string }) => {
    console.log('User context (Sentry disabled):', user);
};

export const clearUserContext = () => {
    console.log('User context cleared (Sentry disabled)');
};
