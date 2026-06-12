// Single gate for frontend surfaces whose backend routers are AUTO-DISABLED
// in production (_EXPERIMENTAL_ROUTERS in server/main.py): nlp, graph, and the
// experimental ingestion routers (sandbox, discovery, audit, label_vision, …).
//
// Default (unset / anything but "1"/"true") = features hidden. Set
// NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES=true on the frontend alongside
// ENABLE_EXPERIMENTAL_ROUTERS=true on the backend to expose them.

export function experimentalFeaturesEnabled(): boolean {
    const value = process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES;
    return value === '1' || value === 'true';
}

/** /tools/<slug> pages whose core flow calls an experimental backend router. */
export const EXPERIMENTAL_TOOL_SLUGS: ReadonlySet<string> = new Set([
    'ask', // NLP query (nlp router)
    'knowledge-graph', // NLP traceability query (nlp router)
    'label-scanner', // vision analyze-label (label_vision router)
    'inflow-lab', // sandbox evaluate (sandbox router)
    'inflow-lab-dashboard-preview', // mounts the same sandbox-backed dashboard
]);

export function isExperimentalToolHref(href: string): boolean {
    const match = href.match(/^\/tools\/([^/?#]+)/);
    return match !== null && EXPERIMENTAL_TOOL_SLUGS.has(match[1]);
}

/** Drop links to experimental tools when the flag is off; pass through otherwise. */
export function filterExperimentalToolLinks<T extends { href: string }>(tools: T[]): T[] {
    if (experimentalFeaturesEnabled()) return tools;
    return tools.filter((tool) => !isExperimentalToolHref(tool.href));
}

/** Non-/tools pages gated behind the flag (each has its own page-level guard). */
export const EXPERIMENTAL_PAGE_HREFS: ReadonlySet<string> = new Set([
    '/dashboard/inflow-lab', // sandbox-backed Inflow Lab dashboard
    '/dashboard/scan', // launcher (QR + link) for /fsma/field-capture
    '/ingest/curation', // discovery-router curation queue
    '/fsma', // graph-service readiness dashboard
    '/fsma/field-capture', // vision analyze-label capture (label_vision router)
]);

export function isExperimentalHref(href: string): boolean {
    const path = href.split(/[?#]/)[0];
    return isExperimentalToolHref(href) || EXPERIMENTAL_PAGE_HREFS.has(path);
}

/** Drop links to experimental tools AND gated app pages when the flag is off. */
export function filterExperimentalLinks<T extends { href: string }>(links: T[]): T[] {
    if (experimentalFeaturesEnabled()) return links;
    return links.filter((link) => !isExperimentalHref(link.href));
}
