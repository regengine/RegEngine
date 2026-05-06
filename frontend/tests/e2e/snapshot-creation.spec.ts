/**
 * E2E Test: Compliance Snapshot Workspace
 *
 * Exercises the real `/compliance/snapshots` surface instead of the old
 * placeholder `/energy` route. Covers the actual manual-freeze, verify, and
 * comparison flows that the snapshots workspace exposes today.
 */

import { expect, test, type Page } from '@playwright/test';
import { authenticatedE2ESkipReason, hasAuthenticatedE2E } from './auth-prereqs';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

function uniqueSnapshotName(prefix: string): string {
    return `${prefix} ${Date.now()}`;
}

async function loginAndWaitForDashboard(page: Page) {
    await page.goto('/login?next=/dashboard');
    await page.fill('input[type="email"]', TEST_USER_EMAIL);
    await page.fill('input[type="password"]', TEST_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard/, { timeout: 15000 });
    // Let the dashboard finish its initial background fetches before we
    // navigate away; otherwise Playwright cancels those requests and the
    // dev proxy logs noisy ECONNRESET "aborted" errors.
    await page.waitForLoadState('networkidle');
}

async function openSnapshotsWorkspace(page: Page) {
    await loginAndWaitForDashboard(page);

    const snapshotsLoad = page.waitForResponse((response) =>
        response.request().method() === 'GET' &&
        response.url().includes('/api/v1/compliance/snapshots/')
    );

    await page.goto('/compliance/snapshots');
    await snapshotsLoad;

    await expect(
        page.getByRole('heading', { name: 'Compliance Snapshots' }),
    ).toBeVisible();
    await expect(page.getByText('Living Compliance Artifacts')).toBeVisible();
}

function snapshotCard(page: Page, snapshotName: string) {
    return page
        .locator('[data-testid^="snapshot-card-"]')
        .filter({ hasText: snapshotName })
        .first();
}

async function createSnapshotViaUi(page: Page, snapshotName: string, reason?: string) {
    await page.getByRole('button', { name: 'Manual Freeze', exact: true }).click();
    await expect(
        page.getByRole('heading', { name: 'Manual Compliance Freeze' }),
    ).toBeVisible();

    await page.getByLabel('Snapshot Name').fill(snapshotName);
    if (reason) {
        await page.getByLabel('Snapshot Reason').fill(reason);
    }

    const createResponse = page.waitForResponse((response) =>
        response.request().method() === 'POST' &&
        response.url().includes('/api/v1/compliance/snapshots/') &&
        response.ok()
    );

    await page.getByRole('button', { name: 'Create Snapshot' }).click();
    await createResponse;

    await expect(
        page.getByRole('heading', { name: 'Manual Compliance Freeze' }),
    ).toBeHidden();

    const card = snapshotCard(page, snapshotName);
    await expect(card).toBeVisible();
    return card;
}

test.describe('Compliance Snapshot Workspace', () => {
    test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);

    test.beforeEach(async ({ page }) => {
        await openSnapshotsWorkspace(page);
    });

    test('renders the real snapshots workspace state', async ({ page }) => {
        const cards = page.locator('[data-testid^="snapshot-card-"]');
        const cardCount = await cards.count();

        if (cardCount === 0) {
            const emptyState = page.getByTestId('snapshot-empty-state');
            await expect(emptyState).toBeVisible();
            await expect(emptyState).toContainText('No Snapshots Yet');
            await expect(emptyState).toContainText('manual snapshot');
            return;
        }

        await expect(cards.first()).toBeVisible();
        await expect(
            cards.first().getByRole('button', { name: /Verify snapshot/i }),
        ).toBeVisible();
    });

    test('can create a manual compliance snapshot', async ({ page }) => {
        const snapshotName = uniqueSnapshotName('E2E manual freeze');
        const reason = 'Playwright manual-freeze coverage';
        const card = await createSnapshotViaUi(page, snapshotName, reason);

        await expect(card).toContainText(reason);
        await expect(card).toContainText('Verify');
        await expect(card).toContainText('PDF');
    });

    test('can open an FDA response template from the workspace', async ({ page }) => {
        const snapshotName = uniqueSnapshotName('E2E fda snapshot');
        const card = await createSnapshotViaUi(page, snapshotName, 'FDA fallback coverage');

        const fdaResponse = page.waitForResponse((response) =>
            response.request().method() === 'GET' &&
            response.url().includes('/fda-response') &&
            response.ok()
        );

        await card.locator('button[title="Generate FDA Response"]').click();
        await fdaResponse;

        const fdaModal = page.getByTestId('snapshot-fda-modal');
        await expect(
            fdaModal.getByRole('heading', { name: /FDA Response Template/i }),
        ).toBeVisible();
        await expect(fdaModal.locator('pre')).toContainText(snapshotName);
    });

    test('can download a zero-trust audit pack from the workspace', async ({ page }) => {
        const snapshotName = uniqueSnapshotName('E2E audit pack');
        const card = await createSnapshotViaUi(page, snapshotName);

        const auditPackResponse = page.waitForResponse((response) =>
            response.request().method() === 'GET' &&
            response.url().includes('/audit-pack') &&
            response.ok()
        );
        const downloadPromise = page.waitForEvent('download');

        await card.getByRole('button', { name: 'Audit Pack', exact: true }).click();

        await auditPackResponse;
        const download = await downloadPromise;
        expect(download.suggestedFilename()).toContain('ZeroTrust-AuditPack-');
    });

    test('can verify snapshot integrity from the workspace', async ({ page }) => {
        const snapshotName = uniqueSnapshotName('E2E verify snapshot');
        const card = await createSnapshotViaUi(page, snapshotName);

        const verifyResponse = page.waitForResponse((response) =>
            response.request().method() === 'GET' &&
            response.url().includes('/verify?verified_by=') &&
            response.ok()
        );

        const verifyButton = card.getByRole('button', {
            name: `Verify snapshot ${snapshotName}`,
        });
        await verifyButton.scrollIntoViewIfNeeded();
        await verifyButton.click();
        await verifyResponse;

        await expect(
            page.getByRole('heading', { name: /Integrity Verified/i }),
        ).toBeVisible();
        await expect(page.getByText('Verified by:')).toBeVisible();
    });

    test('can compare two snapshots from the workspace', async ({ page }) => {
        const snapshotA = uniqueSnapshotName('E2E compare A');
        const snapshotB = uniqueSnapshotName('E2E compare B');

        const cardA = await createSnapshotViaUi(page, snapshotA);
        const cardB = await createSnapshotViaUi(page, snapshotB);

        await cardA.getByRole('button', {
            name: `Select snapshot ${snapshotA} for comparison`,
        }).click();
        await cardB.getByRole('button', {
            name: `Select snapshot ${snapshotB} for comparison`,
        }).click();

        const compareResponse = page.waitForResponse((response) =>
            response.request().method() === 'GET' &&
            response.url().includes('/diff?snapshot_a=') &&
            response.ok()
        );

        await page.getByRole('button', { name: 'Compare Selected' }).click();
        await compareResponse;

        const diffModal = page.getByTestId('snapshot-diff-modal');
        await expect(
            diffModal.getByRole('heading', { name: 'Snapshot Comparison' }),
        ).toBeVisible();
        await expect(diffModal).toContainText(`From: ${snapshotA}`);
        await expect(diffModal).toContainText(`To: ${snapshotB}`);
    });
});
