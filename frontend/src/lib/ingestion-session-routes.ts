const SESSION_ROUTE_PREFIXES = [
    'api/v1/records', 'api/v1/rules', 'api/v1/exceptions',
    'api/v1/requests', 'api/v1/epcis',
];

/** Routes whose backend verifies a workspace session principal. */
export function acceptsWorkspaceSession(path: string): boolean {
    return SESSION_ROUTE_PREFIXES.some(prefix => path === prefix || path.startsWith(`${prefix}/`))
        || path === 'v1/ingest/url'
        || path === 'ingest/url'
        || path === 'api/v1/regulatory/ingest/url'
        || path === 'api/v1/regulatory/v1/ingest/url'
        || path === 'api/v1/ingest/csv'
        || path === 'ingest/csv';
}
