/**
 * Turn a failed `requestPublicJson` call into a sentence a person can act on.
 *
 * `requestPublicJson` throws `{ status, data, requestId }`. The API's error body is
 * `{ "error": { "type", "message", "details"?, "correlation_id"?, "request_id"? } }`
 * (services/shared/error_handling.py). Older handlers used `{ "detail": "..." }`.
 * A page that only reads `detail` shows its fallback for every failure.
 */

// Messages the API uses when it is deliberately saying nothing. Showing them
// helps nobody; the caller's fallback is better.
const UNINFORMATIVE = new Set(['an internal error occurred', 'invalid request', 'request validation failed']);

function asRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function usable(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const text = value.trim();
    if (!text || UNINFORMATIVE.has(text.toLowerCase().replace(/[.!]+$/, ''))) return null;
    return text;
}

/** HTTP status of a failed request, or undefined (network failure, unknown shape). */
export function requestErrorStatus(error: unknown): number | undefined {
    const status = asRecord(error)?.status;
    return typeof status === 'number' ? status : undefined;
}

/** "ship_date" -> "Ship date". The last named segment of a pydantic `loc`. */
function fieldLabel(loc: unknown): string | null {
    if (!Array.isArray(loc)) return null;
    const name = [...loc].reverse().find((part) => typeof part === 'string' && part !== 'body');
    if (typeof name !== 'string' || !/^[a-z0-9_]{1,60}$/i.test(name)) return null;
    const words = name.replace(/_/g, ' ').trim();
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : null;
}

/**
 * First field-level validation message. A custom validator's message
 * ("Value error, ship_date must be ...") already names its field; pydantic's
 * built-in ones ("Field required") do not, so the field is put in front.
 */
function validationMessage(envelope: Record<string, unknown>): string | null {
    if (!Array.isArray(envelope.details)) return null;
    for (const item of envelope.details) {
        const detail = asRecord(item);
        const message = usable(detail?.msg);
        if (!message) continue;
        if (/^value error,\s*/i.test(message)) return message.replace(/^value error,\s*/i, '');
        const label = fieldLabel(detail?.loc);
        return label ? `${label}: ${message}` : message;
    }
    return null;
}

function serverMessage(data: unknown): string | null {
    const body = asRecord(data);
    if (!body) return null;
    const envelope = asRecord(body.error);
    if (envelope) {
        return validationMessage(envelope) ?? usable(envelope.message);
    }
    // A top-level string `error` is a machine code or proxy text
    // ("rate_limit_exceeded", "Missing CSRF token"), not a sentence for the
    // person filling in the form. Bodies that carry one are not shown.
    if (typeof body.error === 'string') return null;
    return usable(body.detail);
}

function reference(error: unknown): string | null {
    const failure = asRecord(error);
    const envelope = asRecord(asRecord(failure?.data)?.error);
    // Through the BFF proxy the 5xx body is replaced and the id arrives as the
    // x-request-id header, which requestPublicJson passes on as `requestId`.
    return usable(envelope?.correlation_id) ?? usable(envelope?.request_id) ?? usable(failure?.requestId);
}

/**
 * The message to show for a failed public request.
 *
 * - 4xx: the server's own message when it has one (these are written for the
 *   caller: "Portal link not found or expired", a rate-limit notice, the
 *   field that failed validation).
 * - 5xx: the fallback, plus the server's reference id when it sent one, so the
 *   person can quote it. The server masks 5xx details on purpose.
 * - No response (offline, DNS, CORS): the fallback.
 */
export function publicRequestErrorMessage(error: unknown, fallback: string): string {
    const status = requestErrorStatus(error);
    const data = asRecord(error)?.data;

    if (status !== undefined && status >= 500) {
        const ref = reference(error);
        return ref ? `${fallback} (Reference: ${ref})` : fallback;
    }

    const message = serverMessage(data);
    if (message) return message;
    if (status === 429) return 'Too many requests. Wait a minute and try again.';
    return fallback;
}
