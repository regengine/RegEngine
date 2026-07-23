/**
 * Design-partner demo smoke — passwordless edition.
 *
 * The app has no password login (POST /api/admin/auth/login is gone). Auth here
 * runs in one of two modes, decided by environment:
 *
 * 1. Email-OTP mode (local full stack only). Requires DEMO_SMOKE_EMAIL and
 *    REGENGINE_E2E_EMAIL_OUTBOX, with the backend started with
 *    REGENGINE_E2E_MODE=true so the challenges router writes OTPs to the
 *    outbox fixture (services/admin/app/auth/challenges_router.py). The spec
 *    drives the real /login UI and hydrates the opaque
 *    __Host-regengine_session cookie. E2E mode is hard-forbidden in
 *    production, so this mode can never run against regengine.co.
 *
 * 2. API-key mode (live targets, e.g. https://regengine.co from CI). OTPs go
 *    to a real inbox there, so completing a user login is not automatable.
 *    Instead the spec (a) probes the passwordless challenge surface —
 *    POST /auth/challenges must accept and a wrong code must be rejected —
 *    and (b) runs the workbench loop with an inflow-scoped API key:
 *    DEMO_SMOKE_API_KEY directly, or one minted via ADMIN_MASTER_KEY.
 *    DEMO_SMOKE_TENANT_ID is required in this mode (in OTP mode the tenant
 *    comes from the authenticated session). The Inflow Lab page and supplier
 *    portal are public routes, so the UI portion works without a user session.
 */
import { expect, test, type APIResponse, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { loginWithEmailOtp } from './auth-helpers';

const DEMO_EMAIL = process.env.DEMO_SMOKE_EMAIL || process.env.TEST_USER_EMAIL || '';
const DEMO_API_KEY = process.env.DEMO_SMOKE_API_KEY || '';
const DEMO_ADMIN_MASTER_KEY =
    process.env.DEMO_SMOKE_ADMIN_MASTER_KEY || process.env.ADMIN_MASTER_KEY || '';
const DEMO_TENANT_ID = process.env.DEMO_SMOKE_TENANT_ID || '';
const OTP_OUTBOX = process.env.REGENGINE_E2E_EMAIL_OUTBOX || '';
const COMMIT_MODE = process.env.DEMO_SMOKE_COMMIT_MODE || 'preflight';
const ALLOW_PRODUCTION_EVIDENCE = process.env.DEMO_SMOKE_ALLOW_PRODUCTION_EVIDENCE === 'true'
    || process.env.DEMO_SMOKE_ALLOW_COMMIT === 'true';

const OTP_MODE = Boolean(DEMO_EMAIL && OTP_OUTBOX);

const MESSY_SUPPLIER_CSV = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-DEMO-SMOKE-001,Romaine Lettuce,104,cases,Valley Fresh Farms,2026-04-26T15:20:00Z,,,HARV-SMOKE-001
cooling,TLC-DEMO-SMOKE-001,Romaine Lettuce,104,cases,Salinas Cooling Hub,2026-04-26T18:12:00Z,,,COOL-SMOKE-001
initial_packing,TLC-DEMO-SMOKE-001,Romaine Lettuce,103,cases,Salinas Packhouse,2026-04-26T20:12:00Z,,,PACK-SMOKE-001
shipping,TLC-DEMO-SMOKE-001,Romaine Lettuce,103,cases,Salinas Packout Dock,2026-04-26T22:41:00Z,Salinas Packhouse,,BOL-SMOKE-001
receiving,TLC-DEMO-SMOKE-001,Romaine Lettuce,103,cases,,2026-04-27T02:04:00Z,Salinas Packout Dock,,REC-SMOKE-001`;

type JsonObject = Record<string, unknown>;
type AuthMode = 'email_otp' | 'api_key';

function baseOrigin(): string {
    return new URL(
        process.env.DEMO_SMOKE_BASE_URL || process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001',
    ).origin;
}

async function authenticate(page: Page, context: BrowserContext): Promise<{ tenantId: string; authMode: AuthMode }> {
    if (OTP_MODE) {
        await loginWithEmailOtp(page, context, DEMO_EMAIL);
        const session = await expectJson<JsonObject>(await page.request.get('/api/session'), 'session');
        expect(session.authenticated, 'OTP login should hydrate an authenticated session').toBe(true);
        expect(session.auth_method, 'session should be passwordless email OTP').toBe('email_otp');
        expect(session.tenant_id, 'passwordless session should resolve a tenant_id').toEqual(expect.any(String));
        return { tenantId: String(session.tenant_id), authMode: 'email_otp' };
    }

    expect(
        DEMO_TENANT_ID,
        'Set DEMO_SMOKE_TENANT_ID to run the demo smoke in api-key mode (no OTP outbox available).',
    ).toBeTruthy();
    await verifyPasswordlessSurface(page);
    return { tenantId: DEMO_TENANT_ID, authMode: 'api_key' };
}

/**
 * Live-target stand-in for a full OTP login: the challenge endpoint must
 * accept (202 + challenge_id — anti-enumeration means a synthetic address
 * gets the same response and no email is dispatched) and a wrong code must
 * be rejected with 401.
 */
async function verifyPasswordlessSurface(page: Page): Promise<void> {
    const probeEmail = `demo-smoke-probe+${Date.now()}@example.com`;
    const challenge = await expectJson<JsonObject>(
        await page.request.post('/api/admin/auth/challenges', { data: { email: probeEmail } }),
        'passwordless challenge create',
    );
    expect(challenge.challenge_id, 'challenge create should return a challenge_id').toEqual(expect.any(String));

    const badVerify = await page.request.post(
        `/api/admin/auth/challenges/${challenge.challenge_id}/verify`,
        { data: { code: '000000' } },
    );
    expect(badVerify.status(), 'wrong OTP must be rejected').toBe(401);
}

async function csrfHeaders(context: BrowserContext): Promise<Record<string, string>> {
    const cookies = await context.cookies();
    const csrf = cookies.find((cookie) => cookie.name === 're_csrf')?.value;
    expect(csrf, 'GET /api/session should set a readable CSRF cookie').toBeTruthy();
    return {
        'content-type': 'application/json',
        'x-csrf-token': csrf || '',
    };
}

async function postWithCsrf(
    page: Page,
    context: BrowserContext,
    url: string,
    data: unknown,
    extraHeaders: Record<string, string> = {},
) {
    return page.request.post(url, {
        headers: {
            ...(await csrfHeaders(context)),
            ...extraHeaders,
        },
        data,
    });
}

async function setSessionApiKey(
    page: Page,
    context: BrowserContext,
    apiKey: string,
    tenantId: string,
): Promise<void> {
    await expectJson<JsonObject>(
        await page.request.post('/api/session', {
            headers: {
                ...(await csrfHeaders(context)),
                // POST /api/session enforces an Origin allowlist in production
                // (RE-SEC-003); APIRequestContext does not send Origin on its own.
                origin: baseOrigin(),
            },
            data: { api_key: apiKey, tenant_id: tenantId },
        }),
        'api key cookie bootstrap',
    );
}

async function bootstrapApiKey(
    page: Page,
    context: BrowserContext,
    tenantId: string,
    runPrefix: string,
): Promise<string> {
    // CSRF double-submit cookies are issued on the first GET, for both
    // authenticated and anonymous visitors.
    await page.request.get('/api/session');

    if (DEMO_API_KEY) {
        await setSessionApiKey(page, context, DEMO_API_KEY, tenantId);
        return DEMO_API_KEY;
    }

    expect(
        DEMO_ADMIN_MASTER_KEY,
        'Set DEMO_SMOKE_API_KEY or ADMIN_MASTER_KEY to provision an ingestion API key for demo smoke.',
    ).toBeTruthy();

    const created = await expectJson<JsonObject>(
        await postWithCsrf(
            page,
            context,
            '/api/admin/v1/admin/keys',
            {
                name: `${runPrefix} Demo Smoke Key`,
                tenant_id: tenantId,
                scopes: ['inflow.read', 'inflow.write', 'webhooks.ingest'],
            },
            { 'x-admin-key': DEMO_ADMIN_MASTER_KEY },
        ),
        'demo smoke API key create',
    );

    const apiKey = String(created.api_key || '');
    expect(apiKey, 'API key creation should return a raw key once').toBeTruthy();

    await setSessionApiKey(page, context, apiKey, tenantId);
    return apiKey;
}

async function expectJson<T>(response: APIResponse, label: string): Promise<T> {
    if (!response.ok()) {
        throw new Error(`${label} failed with ${response.status()}: ${await response.text()}`);
    }
    return await response.json() as T;
}

async function writeSummary(testInfo: TestInfo, summary: JsonObject) {
    const body = JSON.stringify(summary, null, 2);
    await testInfo.attach('demo-smoke-summary', { body, contentType: 'application/json' });
    await writeFile(testInfo.outputPath('demo-smoke-summary.json'), body);
}

test.describe('Design-partner demo smoke', () => {
    test('runs the Inflow Workbench preflight loop and supplier portal handoff', async ({ page, context }, testInfo) => {
        test.skip(
            !OTP_MODE && !DEMO_API_KEY && !DEMO_ADMIN_MASTER_KEY,
            'Set DEMO_SMOKE_EMAIL + REGENGINE_E2E_EMAIL_OUTBOX (email-OTP mode) or '
            + 'DEMO_SMOKE_API_KEY / ADMIN_MASTER_KEY + DEMO_SMOKE_TENANT_ID (api-key mode) to run the demo smoke.',
        );
        expect(
            COMMIT_MODE !== 'production_evidence' || ALLOW_PRODUCTION_EVIDENCE,
            'production_evidence demo smoke requires DEMO_SMOKE_ALLOW_PRODUCTION_EVIDENCE=true',
        ).toBe(true);

        const runPrefix = `demo-smoke-${Date.now()}`;
        const { tenantId, authMode } = await authenticate(page, context);
        const apiKey = await bootstrapApiKey(page, context, tenantId, runPrefix);

        const session = await expectJson<JsonObject>(await page.request.get('/api/session'), 'session state');
        expect(session.has_api_key, 'ingestion API key cookie should be set').toBe(true);
        expect(String(session.tenant_id || ''), 'session should carry the demo tenant').toBe(tenantId);

        await page.goto('/tools/inflow-lab');
        await expect(page.getByRole('button', { name: /Data feeder/i })).toBeVisible({ timeout: 20_000 });
        const tenantInput = page.getByLabel(/^Tenant$/i).first();
        if (await tenantInput.isVisible()) {
            await tenantInput.fill(tenantId);
        }
        await page.getByRole('button', { name: /Data feeder/i }).click();
        await page.getByLabel('Inbound CSV data').fill(MESSY_SUPPLIER_CSV);
        await page.getByRole('button', { name: /Evaluate data/i }).click();
        await expect(page.getByText('Events evaluated', { exact: true })).toBeVisible({ timeout: 30_000 });
        await expect(page.getByText('Backend readiness')).toBeVisible({ timeout: 30_000 });
        await page.getByRole('button', { name: /Save test run/i }).click();
        await expect(page.getByText(/Persisted as|Saved/i).first()).toBeVisible({ timeout: 30_000 });

        const sandboxResult = await expectJson<JsonObject>(
            await page.request.post('/api/ingestion/api/v1/sandbox/evaluate', {
                data: { csv: MESSY_SUPPLIER_CSV },
            }),
            'sandbox evaluation',
        );
        expect(sandboxResult.total_events).toBe(5);
        expect(
            Number(sandboxResult.total_kde_errors) + Number(sandboxResult.total_rule_failures),
            'messy demo file should produce remediation work',
        ).toBeGreaterThan(0);

        const savedRun = await expectJson<JsonObject>(
            await postWithCsrf(page, context, '/api/ingestion/api/v1/inflow-workbench/runs', {
                tenant_id: tenantId,
                source: 'demo-smoke',
                csv: MESSY_SUPPLIER_CSV,
                result: sandboxResult,
            }),
            'workbench run save',
        );
        expect(savedRun.run_id).toEqual(expect.stringMatching(/^run-/));
        expect((savedRun.readiness as JsonObject).score).toEqual(expect.any(Number));
        expect(savedRun.fix_queue).toEqual(expect.any(Array));
        expect((savedRun.fix_queue as unknown[]).length).toBeGreaterThan(0);

        const readiness = await expectJson<JsonObject>(
            await page.request.get(`/api/ingestion/api/v1/inflow-workbench/readiness/summary?tenant_id=${tenantId}`),
            'readiness summary',
        );
        expect(readiness.source).not.toBe('none');
        expect(readiness.score).toEqual(expect.any(Number));

        const fixQueue = await expectJson<unknown[]>(
            await page.request.get(`/api/ingestion/api/v1/inflow-workbench/fix-queue?tenant_id=${tenantId}`),
            'fix queue',
        );
        expect(fixQueue.length).toBeGreaterThan(0);

        const commitGate = await expectJson<JsonObject>(
            await postWithCsrf(page, context, '/api/ingestion/api/v1/inflow-workbench/commit-gate', {
                mode: COMMIT_MODE,
                tenant_id: tenantId,
                result: sandboxResult,
                authenticated: true,
                persisted: true,
                provenance_attached: true,
                unresolved_fix_count: fixQueue.length,
            }),
            'commit gate',
        );
        expect(commitGate.mode).toBe(COMMIT_MODE);
        expect(commitGate.export_eligible).toBe(COMMIT_MODE === 'production_evidence' && fixQueue.length === 0);

        const profile = await expectJson<JsonObject>(
            await postWithCsrf(page, context, `/api/ingestion/api/v1/integrations/profiles/${tenantId}`, {
                display_name: `${runPrefix} FreshPack CSV`,
                source_type: 'csv',
                default_cte_type: 'shipping',
                status: 'active',
                confidence: 0.91,
                supplier_name: `${runPrefix} FreshPack Central`,
                notes: 'Created by automated design-partner demo smoke.',
                field_mapping: {
                    cte_type: 'type',
                    traceability_lot_code: 'lot',
                    product_description: 'sku',
                    quantity: 'qty',
                    unit_of_measure: 'uom',
                    ship_from_location: 'from',
                    ship_to_location: 'to',
                    reference_document: 'bol_number',
                    timestamp: 'event_time',
                },
            }),
            'integration profile create',
        );
        const profileId = String(profile.profile_id);
        expect(profileId).toEqual(expect.stringMatching(/^prof_/));

        const preview = await expectJson<JsonObject>(
            await postWithCsrf(page, context, `/api/ingestion/api/v1/integrations/profiles/${tenantId}/${profileId}/preview`, {
                events: [{
                    type: 'shipping',
                    lot: 'TLC-DEMO-SMOKE-001',
                    sku: 'Romaine Lettuce',
                    qty: 103,
                    uom: 'cases',
                    from: 'Salinas Packhouse',
                    to: 'Bay Area DC',
                    bol_number: 'BOL-SMOKE-001',
                    event_time: '2026-04-26T22:41:00Z',
                }],
            }),
            'integration profile preview',
        );
        expect(preview.mapped).toBe(1);
        expect(((preview.events as JsonObject[])[0] || {})._integration_profile_id).toBe(profileId);

        const portalLink = await expectJson<JsonObject>(
            await postWithCsrf(page, context, '/api/ingestion/api/v1/portal/links', {
                tenant_id: tenantId,
                supplier_name: `${runPrefix} FreshPack Central`,
                supplier_email: `supplier+${runPrefix}@example.com`,
                expires_days: 7,
                integration_profile_id: profileId,
            }),
            'supplier portal link create',
        );
        expect(portalLink.portal_id).toEqual(expect.any(String));

        const portalPath = new URL(String(portalLink.portal_url)).pathname;
        await page.goto(portalPath);
        await expect(page.getByText(`${runPrefix} FreshPack Central`).first()).toBeVisible({ timeout: 20_000 });
        await expect(page.getByText(`${runPrefix} FreshPack CSV`).first()).toBeVisible({ timeout: 20_000 });
        await expect(page.getByText(/91% mapping confidence/i)).toBeVisible({ timeout: 20_000 });

        await writeSummary(testInfo, {
            base_url: testInfo.project.use.baseURL,
            auth_mode: authMode,
            tenant_id: tenantId,
            workbench_run_id: savedRun.run_id,
            readiness_score: readiness.score,
            fix_queue_count: fixQueue.length,
            commit_gate: commitGate,
            integration_profile_id: profileId,
            portal_id: portalLink.portal_id,
            portal_path: portalPath,
            api_key_prefix: apiKey.slice(0, 12),
        });
    });
});
