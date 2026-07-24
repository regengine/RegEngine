import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { hasPasswordlessE2E, passwordlessE2ESkipReason } from './auth-prereqs';
import { csrfHeader, loginViaApi, logoutViaApi, type ApiSession } from './support/api-auth';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const ADMIN_MASTER_KEY = process.env.ADMIN_MASTER_KEY || 'playwright-local-admin-master-key-2026';
const DEFAULT_ADMIN_DB = 'sqlite:////tmp/regengine-playwright-admin.db';

async function loginToDashboardInflowLab(page: Page, email = TEST_USER_EMAIL): Promise<ApiSession> {
    const session = await loginViaApi(page.context(), email);
    await page.goto('/dashboard/inflow-lab');
    await page.waitForURL(/\/dashboard\/inflow-lab/, { timeout: 15000 });
    return session;
}

async function enableInflowWriteApiKey(page: Page, session: ApiSession) {
    const tenantId = session.tenant_id;
    expect(tenantId, 'Inflow write E2E requires an authenticated tenant').toBeTruthy();
    expect(ADMIN_MASTER_KEY, 'Inflow write E2E requires ADMIN_MASTER_KEY to mint a scoped key').toBeTruthy();

    const createdResponse = await page.request.post('/api/admin/v1/admin/keys', {
        headers: {
            'Content-Type': 'application/json',
            Origin: new URL(page.url()).origin,
            'x-admin-key': ADMIN_MASTER_KEY,
            ...(await csrfHeader(page.context())),
        },
        data: {
            name: `inflow-dashboard-e2e-${Date.now()}`,
            tenant_id: tenantId,
            scopes: ['inflow.read', 'inflow.write'],
        },
    });
    expect(createdResponse.ok(), await createdResponse.text()).toBeTruthy();
    const created = await createdResponse.json() as { api_key?: string };
    const apiKey = String(created.api_key || '');
    expect(apiKey, 'Admin API should return the scoped API key once').toBeTruthy();

    await page.request.get('/api/session');
    const response = await page.request.post('/api/session', {
        headers: {
            'Content-Type': 'application/json',
            Origin: new URL(page.url()).origin,
            ...(await csrfHeader(page.context())),
        },
        data: {
            api_key: apiKey,
            tenant_id: tenantId,
        },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
}

function resolveAdminSqlitePath() {
    return (process.env.ADMIN_FALLBACK_SQLITE || DEFAULT_ADMIN_DB).replace(/^sqlite:\/*/, '/');
}

function ensureViewerRole(tenantId: string) {
    const database = new DatabaseSync(resolveAdminSqlitePath());
    try {
        const existingRole = database
            .prepare('SELECT id FROM roles WHERE tenant_id = ? AND name = ? LIMIT 1')
            .get(tenantId, 'Viewer') as { id: string } | undefined;
        if (existingRole?.id) {
            return existingRole.id;
        }

        const viewerRoleId = randomUUID();
        database
            .prepare('INSERT INTO roles (id, tenant_id, name, permissions) VALUES (?, ?, ?, ?)')
            .run(viewerRoleId, tenantId, 'Viewer', JSON.stringify(['inflow.read']));
        return viewerRoleId;
    } finally {
        database.close();
    }
}

test.describe('Dashboard Inflow Lab', () => {
    test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);

    test('renders the sandbox-first inflow workspace for authenticated users', async ({ page }) => {
        await loginToDashboardInflowLab(page);

        await expect(page.getByRole('heading', { name: 'Inflow Lab' })).toBeVisible();
        await expect(page.getByText('Sandbox preview only.')).toBeVisible();
        await expect(page.getByTestId('inflow-funnel')).toBeVisible();
        await expect(page.getByText('KDE completeness')).toBeVisible();
        await expect(page.getByText('Filter')).toBeVisible();
        await expect(page.getByText('Selected lot')).toBeVisible();
        await expect(page.getByRole('button', { name: /Run sandbox test/i })).toBeVisible();
        await expect(page.getByRole('link', { name: 'Open fix queue' })).toHaveAttribute(
            'href',
            '/exceptions',
        );
    });

    test('keeps sandbox evaluation gated behind local CSV input', async ({ page }) => {
        await loginToDashboardInflowLab(page);

        await page.getByRole('button', { name: /Run sandbox test/i }).click();
        await expect(
            page.getByText('Paste CSV text or upload a CSV file before evaluating.'),
        ).toBeVisible();
        await expect(page.getByRole('region', { name: 'CSV input' })).toBeVisible();
        await expect(page.getByLabel('Inbound CSV data')).toBeVisible();
    });

    test('records a saved workbench run only after the explicit save action', async ({ page }) => {
        const session = await loginToDashboardInflowLab(page);
        await enableInflowWriteApiKey(page, session);

        await page.getByRole('button', { name: /Run sandbox test/i }).click();
        await page.getByRole('textbox', { name: 'Inbound CSV data' }).fill(
            'cte_type,traceability_lot_code\nshipping,TLC-FEED-001',
        );
        await page.getByRole('button', { name: /Run sandbox test/i }).click();

        await expect(page.getByText('Sandbox evaluator processed 1 event.')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Save test run' })).toBeVisible();
        await expect(
            page.getByText(
                'Sandbox evaluation is stateless until you explicitly save a test run.',
            ),
        ).toBeVisible();

        await page.getByRole('button', { name: 'Save test run' }).click();

        await expect(page.getByText('Saved to Inflow Workbench as')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Saved' })).toBeDisabled();
        await expect(
            page.getByText(/open fix(?:es)? remain for this saved test run\./),
        ).toBeVisible();
        await expect(page.getByText(/Last test run ·/)).not.toContainText('never');
    });

    test('shows a write-access note when the workbench save path is denied', async ({ page }) => {
        await loginToDashboardInflowLab(page);
        await page.route('**/api/ingestion/api/v1/inflow-workbench/runs', async (route) => {
            await route.fulfill({
                status: 403,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Write access required' }),
            });
        });

        await page.getByRole('button', { name: /Run sandbox test/i }).click();
        await page.getByRole('textbox', { name: 'Inbound CSV data' }).fill(
            'cte_type,traceability_lot_code\nshipping,TLC-FEED-002',
        );
        await page.getByRole('button', { name: /Run sandbox test/i }).click();

        await expect(page.getByText('Sandbox evaluator processed 1 event.')).toBeVisible();
        await page.getByRole('button', { name: 'Save test run' }).click();
        await expect(
            page.getByText(
                'You can evaluate sandbox data here, but only users with write access can save an Inflow Workbench test run.',
            ),
        ).toBeVisible();
        await expect(page.getByText('Saved to Inflow Workbench as')).toHaveCount(0);
    });
    test('reloads the latest saved workbench run after a successful save', async ({ page }) => {
        const session = await loginToDashboardInflowLab(page);
        await enableInflowWriteApiKey(page, session);

        await page.getByRole('button', { name: /Run sandbox test/i }).click();
        await page.getByRole('textbox', { name: 'Inbound CSV data' }).fill(
            'cte_type,traceability_lot_code\nshipping,TLC-FEED-004',
        );
        await page.getByRole('button', { name: /Run sandbox test/i }).click();
        await expect(page.getByRole('button', { name: 'Save test run' })).toBeVisible();
        await page.getByRole('button', { name: 'Save test run' }).click();

        const saveConfirmation = page.locator('div').filter({ hasText: 'Saved to Inflow Workbench as' }).last();
        const savedRunId = await saveConfirmation.locator('code').textContent();
        expect(savedRunId).toBeTruthy();

        await page.reload();
        await expect(page.getByText('Latest saved workbench run')).toBeVisible();
        await expect(page.getByText(savedRunId as string)).toBeVisible();
        await expect(page.getByText(/open fix(?:es)? remain in workbench\./)).toBeVisible();
        await expect(page.getByText(/Last test run ·/)).not.toContainText('never');
    });

    test('disables save before any POST when the logged-in user lacks inflow.write', async ({ page, context }) => {
        const viewerEmail = `e2e-inflow-viewer-${Date.now()}@example.com`;

        // Invite the viewer as the owner over an authenticated session, then
        // hand the browser context to the viewer for the UI assertions.
        const adminSession = await loginViaApi(context, TEST_USER_EMAIL);
        const viewerRoleId = ensureViewerRole(adminSession.tenant_id);

        const inviteResponse = await context.request.post('/api/admin/v1/admin/invites', {
            headers: await csrfHeader(context),
            data: {
                email: viewerEmail,
                role_id: viewerRoleId,
            },
        });
        expect(inviteResponse.ok(), await inviteResponse.text()).toBeTruthy();
        const invitePayload = await inviteResponse.json();
        const inviteUrl = new URL(invitePayload.invite_link as string, 'http://localhost');
        const token = new URLSearchParams(inviteUrl.hash.slice(1)).get('token');
        expect(token).toBeTruthy();

        const acceptResponse = await context.request.post('/api/admin/v1/auth/accept-invite', {
            data: {
                token,
                name: 'E2E Viewer',
            },
        });
        expect(acceptResponse.ok(), await acceptResponse.text()).toBeTruthy();

        await logoutViaApi(context);
        await context.clearCookies();
        await loginToDashboardInflowLab(page, viewerEmail);

        await page.getByRole('button', { name: /Run sandbox test/i }).click();
        await page.getByRole('textbox', { name: 'Inbound CSV data' }).fill(
            'cte_type,traceability_lot_code\nshipping,TLC-FEED-003',
        );
        await page.getByRole('button', { name: /Run sandbox test/i }).click();

        await expect(page.getByText('Sandbox evaluator processed 1 event.')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Save unavailable' })).toBeDisabled();
        await expect(
            page.getByText(
                'You can evaluate sandbox data here, but only users with write access can save an Inflow Workbench test run.',
            ),
        ).toBeVisible();
        await expect(page.getByText('Saved to Inflow Workbench as')).toHaveCount(0);
    });
});
