// #2757 — single source of truth for every "try it yourself" CTA on the
// marketing site (compare pages, homepage).
//
// Why this is not a plain constant: the free CSV sandbox is served by the
// `sandbox` router, which server/main.py lists in _EXPERIMENTAL_ROUTERS and
// auto-disables in production unless ENABLE_EXPERIMENTAL_ROUTERS=true. When
// the router is not mounted, POST /api/v1/sandbox/evaluate 404s, so a CTA
// promising "results in under 60 seconds" would be a claim the deployment
// cannot honor.
//
// PR #2730 hit exactly this: it repointed the dead homepage sandbox hash
// anchors at a dashboard page but left the sandbox prose above the buttons,
// so the copy promised a CSV sandbox while the button opened a dashboard.
// Resolving copy and destination together, from one flag, is what stops
// those two drifting apart again. The fallback destination is /walkthrough;
// the old /demo route was removed with the synthetic workspace cleanup.
//
// Enabling NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES (or listing 'sandbox' in
// NEXT_PUBLIC_ENABLED_EXPERIMENTAL_TOOLS) alongside the backend's
// ENABLE_EXPERIMENTAL_ROUTERS lights up the whole funnel with no code change.

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
    if (isSandboxEnabled()) {
        return {
            enabled: true,
            href: '/sandbox',
            label: 'Try the Sandbox',
            blurb:
                'Drop your CSV in the sandbox and get FSMA 204 compliance results in under 60 seconds. No signup required.',
        };
    }
    return {
        enabled: false,
        href: '/walkthrough',
        label: 'See the walkthrough',
        blurb:
            'Walk the FSMA 204 records-request workflow step by step. No signup required.',
    };
}
