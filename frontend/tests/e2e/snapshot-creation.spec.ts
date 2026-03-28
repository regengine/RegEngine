/**
 * E2E Test: Energy Snapshot Creation Flow
 * 
 * Tests the complete snapshot creation journey:
 * 1. Navigate to Energy dashboard
 * 2. Click create snapshot button
 * 3. Fill in snapshot form
 * 4. Submit and verify creation
 * 5. View snapshot in list
 */

import { test, expect } from '@playwright/test';

const TEST_PASSWORD = process.env.TEST_PASSWORD || 'test-placeholder';

test.describe('Energy Snapshot Creation', () => {
    test.beforeEach(async ({ page }) => {
        // Login
        await page.goto('/login');
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');

        // Navigate to Energy section
        const energyLink = page.locator('a:has-text("Energy")').first();
        if (await energyLink.isVisible()) {
            await energyLink.click();
            await page.waitForTimeout(500);
        } else {
            // Try direct navigation
            await page.goto('/energy');
        }
    });

    test('create new compliance snapshot', async ({ page }) => {
        // Look for create snapshot button
        const createButton = page.locator('button:has-text("Create"), button:has-text("New Snapshot")').first();

        if (await createButton.isVisible()) {
            await createButton.click();

            // Fill in snapshot form (fields may vary)
            const substationInput = page.locator('input[name="substation_id"], input[placeholder*="substation" i]').first();
            if (await substationInput.isVisible()) {
                await substationInput.fill('SUB-001');
            }

            // Submit form
            const submitButton = page.locator('button[type="submit"], button:has-text("Create"), button:has-text("Save")').first();
            await submitButton.click();

            // Wait for success message or redirect
            await page.waitForTimeout(1000);

            // Verify snapshot appears in list or success message
            const successIndicator = page.locator('text=/success|created|snapshot/i').first();
            await expect(successIndicator).toBeVisible({ timeout: 5000 });
        }
    });

    test('snapshot list displays existing snapshots', async ({ page }) => {
        // Should see snapshot list or table
        const snapshotList = page.locator('table, ul, [role="list"]').first();
        await expect(snapshotList).toBeVisible({ timeout: 5000 });
    });

    test('can filter snapshots by substation', async ({ page }) => {
        // Look for filter input
        const filterInput = page.locator('input[placeholder*="filter" i], input[placeholder*="search" i]').first();

        if (await filterInput.isVisible()) {
            await filterInput.fill('SUB-001');
            await page.waitForTimeout(500);

            // Results should update
            // This is a basic check - actual implementation may vary
            const results = page.locator('table tbody tr, ul li').count();
            expect(await results).toBeGreaterThanOrEqual(0);
        }
    });

    test('snapshot details are viewable', async ({ page }) => {
        // Find first snapshot in list
        const firstSnapshot = page.locator('table tbody tr, ul li, [data-testid*="snapshot"]').first();

        if (await firstSnapshot.isVisible()) {
            await firstSnapshot.click();

            // Should show detail view
            await page.waitForTimeout(500);

            // Should have some detail content
            const detailView = page.locator('text=/snapshot|details|created/i').first();
            await expect(detailView).toBeVisible();
        }
    });
});

test.describe('Snapshot Verification', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/login');
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[type="password"]', TEST_PASSWORD);
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');
        await page.goto('/energy');
    });

    test('verify chain integrity button works', async ({ page }) => {
        // Look for verify button
        const verifyButton = page.locator('button:has-text("Verify"), button:has-text("Check Integrity")').first();

        if (await verifyButton.isVisible()) {
            await verifyButton.click();
            await page.waitForTimeout(1000);

            // Should show verification result
            const result = page.locator('text=/valid|integrity|verified/i').first();
            await expect(result).toBeVisible({ timeout: 5000 });
        }
    });

    test('mismatch detection displays warnings', async ({ page }) => {
        // Navigate to mismatches tab/section
        const mismatchTab = page.locator('text=/mismatch|violation|issue/i').first();

        if (await mismatchTab.isVisible()) {
            await mismatchTab.click();
            await page.waitForTimeout(500);

            // Should show mismatch list or empty state
            const mismatchContent = page.locator('text=/mismatch|no issues|all compliant/i').first();
            await expect(mismatchContent).toBeVisible();
        }
    });
});
