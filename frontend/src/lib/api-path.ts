/**
 * Shared helper for building request paths that contain dynamic IDs.
 *
 * IDs can carry characters such as slashes, spaces or question marks (tenant
 * IDs, case IDs, alert IDs and share IDs all originate outside this client).
 * Splicing them into a path raw either breaks the request or changes which
 * route it hits on the server proxy, which rejects bad characters with a 400.
 * Wrap every dynamic path segment with this helper so the whole class of
 * broken requests is removed in one place.
 *
 * Query string values should keep using URLSearchParams, which encodes them
 * already. This helper is only for values interpolated into the path itself.
 */
export function encodePathSegment(value: string | number): string {
    return encodeURIComponent(String(value));
}
