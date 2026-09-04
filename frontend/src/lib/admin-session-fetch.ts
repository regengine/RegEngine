import { getAdminTargets, shouldRetryAdminProxyResponse } from './admin-targets';

/** Fetch an admin-backend path using the same public/internal fallback order
 * as the main admin proxy. Callers are responsible for constructing the
 * selected opaque-session headers; this helper never injects credentials.
 */
export async function fetchAdminSessionPath(
    path: string,
    init: RequestInit,
): Promise<Response | null> {
    let retryableResponse: Response | null = null;

    for (const target of getAdminTargets(process.env)) {
        const url = `${target.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
        try {
            const response = await fetch(url, { ...init, redirect: 'manual' });
            if (response.status >= 300 && response.status < 400) {
                return response;
            }
            if (shouldRetryAdminProxyResponse(response, path.replace(/^\/+/, ''))) {
                retryableResponse = response;
                continue;
            }
            return response;
        } catch {
            // Try the next configured admin target.
        }
    }

    return retryableResponse;
}
