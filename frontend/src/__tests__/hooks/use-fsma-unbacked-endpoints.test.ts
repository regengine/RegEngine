/**
 * #2980 — the FSMA hooks must not call `wizard/*`, which no backend serves.
 *
 * `useFTLCategories`, `useCheckApplicability` and `useCheckExemptions` fetched
 * `${GRAPH_API_BASE}/wizard/{ftl-categories,applicability,exemptions}`. With
 * GRAPH_API_BASE = '/api/fsma' in the browser, src/app/api/fsma/[...path]/route.ts
 * forwards anything outside its graph prefix table (compliance/, traceability/,
 * recall/, science/, metrics/, gaps, export/) to COMPLIANCE_SERVICE_URL
 * verbatim — so those three land on `${COMPLIANCE_URL}/wizard/...`.
 *
 * No such route is registered anywhere in the backend:
 *
 *   $ grep -rnE '(get|post)\(\s*"[^"]*(wizard|applicability|exemption)' \
 *       --include=*.py services/ server/
 *   (no route decorators)
 *
 * This is absence, not production gating: unlike the `graph` router — which is
 * listed in _EXPERIMENTAL_ROUTERS in server/main.py and is therefore 404 in
 * production unless ENABLE_EXPERIMENTAL_ROUTERS=true — there is no wizard
 * router to enable, so the paths 404 in every environment and under every flag.
 *
 * The readiness wizard that DOES exist (services/ingestion/app/readiness_router.py,
 * APIRouter(prefix="/api/v1/readiness")) is a different feature: it serves
 * /assessment, /checklist and /gaps, answers "how mature is this tenant's
 * compliance programme" from live tenant data, and requires the
 * `readiness.read` permission — it cannot answer "does FSMA 204 apply to me".
 * So the hooks could not be repointed at it either.
 *
 * They also had zero callers. The FTL applicability flow that actually shipped
 * is /onboarding/setup/ftl-check, which computes coverage, exclusions and
 * required CTEs client-side from the static catalog in src/lib/ftl-data.ts —
 * correct for regulatory reference data, and needing no backend at all.
 *
 * The four `drift/*` hooks are deliberately NOT covered here: they are equally
 * unbacked, but they still have live UI consumers, so removing them is a
 * product decision rather than dead-code deletion. See the issue.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const HOOKS_SRC = readFileSync(
    path.resolve(__dirname, '../../hooks/use-fsma.ts'),
    'utf8',
);

/** Hook names removed by #2980. */
const REMOVED_WIZARD_HOOKS = [
    'useFTLCategories',
    'useCheckApplicability',
    'useCheckExemptions',
] as const;

/** Path segments that reach a backend which registers nothing for them. */
const UNBACKED_WIZARD_PATHS = [
    '/wizard/ftl-categories',
    '/wizard/applicability',
    '/wizard/exemptions',
] as const;

describe('#2980 use-fsma must not target unbacked wizard endpoints', () => {
    it.each(UNBACKED_WIZARD_PATHS)(
        'never builds a request URL for %s',
        (unbackedPath) => {
            expect(HOOKS_SRC).not.toContain(unbackedPath);
        },
    );

    it('contains no `wizard/` path segment at all', () => {
        // Guards the whole class, not just the three known spellings: any new
        // `wizard/...` path added here would hit the same missing router.
        expect(HOOKS_SRC).not.toMatch(/\/wizard\//);
    });

    it.each(REMOVED_WIZARD_HOOKS)('no longer exports %s', (hookName) => {
        expect(HOOKS_SRC).not.toMatch(
            new RegExp(`export\\s+function\\s+${hookName}\\b`),
        );
    });

    it('still exports the FSMA hooks that DO have a backend', () => {
        // Deleting dead code must not take live hooks with it. Each of these
        // resolves through the /api/fsma proxy onto a real graph sub-router
        // (services/graph/app/routes.py:59-63).
        for (const live of [
            'useForwardTrace',
            'useBackwardTrace',
            'useFSMADashboard',
            'useComplianceScore',
        ]) {
            expect(HOOKS_SRC).toMatch(
                new RegExp(`export\\s+function\\s+${live}\\b`),
            );
        }
    });
});

/**
 * #2980 group 1 — `drift/*`. Same absence proof as the wizard group (no
 * drift route decorator exists anywhere in services/ or server/), but these
 * four hooks had live consumers: DriftAlertsWidget on /fsma and the
 * /admin/alerts page were permanently stuck in their failure states in every
 * environment. Product call per the issue: delete the feature surface rather
 * than ship a monitoring panel that has never monitored anything; git
 * history preserves the UI if a drift backend is ever built.
 */
const REMOVED_DRIFT_HOOKS = [
    'useDriftAlerts',
    'useDriftHealth',
    'useSupplierHealth',
    'useAcknowledgeAlert',
] as const;

describe('#2980 use-fsma must not target unbacked drift endpoints', () => {
    it('contains no `drift/` path segment at all', () => {
        expect(HOOKS_SRC).not.toMatch(/\/drift\//);
    });

    it.each(REMOVED_DRIFT_HOOKS)('no longer exports %s', (hookName) => {
        expect(HOOKS_SRC).not.toMatch(
            new RegExp(`export\\s+function\\s+${hookName}\\b`),
        );
    });
});
