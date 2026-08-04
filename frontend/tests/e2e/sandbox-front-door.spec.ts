/**
 * Sandbox front door E2E — #2757.
 *
 * Walks the funnel the compare pages advertise: comparison CTA → sandbox →
 * rendered FSMA 204 diagnosis for a sample FTL chain.
 *
 * The sandbox evaluator is an experimental router (server/main.py
 * _EXPERIMENTAL_ROUTERS) and is auto-disabled in production, so this spec
 * probes it at runtime and asserts the correct behaviour for whichever state
 * the target deployment is in — same convention as demo-smoke.spec.ts:
 *
 *   mounted    → CTA lands on /sandbox and the sample CSV evaluates end to end.
 *   unmounted  → CTA lands on /demo, no page promises a CSV sandbox, and a
 *                direct visit to /sandbox explains itself instead of 404ing.
 *
 * Either way the invariant under test is the one #2730 broke: CTA copy and CTA
 * destination must agree.
 */
import { expect, test, type Page } from '@playwright/test';

const COMPARE_PAGES = ['/compare/tracegains', '/compare/foodlogiq', '/compare/repositrak'];

const SANDBOX_PROMISE = /drop your csv in the sandbox/i;

async function sandboxEvaluatorMounted(page: Page): Promise<boolean> {
    const res = await page.request.post('/api/ingestion/api/v1/sandbox/evaluate', {
        data: { csv: 'cte_type\nshipping\n' },
        failOnStatusCode: false,
    });
    // 404 = router not mounted on this deployment. Anything else (200, 400,
    // 429) means the endpoint is there and answering.
    return res.status() !== 404;
}

test.describe('sandbox front door (#2757)', () => {
    test('/sandbox is a real route, never a 404', async ({ page }) => {
        const res = await page.goto('/sandbox');
        expect(res?.status()).toBe(200);
        // Whichever state we are in, the page says something specific.
        await expect(
            page.getByRole('heading', { name: /FSMA 204 Sandbox|not enabled on this deployment/i }),
        ).toBeVisible();
    });

    for (const comparePath of COMPARE_PAGES) {
        test(`${comparePath} CTA copy matches where it goes`, async ({ page }) => {
            const mounted = await sandboxEvaluatorMounted(page);
            await page.goto(comparePath);

            const cta = page
                .getByRole('link', { name: mounted ? /Try the Sandbox/i : /interactive demo/i })
                .first();
            await expect(cta).toBeVisible();

            const body = await page.locator('body').innerText();
            if (mounted) {
                expect(body).toMatch(SANDBOX_PROMISE);
            } else {
                // The #2730 failure: sandbox prose above a button going elsewhere.
                expect(body).not.toMatch(SANDBOX_PROMISE);
            }

            await cta.click();
            await expect(page).toHaveURL(new RegExp(mounted ? '/sandbox$' : '/demo'));
        });
    }

    test('homepage #sandbox anchor resolves to the same destination', async ({ page }) => {
        const mounted = await sandboxEvaluatorMounted(page);
        await page.goto('/#sandbox');

        const section = page.locator('#sandbox');
        await expect(section).toBeVisible();

        const cta = section.getByRole('link').first();
        await cta.click();
        await expect(page).toHaveURL(new RegExp(mounted ? '/sandbox$' : '/demo'));
    });

    test('sample FTL CSV evaluates and renders a diagnosis', async ({ page }) => {
        test.skip(
            !(await sandboxEvaluatorMounted(page)),
            'sandbox router not mounted on this deployment (experimental, prod-disabled)',
        );

        await page.goto('/sandbox');
        await page.getByRole('button', { name: /Run a sample FTL chain/i }).click();

        await expect(page.getByText('FSMA 204 Sandbox Diagnosis')).toBeVisible({ timeout: 30_000 });

        // The sample chain is deliberately imperfect — a clean result would mean
        // the rules did not run.
        await expect(page.getByText('SV-20260115-001').first()).toBeVisible();
        await expect(page.getByText(/need attention|NEEDS CORRECTION/i).first()).toBeVisible();
    });

    test('unmounted evaluator explains itself instead of hanging', async ({ page }) => {
        test.skip(
            await sandboxEvaluatorMounted(page),
            'sandbox router is mounted — the unavailable path does not apply',
        );

        await page.goto('/sandbox');
        await expect(page.getByText(/not enabled on this deployment/i)).toBeVisible();
        await expect(page.getByRole('link', { name: /interactive demo/i })).toBeVisible();
    });
});
