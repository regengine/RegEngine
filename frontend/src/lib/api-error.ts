/**
 * Shared HTTP error helpers for client-side fetch layers.
 *
 * Every fetch helper used to throw a bare `Error` whose message was the only
 * place the status code appeared (for example `"API error: 401 Unauthorized"`).
 * Callers could not tell 401 (session expired, redirect to login) from 403
 * (forbidden, show access UI) from 404 or 500 without parsing the string, so
 * auth failures were handled like generic errors or hidden entirely.
 *
 * These helpers attach the status as data (`error.status` and
 * `error.response.status`, matching the shape `APIClient` and
 * `passwordless-auth` already use) so UI code can branch on it.
 */

export type StatusError = Error & {
    status?: number;
    response?: { status?: number; data?: unknown };
};

/** Build an error that keeps the HTTP status machine-readable. */
export function apiError(status: number, statusText: string): StatusError {
    const suffix = statusText ? ` ${statusText}` : '';
    const error = new Error(`API error: ${status}${suffix}`) as StatusError;
    error.status = status;
    error.response = { status };
    return error;
}

/** Read the HTTP status off any error shape our fetch layers produce. */
export function getErrorStatus(error: unknown): number | null {
    if (!error || typeof error !== 'object') return null;
    const record = error as { status?: unknown; response?: unknown };
    if (typeof record.status === 'number' && Number.isInteger(record.status)) {
        return record.status;
    }
    const response = record.response;
    if (response && typeof response === 'object') {
        const nested = (response as { status?: unknown }).status;
        if (typeof nested === 'number' && Number.isInteger(nested)) {
            return nested;
        }
    }
    return null;
}

/** True when the error is an authentication or authorization failure. */
export function isAuthError(error: unknown): boolean {
    const status = getErrorStatus(error);
    return status === 401 || status === 403;
}
