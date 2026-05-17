# Authenticated Screen State Coverage

This is the living checklist for authenticated product and developer screens. Keep it in sync with protected Next.js routes whenever adding or moving a screen.

`C` means the route has a documented requirement in this matrix and is covered by the automated guardrail that enforces route coverage plus loading/error fallback wiring. It does not, by itself, mean the exact API failure mode is simulated for that screen. Behavior-specific tests should be linked from feature docs or the authorization/state cross-reference when they exist. `N/A` means the state is not applicable to that route because the screen has no server-side form submission or optimistic mutation.

## Required States

| State ID | Required user experience |
|---|---|
| Empty | Zero records render helpful next-step UI instead of a blank panel. |
| Loading | A skeleton or spinner keeps the page frame stable while data arrives. |
| Error 500 | Server failures show a friendly message, retry action, and no raw stack or implementation detail. |
| Offline | Browser/network loss shows a clear offline indicator or graceful local mode. |
| Partial failure | Loaded sections stay visible when another collection/widget fails. |
| 401 expired | Expired sessions redirect to login with the intended return route and warn before discarding user-entered work where applicable. |
| 403 revoked | Revoked permissions show a clear access message instead of a generic crash. |
| 429 limited | Rate limits show backoff feedback, including Retry-After timing when available. |
| Validation | Server-side validation errors render inline near the relevant field or row. |
| Optimistic rollback | Optimistic changes roll back on failure and explain what happened. |

## Screen Matrix

| Route | Empty | Loading | Error 500 | Offline | Partial failure | 401 expired | 403 revoked | 429 limited | Validation | Optimistic rollback | Test |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `/admin` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/admin/alerts` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/admin/api-console` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/api-keys` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/audit` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/compliance` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/compliance/labels` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/compliance/profile` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/compliance/snapshots` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/compliance/status` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/compliance/traceability-plan` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/controls` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/alerts` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/audit-log` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/compliance` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/export-jobs` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/heartbeat` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/inflow-lab` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/integrations` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/issues` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/notifications` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/products` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/recall-drills` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/recall-report` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/recall-response` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/receiving` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/scan` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/settings` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/suppliers` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/dashboard/team` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/codegen` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs/auth` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs/changelog` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs/endpoints` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs/errors` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs/sdks` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/docs/webhooks` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/keys` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/playground` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/developer/portal/usage` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/exceptions` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/fsma` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/fsma/assessment` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/fsma/field-capture` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/fsma/integration` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/fsma/market` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/identity` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/ingest` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/ingest/curation` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/ingest/results/[id]` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/onboarding` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/onboarding/bulk-upload` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/onboarding/setup` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/onboarding/setup/facility` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/onboarding/setup/ftl-check` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/onboarding/setup/welcome` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/records` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/requests` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/requests/[id]` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/review` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/rules` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/settings` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/settings/notifications` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/settings/profile` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/settings/security` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/settings/support` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/settings/users` | C | C | C | C | C | C | C | C | C | C | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/sysadmin` | C | C | C | C | C | C | C | C | C | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |
| `/trace` | C | C | C | C | C | C | C | C | N/A | N/A | `src/__tests__/pages/authenticated-screen-states.test.ts` |

## Maintenance Rule

When adding a protected page, update this matrix in the same change as the route. The guardrail test discovers authenticated pages from the shared route prefixes plus developer portal gates, so a new protected screen without a row, loading fallback, or error fallback fails CI.

## Evidence Limits

The guardrail test intentionally catches missing documentation and missing route-level `loading.tsx` / `error.tsx` fallbacks. It is not a substitute for page-level tests that mock `401`, `403`, `429`, validation payloads, partial widget failures, offline mode, or failed optimistic mutations. Add those tests beside the feature code when a screen owns the corresponding behavior, and cross-reference them from the relevant security or QA report.
