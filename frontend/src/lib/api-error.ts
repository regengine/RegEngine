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
    requestId?: string;
    retryAfter?: number;
    response?: { status?: number; data?: unknown; headers?: Record<string, string>; requestId?: string };
};

/** Build an error that keeps the HTTP status machine-readable. */
export function apiError(status: number, statusText: string, requestId?: string | null): StatusError {
    const suffix = statusText ? ` ${statusText}` : '';
    const error = new Error(`API error: ${status}${suffix}`) as StatusError;
    error.status = status;
    error.response = { status };
    if (requestId) {
        error.requestId = requestId;
        error.response.requestId = requestId;
    }
    return error;
}

/**
 * Read the request ID the backend stamped on a failed response. The shared
 * request-id middleware sets X-Request-ID on every response, so this is real
 * correlation data for support, not a client invention. Returns undefined when
 * the response carries none (network failure, opaque error).
 */
export function requestIdFromResponse(res: unknown): string | undefined {
    if (!res || typeof res !== 'object') return undefined;
    const headers = (res as { headers?: unknown }).headers;
    if (!headers) return undefined;
    if (typeof (headers as { get?: unknown }).get === 'function') {
        const value = (headers as { get: (name: string) => string | null }).get('x-request-id');
        return value || undefined;
    }
    if (typeof headers === 'object') {
        const value = (headers as Record<string, unknown>)['x-request-id']
            ?? (headers as Record<string, unknown>)['X-Request-ID'];
        return typeof value === 'string' && value ? value : undefined;
    }
    return undefined;
}

/** Attach the failed response's request ID to any error, preserving its type. */
export function withRequestId<T extends Error>(error: T, res: unknown): T {
    const requestId = requestIdFromResponse(res);
    if (requestId) {
        (error as StatusError).requestId = requestId;
    }
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

/** Read the request ID off any error shape our fetch layers produce. */
export function getErrorRequestId(error: unknown): string | undefined {
    if (!error || typeof error !== 'object') return undefined;
    const record = error as { requestId?: unknown; response?: unknown };
    if (typeof record.requestId === 'string' && record.requestId) {
        return record.requestId;
    }
    const response = record.response;
    if (response && typeof response === 'object') {
        const nested = response as { requestId?: unknown; headers?: unknown };
        if (typeof nested.requestId === 'string' && nested.requestId) {
            return nested.requestId;
        }
        // APIClient stores lowercased response headers on error.response.
        const headers = nested.headers;
        if (headers && typeof headers === 'object') {
            const map = headers as Record<string, unknown>;
            const value = map['x-request-id'] ?? map['X-Request-ID'];
            if (typeof value === 'string' && value) {
                return value;
            }
        }
    }
    return undefined;
}

function toRetryAfterSeconds(value: unknown): number | null {
    if (typeof value === 'number') {
        return Number.isInteger(value) && value >= 0 ? value : null;
    }
    if (typeof value === 'string' && value.trim() !== '') {
        const parsed = Number(value.trim());
        return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
    }
    return null;
}

/**
 * Read the Retry-After delay (in seconds) off any error shape our fetch
 * layers produce: a direct `retryAfter` field, or a `retry-after` entry in
 * `response.headers` (APIClient stores lowercased headers there). Returns
 * null when absent or not a plain second count (the HTTP-date form is
 * ignored — callers only ever mention seconds).
 */
export function getErrorRetryAfter(error: unknown): number | null {
    if (!error || typeof error !== 'object') return null;
    const direct = toRetryAfterSeconds((error as { retryAfter?: unknown }).retryAfter);
    if (direct !== null) return direct;
    const response = (error as { response?: unknown }).response;
    if (response && typeof response === 'object') {
        const headers = (response as { headers?: unknown }).headers;
        if (headers && typeof headers === 'object') {
            if (typeof (headers as { get?: unknown }).get === 'function') {
                return toRetryAfterSeconds(
                    (headers as { get: (name: string) => string | null }).get('retry-after'),
                );
            }
            const map = headers as Record<string, unknown>;
            return toRetryAfterSeconds(map['retry-after'] ?? map['Retry-After']);
        }
    }
    return null;
}

/** True when the error is an authentication or authorization failure. */
export function isAuthError(error: unknown): boolean {
    const status = getErrorStatus(error);
    return status === 401 || status === 403;
}
