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

// Per-tool override: comma-separated /tools slugs enabled WITHOUT turning on
// the whole experimental surface, e.g.
// NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS=inflow-lab,inflow-lab-dashboard-preview.
// Only useful for tools whose data path does not need the experimental backend
// routers: the Inflow Lab pages talk to the standalone Inflow Lab service via
// the /api/inflow-lab proxy (INFLOW_LAB_SERVICE_URL), so they can be enabled
// alone in production while ENABLE_EXPERIMENTAL_ROUTERS stays off.
export function isExperimentalToolEnabled(slug: string): boolean {
    if (experimentalFeaturesEnabled()) return true;
    const raw = process.env.NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS ?? '';
    return raw
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean)
        .includes(slug);
}

/** /tools/<slug> pages whose core flow calls an experimental backend router. */
export const EXPERIMENTAL_TOOL_SLUGS: ReadonlySet<string> = new Set([
    'ask', // NLP query (nlp router)
    'knowledge-graph', // NLP traceability query (nlp router)
    'label-scanner', // vision analyze-label (label_vision router)
    'inflow-lab', // sandbox evaluate (sandbox router)
    'inflow-lab-dashboard-preview', // mounts the same sandbox-backed dashboard
]);

function experimentalToolSlug(href: string): string | null {
    const match = href.match(/^\/tools\/([^/?#]+)/);
    return match !== null && EXPERIMENTAL_TOOL_SLUGS.has(match[1]) ? match[1] : null;
}

export function isExperimentalToolHref(href: string): boolean {
    return experimentalToolSlug(href) !== null;
}

/** True when the href points at an experimental tool that is NOT enabled. */
export function isExperimentalToolHrefHidden(href: string): boolean {
    const slug = experimentalToolSlug(href);
    return slug !== null && !isExperimentalToolEnabled(slug);
}

/** Drop links to experimental tools that are not enabled; pass through otherwise. */
export function filterExperimentalToolLinks<T extends { href: string }>(tools: T[]): T[] {
    return tools.filter((tool) => !isExperimentalToolHrefHidden(tool.href));
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

/** Drop links to hidden experimental tools AND gated app pages when the flag is off. */
export function filterExperimentalLinks<T extends { href: string }>(links: T[]): T[] {
    return links.filter((link) => {
        if (isExperimentalToolHrefHidden(link.href)) return false;
        // Non-tool experimental pages depend on the experimental backend
        // routers, so they stay behind the global flag only.
        const path = link.href.split(/[?#]/)[0];
        if (EXPERIMENTAL_PAGE_HREFS.has(path)) return experimentalFeaturesEnabled();
        return true;
    });
}
