import { expect, test, type APIResponse, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { writeFile } from 'node:fs/promises';

const DEMO_EMAIL = process.env.DEMO_SMOKE_EMAIL || process.env.TEST_USER_EMAIL || '';
const DEMO_PASSWORD = process.env.DEMO_SMOKE_PASSWORD || process.env.TEST_PASSWORD || '';
const COMMIT_MODE = process.env.DEMO_SMOKE_COMMIT_MODE || 'preflight';
const ALLOW_PRODUCTION_EVIDENCE = process.env.DEMO_SMOKE_ALLOW_PRODUCTION_EVIDENCE === 'true'
    || process.env.DEMO_SMOKE_ALLOW_COMMIT === 'true';

const MESSY_SUPPLIER_CSV = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-DEMO-SMOKE-001,Romaine Lettuce,104,cases,Valley Fresh Farms,2026-04-26T15:20:00Z,,,HARV-SMOKE-001
cooling,TLC-DEMO-SMOKE-001,Romaine Lettuce,104,cases,Salinas Cooling Hub,2026-04-26T18:12:00Z,,,COOL-SMOKE-001
initial_packing,TLC-DEMO-SMOKE-001,Romaine Lettuce,103,cases,Salinas Packhouse,2026-04-26T20:12:00Z,,,PACK-SMOKE-001
shipping,TLC-DEMO-SMOKE-001,Romaine Lettuce,103,cases,Salinas Packout Dock,2026-04-26T22:41:00Z,Salinas Packhouse,,BOL-SMOKE-001
receiving,TLC-DEMO-SMOKE-001,Romaine Lettuce,103,cases,,2026-04-27T02:04:00Z,Salinas Packout Dock,,REC-SMOKE-001`;

type JsonObject = Record<string, unknown>;

async function login(page: Page): Promise<{ tenantId: string }> {
    const loginResponse = await expectJson<JsonObject>(
        await page.request.post('/api/admin/auth/login', {
            data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
        }),
        'admin login',
    );
    expect(loginResponse.access_token, 'admin login should return an access token').toEqual(expect.any(String));
    expect(loginResponse.tenant_id, 'admin login should return a tenant_id').toEqual(expect.any(String));

    await expectJson<JsonObject>(
        await page.request.post('/api/session', {
            data: {
                access_token: loginResponse.access_token,
                tenant_id: loginResponse.tenant_id,
                user: loginResponse.user,
            },
        }),
        'session cookie bootstrap',
    );

    const response = await page.request.get('/api/session');
    const session = await expectJson<JsonObject>(response, 'session');
    expect(session.authenticated, 'demo account should be authenticated').toBe(true);
    expect(session.tenant_id, 'demo account should have a tenant_id').toEqual(expect.any(String));
    return { tenantId: String(session.tenant_id) };
}

async function csrfHeaders(context: BrowserContext): Promise<Record<string, string>> {
    const cookies = await context.cookies();
    const csrf = cookies.find((cookie) => cookie.name === 're_csrf')?.value;
    expect(csrf, 'login should set a readable CSRF cookie').toBeTruthy();
    return {
        'content-type': 'application/json',
        'x-csrf-token': csrf || '',
    };
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
        test.skip(!DEMO_EMAIL || !DEMO_PASSWORD, 'Set DEMO_SMOKE_EMAIL and DEMO_SMOKE_PASSWORD to run the live demo smoke.');
        expect(
            COMMIT_MODE !== 'production_evidence' || ALLOW_PRODUCTION_EVIDENCE,
            'production_evidence demo smoke requires DEMO_SMOKE_ALLOW_PRODUCTION_EVIDENCE=true',
        ).toBe(true);

        const runPrefix = `demo-smoke-${Date.now()}`;
        const { tenantId } = await login(page);
        const headers = await csrfHeaders(context);

        await page.goto('/tools/inflow-lab');
        await expect(page.getByRole('button', { name: /Data feeder/i })).toBeVisible({ timeout: 20_000 });
        const defaultTenantInput = page.locator('input[value="mock-tenant"]').first();
        if (await defaultTenantInput.count()) {
            await defaultTenantInput.fill(tenantId);
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
            await page.request.post('/api/ingestion/api/v1/inflow-workbench/runs', {
                headers,
                data: {
                    tenant_id: tenantId,
                    source: 'demo-smoke',
                    csv: MESSY_SUPPLIER_CSV,
                    result: sandboxResult,
                },
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
            await page.request.post('/api/ingestion/api/v1/inflow-workbench/commit-gate', {
                headers,
                data: {
                    mode: COMMIT_MODE,
                    tenant_id: tenantId,
                    result: sandboxResult,
                    authenticated: true,
                    persisted: true,
                    provenance_attached: true,
                    unresolved_fix_count: fixQueue.length,
                },
            }),
            'commit gate',
        );
        expect(commitGate.mode).toBe(COMMIT_MODE);
        expect(commitGate.export_eligible).toBe(COMMIT_MODE === 'production_evidence' && fixQueue.length === 0);

        const profile = await expectJson<JsonObject>(
            await page.request.post(`/api/ingestion/api/v1/integrations/profiles/${tenantId}`, {
                headers,
                data: {
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
                },
            }),
            'integration profile create',
        );
        const profileId = String(profile.profile_id);
        expect(profileId).toEqual(expect.stringMatching(/^prof_/));

        const preview = await expectJson<JsonObject>(
            await page.request.post(`/api/ingestion/api/v1/integrations/profiles/${tenantId}/${profileId}/preview`, {
                headers,
                data: {
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
                },
            }),
            'integration profile preview',
        );
        expect(preview.mapped).toBe(1);
        expect(((preview.events as JsonObject[])[0] || {})._integration_profile_id).toBe(profileId);

        const portalLink = await expectJson<JsonObject>(
            await page.request.post('/api/ingestion/api/v1/portal/links', {
                headers,
                data: {
                    tenant_id: tenantId,
                    supplier_name: `${runPrefix} FreshPack Central`,
                    supplier_email: `supplier+${runPrefix}@example.com`,
                    expires_days: 7,
                    integration_profile_id: profileId,
                },
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
            tenant_id: tenantId,
            workbench_run_id: savedRun.run_id,
            readiness_score: readiness.score,
            fix_queue_count: fixQueue.length,
            commit_gate: commitGate,
            integration_profile_id: profileId,
            portal_id: portalLink.portal_id,
            portal_path: portalPath,
        });
    });
});
