import { expect, test, type Page } from '@playwright/test';

/**
 * Guards the Inflow Lab guided tours end to end in a real browser.
 *
 * The tour engine's failure modes are geometric — a tooltip positioned
 * off-screen, a spotlight ring pinned at stale pre-scroll coordinates, a
 * backdrop that swallows the click a step instructs — and none of them are
 * visible to jsdom. Every regression this spec asserts against shipped at
 * least once before real-browser validation caught it (#2764, #2765).
 */

const DASHBOARD_TOUR = {
    path: '/tools/inflow-lab-dashboard-preview',
    stepCount: 7,
    // Step index (0-based) whose tooltip carries a live action button.
    actionStep: 2,
    actionLabel: 'Run guided proof',
    targets: [
        'section[aria-label="How Inflow Lab works"]',
        '[data-tutorial="inflow-load-data"]',
        '[data-tutorial="inflow-guided-proof"]',
        '[data-testid="inflow-funnel"]',
        '[data-tutorial="inflow-readiness"]',
        '[data-tutorial="inflow-exceptions"]',
        '[data-selected-lot-panel]',
    ],
} as const;

const WORKBENCH_TOUR = {
    path: '/tools/inflow-lab',
    stepCount: 4,
    actionStep: 1,
    actionLabel: 'Run the demo',
    targets: [
        'section[aria-label="Inflow Lab environment boundary"]',
        '[data-tutorial="lab-primary-actions"]',
        '[data-tutorial="lab-tabs"]',
        '[data-tutorial="lab-workspace"]',
    ],
} as const;

type TourFixture = typeof DASHBOARD_TOUR | typeof WORKBENCH_TOUR;

function overlaps(
    a: { x: number; y: number; width: number; height: number },
    b: { x: number; y: number; width: number; height: number },
) {
    return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

async function startTour(page: Page, tour: TourFixture) {
    await page.goto(tour.path);
    const banner = page.getByTestId('inflow-tutorial-banner');
    await expect(banner).toBeVisible();
    await banner.getByRole('button', { name: /Learn to operate it step by step/i }).click();
    await expect(page.getByText(`Step 1 of ${tour.stepCount}`)).toBeVisible();
}

async function assertStepGeometry(page: Page, tour: TourFixture, stepIndex: number) {
    // Let the smooth scroll and the engine's scroll-synced re-measure settle.
    await page.waitForTimeout(900);

    const viewport = page.viewportSize();
    expect(viewport).toBeTruthy();

    const dialog = page.getByRole('dialog');
    const tooltipBox = await dialog.boundingBox();
    expect(tooltipBox, `step ${stepIndex + 1}: tooltip should render`).toBeTruthy();
    // Regression: the engine once positioned tooltips using pre-scroll
    // coordinates (off-screen) and once let page-scoped CSS stretch the
    // tooltip to full viewport width.
    expect(tooltipBox!.x).toBeGreaterThanOrEqual(0);
    expect(tooltipBox!.y).toBeGreaterThanOrEqual(0);
    expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(viewport!.width + 1);
    expect(tooltipBox!.y + tooltipBox!.height).toBeLessThanOrEqual(viewport!.height + 1);
    expect(tooltipBox!.width, 'tooltip must be a card, not a full-width bar').toBeLessThan(
        viewport!.width * 0.75,
    );

    const spotlight = page.getByTestId('tutorial-spotlight');
    await expect(spotlight, `step ${stepIndex + 1}: spotlight ring should render`).toBeVisible();
    const ringBox = await spotlight.boundingBox();
    const targetBox = await page.locator(tour.targets[stepIndex]).first().boundingBox();
    expect(targetBox, `step ${stepIndex + 1}: target should exist`).toBeTruthy();
    // Regression: the ring once stayed pinned where the target WAS before the
    // smooth scroll moved it.
    expect(
        overlaps(ringBox!, targetBox!),
        `step ${stepIndex + 1}: spotlight must frame its target`,
    ).toBe(true);
}

for (const [label, viewport] of [
    ['desktop', { width: 1440, height: 900 }],
    ['narrow', { width: 900, height: 800 }],
] as const) {
    test.describe(`guided tours (${label})`, () => {
        test.use({ viewport });

        for (const [name, tour] of [
            ['dashboard preview', DASHBOARD_TOUR],
            ['standalone workbench', WORKBENCH_TOUR],
        ] as const) {
            test(`${name}: every step keeps the tooltip on-screen and the spotlight on target`, async ({
                page,
            }) => {
                await startTour(page, tour);

                for (let step = 0; step < tour.stepCount; step++) {
                    await assertStepGeometry(page, tour, step);

                    if (step === tour.actionStep) {
                        await expect(
                            page
                                .getByRole('dialog')
                                .getByRole('button', { name: tour.actionLabel }),
                            'the run step must carry its live action button',
                        ).toBeVisible();
                    }

                    if (step < tour.stepCount - 1) {
                        await page.getByRole('dialog').getByRole('button', { name: /Next/i }).click();
                        await expect(page.getByText(`Step ${step + 2} of ${tour.stepCount}`)).toBeVisible();
                    }
                }

                // Completing the tour retires this surface's banner…
                await page.getByRole('dialog').getByRole('button', { name: 'Finish' }).click();
                await expect(page.getByTestId('inflow-tutorial-banner')).toHaveCount(0);
                // …but "How to use" stays as the re-entry point.
                await page.getByRole('button', { name: /How to use/i }).first().click();
                await expect(page.getByText(`Step 1 of ${tour.stepCount}`)).toBeVisible();
            });
        }

        test('dashboard preview: the spotlighted control is clickable while the tour stays open', async ({
            page,
        }) => {
            // Regression: the old backdrop overlaid the target, so clicking the
            // button a step pointed at closed the tour instead.
            await startTour(page, DASHBOARD_TOUR);
            for (let step = 0; step < DASHBOARD_TOUR.actionStep; step++) {
                await page.getByRole('dialog').getByRole('button', { name: /Next/i }).click();
            }
            await expect(
                page.getByText(`Step ${DASHBOARD_TOUR.actionStep + 1} of ${DASHBOARD_TOUR.stepCount}`),
            ).toBeVisible();
            await page.waitForTimeout(900);

            await page
                .locator('[data-tutorial="inflow-guided-proof"]')
                .getByRole('button', { name: 'Run guided proof' })
                .click();

            await expect(page.getByRole('dialog')).toBeVisible();
        });
    });
}
