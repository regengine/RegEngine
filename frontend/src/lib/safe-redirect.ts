/**
 * Placeholder origin used only to prove that a candidate path resolves to the
 * same origin it is resolved against. It is never used as a redirect target.
 */
const BASE_ORIGIN = 'https://regengine.co';

/**
 * Validate a `next`-style relative-path redirect target. Returns the input
 * unchanged if it's a same-app path; returns the fallback otherwise.
 *
 * Rejects:
 *   - empty / null / undefined
 *   - strings longer than 256 chars (defense in depth)
 *   - strings not starting with `/` (relative path traversal)
 *   - strings starting with `//` (protocol-relative URL bypass)
 *   - strings containing `\` (Windows-style backslash bypass)
 *   - strings containing `://` (absolute URLs, including `javascript:`/`data:`)
 *   - strings containing any character <= U+0020 or U+007F, anywhere. The
 *     WHATWG URL parser silently deletes tab, LF and CR wherever they appear,
 *     so `/<TAB>/evil.com` is read by a browser as `//evil.com` (a different
 *     origin) even though the raw string starts with a single `/`.
 *   - strings that start with one of `denyPrefixes` (e.g. the login page
 *     itself, so a `next` target cannot bounce back to the page that reads it)
 *   - strings that do not resolve to the same origin once parsed as a URL
 *
 * Closes the audit's OQ-2 / RE-FE-AUDIT-002 (next-param redirect hygiene).
 */
export function safeNextPath(
    next: string | null | undefined,
    fallback: string,
    denyPrefixes: readonly string[] = [],
): string {
    if (!next) return fallback;
    if (next.length > 256) return fallback;
    if (!next.startsWith('/')) return fallback;
    if (next.startsWith('//')) return fallback;
    if (next.includes('\\')) return fallback;
    if (next.includes('://')) return fallback;
    for (let i = 0; i < next.length; i++) {
        const code = next.charCodeAt(i);
        if (code <= 0x20 || code === 0x7f) return fallback;
    }
    if (denyPrefixes.some((prefix) => next.startsWith(prefix))) return fallback;
    try {
        if (new URL(next, BASE_ORIGIN).origin !== BASE_ORIGIN) return fallback;
    } catch {
        return fallback;
    }
    return next;
}
