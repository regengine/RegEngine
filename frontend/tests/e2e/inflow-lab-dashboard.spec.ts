import { expect, test, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { authenticatedE2ESkipReason, hasAuthenticatedE2E } from './auth-prereqs';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || process.env.TEST_USER_EMAIL || 'admin@example.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || process.env.TEST_PASSWORD || 'test-placeholder';
const VIEWER_PASSWORD = 'Trace204!Viewer1'; // pragma: allowlist secret
const DEFAULT_ADMIN_DB = 'sqlite:////tmp/regengine-playwright-admin.db';

async function loginToDashboardInflowLab(page: Page) {
    await loginAsUser(page, TEST_USER_EMAIL, TEST_PASSWORD);
}

async function loginAsUser(page: Page, email: string, password: string) {
    await page.goto('/login?next=/dashboard/inflow-lab');
    await page.fill('input[type="email"]', email);
    await page.fill('input[type="password"]', password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard\/inflow-lab/, { timeout: 15000 });
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
    test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

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
        await loginToDashboardInflowLab(page);

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
        await loginToDashboardInflowLab(page);

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

    test('disables save before any POST when the logged-in user lacks inflow.write', async ({ page, request }) => {
        const viewerEmail = `e2e-inflow-viewer-${Date.now()}@example.com`;

        const adminLoginResponse = await request.post('/api/admin/auth/login', {
            data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
        });
        expect(adminLoginResponse.ok()).toBeTruthy();
        const adminLoginPayload = await adminLoginResponse.json();
        const viewerRoleId = ensureViewerRole(adminLoginPayload.tenant_id as string);

        const inviteResponse = await request.post('/api/admin/v1/admin/invites', {
            headers: {
                Authorization: `Bearer ${adminLoginPayload.access_token as string}`,
            },
            data: {
                email: viewerEmail,
                role_id: viewerRoleId,
            },
        });
        expect(inviteResponse.ok()).toBeTruthy();
        const invitePayload = await inviteResponse.json();
        const inviteUrl = new URL(invitePayload.invite_link as string, 'http://localhost');
        const token = new URLSearchParams(inviteUrl.hash.slice(1)).get('token');
        expect(token).toBeTruthy();

        const acceptResponse = await request.post('/api/admin/v1/auth/accept-invite', {
            data: {
                token,
                password: VIEWER_PASSWORD,
                name: 'E2E Viewer',
            },
        });
        expect(acceptResponse.ok()).toBeTruthy();

        await loginAsUser(page, viewerEmail, VIEWER_PASSWORD);

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
