import { expect, test, type Page } from '@playwright/test';
import { authenticatedE2ESkipReason, hasAuthenticatedE2E } from './auth-prereqs';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

async function loginToDashboardInflowLab(page: Page) {
    await page.goto('/login?next=/dashboard/inflow-lab');
    await page.fill('input[type="email"]', TEST_USER_EMAIL);
    await page.fill('input[type="password"]', TEST_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard\/inflow-lab/, { timeout: 15000 });
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
            '/dashboard/exceptions',
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

});
