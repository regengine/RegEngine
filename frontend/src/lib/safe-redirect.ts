/**
 * Validate a `next`-style relative-path redirect target. Returns the input
 * if it's a same-app path; returns the fallback otherwise.
 *
 * Rejects:
 *   - empty / null / undefined
 *   - strings longer than 256 chars (defense in depth)
 *   - strings not starting with `/` (relative path traversal)
 *   - strings starting with `//` (protocol-relative URL bypass)
 *   - strings containing `\` (Windows-style backslash bypass)
 *   - strings containing `://` (absolute URLs, including `javascript:`/`data:`)
 *
 * Closes the audit's OQ-2 / RE-FE-AUDIT-002 (next-param redirect hygiene).
 */
export function safeNextPath(next: string | null | undefined, fallback: string): string {
    if (!next) return fallback;
    if (next.length > 256) return fallback;
    if (!next.startsWith('/')) return fallback;
    if (next.startsWith('//')) return fallback;
    if (next.includes('\\')) return fallback;
    if (next.includes('://')) return fallback;
    return next;
}
