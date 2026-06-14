import { expect, type Page } from '@playwright/test';

export async function selectPasswordLogin(page: Page): Promise<void> {
    await page.getByRole('button', { name: /^Password$/ }).click();
    await expect(page.locator('input[type="password"]')).toBeVisible();
}

export async function fillPasswordLogin(page: Page, email: string, password: string): Promise<void> {
    await selectPasswordLogin(page);
    await page.fill('input[type="email"]', email);
    await page.fill('input[type="password"]', password);
}
