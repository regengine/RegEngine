// #2757 — single source of truth for every "try it yourself" CTA on the
// marketing site (compare pages, homepage).
//
// Why this is not a plain constant: a CTA must never promise a destination
// the deployment cannot serve.
//
// PR #2730 hit exactly this: it repointed the dead homepage sandbox hash
// anchors at a dashboard page but left the sandbox prose above the buttons,
// so the copy promised a CSV sandbox while the button opened a dashboard.
// Resolving copy and destination together, from one place, is what stops
// those two drifting apart again. The old /demo route was removed with the
// synthetic workspace cleanup.
//
// #3825 note — the backend side of this comment is no longer what it was.
// Router exposure now lives in server/router_policy.py, not main.py, and
// production rejects ENABLE_EXPERIMENTAL_ROUTERS outright: optional routers
// are promoted by name into PRODUCTION_ENABLED_ROUTERS. The `sandbox` router
// was promoted that way and POST /api/v1/sandbox/evaluate is live in
// production, serving the Inflow Lab CSV checker. That does NOT bring back a
// public /sandbox page — that route stays retired and this CTA still points
// at /ingest. Only the persisted /share endpoints remain unpromoted, under
// the separate `sandbox_share` owner.

import { isExperimentalToolEnabled } from '@/lib/experimental-features';

/** Slug used for the per-tool override; matches the backend router name. */
export const SANDBOX_SLUG = 'sandbox';

export interface SandboxCta {
    /** True when the sandbox surface is enabled on this deployment. */
    enabled: boolean;
    href: string;
    label: string;
    /** Body copy. Never promises CSV evaluation unless the sandbox is live. */
    blurb: string;
}

export function isSandboxEnabled(): boolean {
    return isExperimentalToolEnabled(SANDBOX_SLUG);
}

export function sandboxCta(): SandboxCta {
    // The public /sandbox route was retired. The CTA never links to it, even
    // when the experimental sandbox router is enabled on the backend.
    return {
        enabled: false,
        href: '/ingest',
        label: 'Upload your CSV',
        blurb:
            'Upload your own traceability records as CSV to check them against FSMA 204.',
    };
}
