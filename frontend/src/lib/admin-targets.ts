import { isPublicHost, stripTrailingSlash } from './proxy-factory';

export const DEFAULT_LOCAL_MONOLITH_URL = 'http://localhost:8000';
export const DEFAULT_LOCAL_ADMIN_URL = 'http://localhost:8400';

const VERCEL_PRIVATE_DNS_ERROR = 'DNS_HOSTNAME_RESOLVED_PRIVATE';

function pushUniqueTarget(targets: string[], value: string | undefined): void {
    if (!value) {
        return;
    }

    const normalized = stripTrailingSlash(value);
    if (!normalized || targets.includes(normalized)) {
        return;
    }

    targets.push(normalized);
}

function isLocalRuntime(env: NodeJS.ProcessEnv): boolean {
    return !Boolean(env.VERCEL || env.VERCEL_URL || env.VERCEL_ENV);
}

export function getAdminTargets(env: NodeJS.ProcessEnv = process.env): string[] {
    const targets: string[] = [];
    const publicAdminUrl = env.NEXT_PUBLIC_ADMIN_URL;
    const publicApiBase = env.NEXT_PUBLIC_API_BASE_URL;
    const internalAdminUrl = env.ADMIN_SERVICE_URL;
    const runningLocally = isLocalRuntime(env);

    pushUniqueTarget(targets, publicAdminUrl);

    if (internalAdminUrl && (runningLocally || isPublicHost(internalAdminUrl))) {
        pushUniqueTarget(targets, internalAdminUrl);
    }

    if (publicApiBase) {
        const normalizedPublicApiBase = stripTrailingSlash(publicApiBase);
        // Support both deployment shapes:
        //  1. Monolith root exposing /auth/* and /v1/*
        //  2. Legacy gateway exposing /admin/auth/* and /admin/v1/*
        pushUniqueTarget(targets, normalizedPublicApiBase);
        pushUniqueTarget(targets, `${normalizedPublicApiBase}/admin`);
    }

    if (runningLocally) {
        // Local development can run either the consolidated monolith (:8000)
        // or the older split admin service (:8400).
        pushUniqueTarget(targets, DEFAULT_LOCAL_MONOLITH_URL);
        pushUniqueTarget(targets, DEFAULT_LOCAL_ADMIN_URL);
    }

    return targets;
}

export function shouldRetryAdminProxyResponse(response: Response, path: string): boolean {
    const vercelError = response.headers.get('x-vercel-error') || '';
    if (vercelError.includes(VERCEL_PRIVATE_DNS_ERROR)) {
        return true;
    }

    if (response.status !== 404) {
        return false;
    }

    // Route-shape drift shows up as 404s when one deploy expects
    // `/auth/*` / `/v1/*` at the root and another expects `/admin/...`.
    return path === 'health' || path.startsWith('auth/') || path.startsWith('v1/');
}
