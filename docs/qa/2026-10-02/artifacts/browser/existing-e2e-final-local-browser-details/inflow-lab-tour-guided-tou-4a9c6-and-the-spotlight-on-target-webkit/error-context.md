# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: inflow-lab-tour.spec.ts >> guided tours (desktop) >> dashboard preview: every step keeps the tooltip on-screen and the spotlight on target
- Location: tests/e2e/inflow-lab-tour.spec.ts:105:17

# Error details

```
Error: expect(received).toBeLessThanOrEqual(expected)

Expected: <= 901
Received:    917.796875
```

# Page snapshot

```yaml
- generic [ref=e1]:
  - main "Page content" [ref=e2]:
    - generic [ref=e4]:
      - generic [ref=e5]:
        - generic [ref=e6]:
          - generic [ref=e7]:
            - heading "Inflow Lab" [level=1] [ref=e8]
            - generic [ref=e9]: Sandbox
          - paragraph [ref=e10]: See exactly why a supplier lot will fail before it reaches production export.
        - generic [ref=e11]:
          - button "How to use" [ref=e12] [cursor=pointer]
          - link "Connections" [ref=e16]:
            - /url: /dashboard/integrations
          - button "Upload CSV" [ref=e20] [cursor=pointer]
          - button "Load realistic sample" [ref=e24] [cursor=pointer]
      - status [ref=e28]:
        - generic [ref=e30]: Sandbox preview only.
        - generic [ref=e31]: Production FDA-oriented exports stay sealed and review-ready — nothing here writes to them.
        - link "What runs in sandbox →" [ref=e32]:
          - /url: /docs/connectors/inflow-lab
      - generic [ref=e33]:
        - 'button "New to Inflow Lab? Learn to operate it step by step A guided walkthrough: load supplier data, run a sandbox test, read the readiness score, and clear blocked lots. Start walkthrough" [ref=e34] [cursor=pointer]':
          - generic [ref=e39]:
            - generic [ref=e40]: New to Inflow Lab? Learn to operate it step by step
            - generic [ref=e41]: "A guided walkthrough: load supplier data, run a sandbox test, read the readiness score, and clear blocked lots."
          - generic [ref=e42]: Start walkthrough
        - button "Dismiss tutorial banner" [ref=e45] [cursor=pointer]
      - region "Evidence chain" [ref=e49]:
        - generic [ref=e50]:
          - generic [ref=e51]:
            - generic [ref=e52]: TLC-20260508-000022
            - generic [ref=e53]: Green Leaf Lettuce · 156 cases · Valley Fresh Farms
          - generic [ref=e54]:
            - button "Run trace again" [ref=e55] [cursor=pointer]
            - button "Open sample in editor" [ref=e58] [cursor=pointer]
        - generic [ref=e60]:
          - generic [ref=e61]:
            - generic [ref=e65]:
              - text: Harvesting
              - generic [ref=e66]: ": proven"
            - generic [ref=e67]: Valley Fresh FarmsMay 7, 2026 at 3:18 AM
          - generic [ref=e68]:
            - generic [ref=e73]:
              - text: Cooling
              - generic [ref=e74]: ": proven"
            - generic [ref=e75]: Salinas Cooling HubMay 7, 2026 at 4:02 AM
          - generic [ref=e76]:
            - generic [ref=e81]:
              - text: Initial packing
              - generic [ref=e82]: ": proven"
            - generic [ref=e83]: GreenLeaf Packing HouseMay 7, 2026 at 6:20 AM
          - generic [ref=e84]:
            - generic [ref=e89]:
              - text: Shipping
              - generic [ref=e90]: ": missing"
            - generic [ref=e91]: no record received
          - generic [ref=e92]:
            - generic [ref=e97]:
              - text: DC receiving
              - generic [ref=e98]: ": missing"
            - generic [ref=e99]: no record received
          - generic [ref=e101]:
            - generic [ref=e102]: Export gate
            - generic [ref=e106]: Blocked
        - generic [ref=e107]:
          - generic [ref=e108]: rows read 11
          - generic [ref=e109]:
            - text: links proven
            - generic [ref=e110]: 3/5
          - generic [ref=e111]: lots in batch 3
        - generic [ref=e112]:
          - generic [ref=e113]:
            - heading "2 records never arrived." [level=2] [ref=e114]
            - generic [ref=e115]: Blocked now
          - paragraph [ref=e116]: Green Leaf Lettuce lot 000022 is blocked because Shipping, DC receiving never reached the evidence chain, so the export cannot be certified.
          - generic [ref=e117]:
            - generic [ref=e118]:
              - generic [ref=e119]: Missing
              - generic [ref=e120]: Shipping, DC receiving
            - generic [ref=e121]:
              - generic [ref=e122]: Pattern
              - generic [ref=e123]: Missing handoff evidence
            - generic [ref=e124]:
              - generic [ref=e125]: Lots affected
              - generic [ref=e126]: This lot only
          - generic [ref=e127]:
            - button "Focus this defect" [ref=e128] [cursor=pointer]
            - generic [ref=e129]: Map the missing handoff fields once, then re-run the lot group to clear the blocked export path.
      - region "Pipeline funnel" [ref=e130]:
        - generic [ref=e131]:
          - generic [ref=e132]: Pipeline
          - generic [ref=e133]: Last test run · May 7, 2026 at 12:08 PM
        - list [ref=e134]:
          - listitem [ref=e135]:
            - generic [ref=e136]:
              - generic [ref=e137]: Loaded
              - generic [ref=e138]: CSV
            - generic [ref=e139]: "3"
            - generic [ref=e140]: lots ingested
          - listitem [ref=e141]:
            - generic [ref=e142]:
              - generic [ref=e143]: Validated
              - generic [ref=e144]: schema
            - generic [ref=e145]: "11"
            - generic [ref=e146]: rows parse-clean
          - listitem [ref=e147]:
            - generic [ref=e148]:
              - generic [ref=e149]: Passing
              - generic [ref=e150]: ▶ next
            - generic [ref=e151]: 1/ 3
            - generic [ref=e152]: 2 exceptions blocking
            - button "Run sandbox test" [ref=e153] [cursor=pointer]
          - listitem [ref=e156]:
            - generic [ref=e157]:
              - generic [ref=e158]: Preview-ready
              - generic [ref=e159]: CTE
            - generic [ref=e160]: "0"
            - generic [ref=e161]: lots
          - listitem [ref=e162]:
            - generic [ref=e163]: Production import
            - generic [ref=e169]: —
            - generic [ref=e170]: locked until preview passes
      - generic [ref=e171]:
        - generic [ref=e172]:
          - generic [ref=e173]:
            - generic [ref=e174]:
              - generic [ref=e175]:
                - generic [ref=e176]: Data Preflight Score
                - generic [ref=e177]:
                  - generic [ref=e178]: "77"
                  - generic [ref=e179]: / 100
                  - generic [ref=e180]: needs work
                - paragraph [ref=e181]: Lowest factor sets the next fix.
              - generic [ref=e182]:
                - generic [ref=e183]: Latest sandbox run
                - generic [ref=e184]: not run yet
            - generic [ref=e185]:
              - text: "Proof lead: Proof lead lot 000022 is dragging down cte lifecycle because Shipping, DC receiving is still missing."
              - button "Open lead defect" [ref=e187] [cursor=pointer]
            - generic [ref=e188]:
              - generic [ref=e190]:
                - generic [ref=e191]: KDE completeness
                - generic [ref=e192]: 73%
              - generic [ref=e196]:
                - generic [ref=e197]: CTE lifecycle
                - generic [ref=e198]:
                  - text: 33%
                  - generic [ref=e199]: biggest gap
              - generic [ref=e203]:
                - generic [ref=e204]: Delivery quality
                - generic [ref=e205]: 100%
              - generic [ref=e209]:
                - generic [ref=e210]: Sandbox pass rate
                - generic [ref=e211]:
                  - text: —
                  - generic [ref=e212]: not run
              - generic [ref=e215]:
                - generic [ref=e216]: Connection health
                - generic [ref=e217]: 100%
          - generic [ref=e220]:
            - generic [ref=e221]:
              - generic [ref=e222]:
                - generic [ref=e223]: Exceptions
                - heading "2 lots blocked across 2 patterns" [level=2] [ref=e224]
                - paragraph [ref=e225]: Clear the pattern once, unblock the group.
                - generic [ref=e226]:
                  - generic [ref=e227]: Proof lead pattern
                  - generic [ref=e228]: Missing handoff evidence
                  - generic [ref=e229]: Lot 000022
              - generic [ref=e230]:
                - generic [ref=e231]:
                  - generic [ref=e232]: Filter
                  - button "all" [ref=e233] [cursor=pointer]
                  - button "handoff" [ref=e234] [cursor=pointer]
                  - button "source" [ref=e235] [cursor=pointer]
                  - button "mixed" [ref=e236] [cursor=pointer]
                - link "Open fix queue" [ref=e237]:
                  - /url: /exceptions
            - group [ref=e238]:
              - 'generic "Missing handoff evidence proof lead 1 lot Initial packing, shipping, DC receiving — handoff fields absent. Likely owner: Shipping / receiving source Fix all 1" [ref=e239] [cursor=pointer]':
                - generic [ref=e242]:
                  - generic [ref=e243]:
                    - generic [ref=e244]: Missing handoff evidence
                    - generic [ref=e245]: proof lead
                    - generic [ref=e246]: 1 lot
                  - paragraph [ref=e247]: Initial packing, shipping, DC receiving — handoff fields absent.
                - generic [ref=e248]: "Likely owner: Shipping / receiving source"
                - link "Fix all 1" [ref=e249]:
                  - /url: /exceptions
              - generic [ref=e250]:
                - generic [ref=e255]:
                  - generic [ref=e256]: "Root cause: 1 mapping fix likely clears all 1."
                  - generic [ref=e257]:
                    - text: Map the
                    - code [ref=e258]: handoff_evidence
                    - text: column from your shipping CSV, or upload a corrected file with packing/shipping/DC-receive timestamps.
                  - generic [ref=e259]:
                    - button "Upload corrected CSV" [ref=e260] [cursor=pointer]
                    - button "View a complete example" [ref=e261] [cursor=pointer]
                - generic [ref=e263]:
                  - button "TLC-20260508-000022 handoff Green Leaf Lettuce" [ref=e264] [cursor=pointer]:
                    - generic [ref=e265]: TLC-20260508-000022
                    - generic [ref=e266]: handoff
                    - generic [ref=e267]: Green Leaf Lettuce
                  - generic [ref=e268]: "missing: Shipping, DC receiving"
            - group [ref=e269]:
              - 'generic "Missing source evidence 1 lot Harvesting and cooling KDEs absent at the source. Likely owner: Supplier data owner Fix all 1" [ref=e270] [cursor=pointer]':
                - generic [ref=e273]:
                  - generic [ref=e274]:
                    - generic [ref=e275]: Missing source evidence
                    - generic [ref=e276]: 1 lot
                  - paragraph [ref=e277]: Harvesting and cooling KDEs absent at the source.
                - generic [ref=e278]: "Likely owner: Supplier data owner"
                - link "Fix all 1" [ref=e279]:
                  - /url: /exceptions
              - generic [ref=e280]:
                - generic [ref=e287]:
                  - generic [ref=e288]: "Root cause: 2 suppliers aren't sending harvest/cool timestamps."
                  - generic [ref=e289]: Fix at the source — sandbox can't fabricate KDEs.
                  - generic [ref=e290]:
                    - generic [ref=e291]:
                      - generic [ref=e292]: Desert Bloom Farms
                      - generic [ref=e293]: 1 lot · harvest_ts
                    - generic [ref=e294]:
                      - generic [ref=e295]: Desert Bloom Farms
                      - generic [ref=e296]: 1 lot · cooling_ts
                    - generic [ref=e297]:
                      - generic [ref=e298]: Both missing
                      - generic [ref=e299]: 1 lot
                  - generic [ref=e300]:
                    - link "Email suppliers" [ref=e301]:
                      - /url: mailto:?subject=Missing%20traceability%20timestamps%20in%20your%20supplier%20feed&body=Our%20preflight%20check%20found%20lots%20from%20your%20feed%20missing%20required%20timestamps%3A%0A%0A-%20Desert%20Bloom%20Farms%3A%20harvest%20timestamp%20missing%20on%201%20lot(s)%0A-%20Desert%20Bloom%20Farms%3A%20cooling%20timestamp%20missing%20on%201%20lot(s)%0A%0APlease%20include%20these%20fields%20in%20the%20next%20file%20so%20the%20lots%20can%20pass%20traceability%20preflight.
                    - button "Upload supplier CSV" [ref=e305] [cursor=pointer]
                    - link "View FSMA 204 KDE list" [ref=e306]:
                      - /url: https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods
                - generic [ref=e308]:
                  - button "TLC-20260508-000023 source Romaine Lettuce" [ref=e309] [cursor=pointer]:
                    - generic [ref=e310]: TLC-20260508-000023
                    - generic [ref=e311]: source
                    - generic [ref=e312]: Romaine Lettuce
                  - generic [ref=e313]: "missing: Harvesting, Cooling"
        - complementary [ref=e314]:
          - generic [ref=e315]:
            - generic [ref=e316]:
              - generic [ref=e317]:
                - generic [ref=e318]: Selected lot
                - button "Change" [ref=e319] [cursor=pointer]
              - generic [ref=e320]: TLC-20260508-000022
              - generic [ref=e321]:
                - generic [ref=e322]: proof lead
                - generic [ref=e323]: blocked
                - generic [ref=e324]: Green Leaf Lettuce
              - generic [ref=e325]:
                - text: "This proof lead is blocked on missing handoff evidence: Shipping, DC receiving missing."
                - button "Show matching queue group" [ref=e327] [cursor=pointer]
              - generic [ref=e328]:
                - generic [ref=e329]: Lifecycle
                - list [ref=e330]:
                  - listitem [ref=e331]:
                    - generic [ref=e333]: Harvesting
                    - generic [ref=e335]: Valley Fresh Farms · May 7, 2026 at 3:18 AM
                  - listitem [ref=e336]:
                    - generic [ref=e338]: Cooling
                    - generic [ref=e340]: Salinas Cooling Hub · May 7, 2026 at 4:02 AM
                  - listitem [ref=e341]:
                    - generic [ref=e343]: Initial packing
                    - generic [ref=e345]: GreenLeaf Packing House · May 7, 2026 at 6:20 AM
                  - listitem [ref=e346]:
                    - generic [ref=e348]:
                      - generic [ref=e349]: Shipping
                      - generic [ref=e350]: missing ts
                    - generic [ref=e351]: Not captured · Missing CTE
                  - listitem [ref=e352]:
                    - generic [ref=e354]:
                      - generic [ref=e355]: DC receiving
                      - generic [ref=e356]: missing ts
                    - generic [ref=e357]: Not captured · Missing CTE
              - generic [ref=e358]:
                - generic [ref=e359]: Lot KDE summary
                - generic [ref=e360]:
                  - generic [ref=e361]:
                    - generic [ref=e362]: Lot
                    - generic [ref=e363]: "000022"
                  - generic [ref=e364]:
                    - generic [ref=e365]: Events
                    - generic [ref=e366]: "3"
                  - generic [ref=e367]:
                    - generic [ref=e368]: CTE coverage
                    - generic [ref=e369]: 3/5
                  - generic [ref=e370]:
                    - generic [ref=e371]: Delivery
                    - generic [ref=e372]: posted
              - generic [ref=e373]:
                - button "Fix this lot" [ref=e374] [cursor=pointer]
                - link "Open in queue" [ref=e375]:
                  - /url: /exceptions
            - generic [ref=e376]:
              - generic [ref=e377]: Why this lot?
              - text: Current proof lead. Confirm the break here, then clear the matching pattern on the left.
  - region "Notifications (F8)":
    - list
  - alert [ref=e378]
  - dialog "What Inflow Lab is (step 1 of 7)" [active] [ref=e383]:
    - generic [ref=e384]:
      - generic [ref=e385]: Step 1 of 7
      - button "Close tutorial" [ref=e389]
    - generic [ref=e393]:
      - heading "What Inflow Lab is" [level=3] [ref=e394]
      - paragraph [ref=e395]: A sandbox for supplier traceability data. This is one lot's chain of custody, harvest through receiving — a solid link is a record we have, a broken one is a record that never arrived. The gate at the end is what a missing link costs you. Nothing here writes to production exports.
    - generic [ref=e396]:
      - generic [ref=e397]:
        - checkbox "Don't show again" [ref=e398]
        - text: Don't show again
      - button "Next" [ref=e400]
```

# Test source

```ts
  1   | import { expect, test, type Page } from '@playwright/test';
  2   | 
  3   | /**
  4   |  * Guards the Inflow Lab guided tours end to end in a real browser.
  5   |  *
  6   |  * The tour engine's failure modes are geometric — a tooltip positioned
  7   |  * off-screen, a spotlight ring pinned at stale pre-scroll coordinates, a
  8   |  * backdrop that swallows the click a step instructs — and none of them are
  9   |  * visible to jsdom. Every regression this spec asserts against shipped at
  10  |  * least once before real-browser validation caught it (#2764, #2765).
  11  |  */
  12  | 
  13  | const DASHBOARD_TOUR = {
  14  |     path: '/tools/inflow-lab-dashboard-preview',
  15  |     stepCount: 7,
  16  |     // Step index (0-based) whose tooltip carries a live action button.
  17  |     actionStep: 2,
  18  |     actionLabel: 'Run trace',
  19  |     targets: [
  20  |         '[data-testid="inflow-evidence-chain"]',
  21  |         '[data-tutorial="inflow-load-data"]',
  22  |         '[data-tutorial="inflow-guided-proof"]',
  23  |         '[data-testid="inflow-funnel"]',
  24  |         '[data-tutorial="inflow-readiness"]',
  25  |         '[data-tutorial="inflow-exceptions"]',
  26  |         '[data-selected-lot-panel]',
  27  |     ],
  28  | } as const;
  29  | 
  30  | const WORKBENCH_TOUR = {
  31  |     path: '/tools/inflow-lab',
  32  |     stepCount: 4,
  33  |     actionStep: 1,
  34  |     actionLabel: 'Run the demo',
  35  |     targets: [
  36  |         'section[aria-label="Inflow Lab environment boundary"]',
  37  |         '[data-tutorial="lab-primary-actions"]',
  38  |         '[data-tutorial="lab-tabs"]',
  39  |         '[data-tutorial="lab-workspace"]',
  40  |     ],
  41  | } as const;
  42  | 
  43  | type TourFixture = typeof DASHBOARD_TOUR | typeof WORKBENCH_TOUR;
  44  | 
  45  | function overlaps(
  46  |     a: { x: number; y: number; width: number; height: number },
  47  |     b: { x: number; y: number; width: number; height: number },
  48  | ) {
  49  |     return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
  50  | }
  51  | 
  52  | async function startTour(page: Page, tour: TourFixture) {
  53  |     await page.goto(tour.path);
  54  |     const banner = page.getByTestId('inflow-tutorial-banner');
  55  |     await expect(banner).toBeVisible();
  56  |     await banner.getByRole('button', { name: /Learn to operate it step by step/i }).click();
  57  |     await expect(page.getByText(`Step 1 of ${tour.stepCount}`)).toBeVisible();
  58  | }
  59  | 
  60  | async function assertStepGeometry(page: Page, tour: TourFixture, stepIndex: number) {
  61  |     // Let the smooth scroll and the engine's scroll-synced re-measure settle.
  62  |     await page.waitForTimeout(900);
  63  | 
  64  |     const viewport = page.viewportSize();
  65  |     expect(viewport).toBeTruthy();
  66  | 
  67  |     const dialog = page.getByRole('dialog');
  68  |     const tooltipBox = await dialog.boundingBox();
  69  |     expect(tooltipBox, `step ${stepIndex + 1}: tooltip should render`).toBeTruthy();
  70  |     // Regression: the engine once positioned tooltips using pre-scroll
  71  |     // coordinates (off-screen) and once let page-scoped CSS stretch the
  72  |     // tooltip to full viewport width.
  73  |     expect(tooltipBox!.x).toBeGreaterThanOrEqual(0);
  74  |     expect(tooltipBox!.y).toBeGreaterThanOrEqual(0);
  75  |     expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(viewport!.width + 1);
> 76  |     expect(tooltipBox!.y + tooltipBox!.height).toBeLessThanOrEqual(viewport!.height + 1);
      |                                                ^ Error: expect(received).toBeLessThanOrEqual(expected)
  77  |     expect(tooltipBox!.width, 'tooltip must be a card, not a full-width bar').toBeLessThan(
  78  |         viewport!.width * 0.75,
  79  |     );
  80  | 
  81  |     const spotlight = page.getByTestId('tutorial-spotlight');
  82  |     await expect(spotlight, `step ${stepIndex + 1}: spotlight ring should render`).toBeVisible();
  83  |     const ringBox = await spotlight.boundingBox();
  84  |     const targetBox = await page.locator(tour.targets[stepIndex]).first().boundingBox();
  85  |     expect(targetBox, `step ${stepIndex + 1}: target should exist`).toBeTruthy();
  86  |     // Regression: the ring once stayed pinned where the target WAS before the
  87  |     // smooth scroll moved it.
  88  |     expect(
  89  |         overlaps(ringBox!, targetBox!),
  90  |         `step ${stepIndex + 1}: spotlight must frame its target`,
  91  |     ).toBe(true);
  92  | }
  93  | 
  94  | for (const [label, viewport] of [
  95  |     ['desktop', { width: 1440, height: 900 }],
  96  |     ['narrow', { width: 900, height: 800 }],
  97  | ] as const) {
  98  |     test.describe(`guided tours (${label})`, () => {
  99  |         test.use({ viewport });
  100 | 
  101 |         for (const [name, tour] of [
  102 |             ['dashboard preview', DASHBOARD_TOUR],
  103 |             ['standalone workbench', WORKBENCH_TOUR],
  104 |         ] as const) {
  105 |             test(`${name}: every step keeps the tooltip on-screen and the spotlight on target`, async ({
  106 |                 page,
  107 |             }) => {
  108 |                 await startTour(page, tour);
  109 | 
  110 |                 for (let step = 0; step < tour.stepCount; step++) {
  111 |                     await assertStepGeometry(page, tour, step);
  112 | 
  113 |                     if (step === tour.actionStep) {
  114 |                         await expect(
  115 |                             page
  116 |                                 .getByRole('dialog')
  117 |                                 .getByRole('button', { name: tour.actionLabel }),
  118 |                             'the run step must carry its live action button',
  119 |                         ).toBeVisible();
  120 |                     }
  121 | 
  122 |                     if (step < tour.stepCount - 1) {
  123 |                         await page.getByRole('dialog').getByRole('button', { name: /Next/i }).click();
  124 |                         await expect(page.getByText(`Step ${step + 2} of ${tour.stepCount}`)).toBeVisible();
  125 |                     }
  126 |                 }
  127 | 
  128 |                 // Completing the tour retires this surface's banner…
  129 |                 await page.getByRole('dialog').getByRole('button', { name: 'Finish' }).click();
  130 |                 await expect(page.getByTestId('inflow-tutorial-banner')).toHaveCount(0);
  131 |                 // …but "How to use" stays as the re-entry point.
  132 |                 await page.getByRole('button', { name: /How to use/i }).first().click();
  133 |                 await expect(page.getByText(`Step 1 of ${tour.stepCount}`)).toBeVisible();
  134 |             });
  135 |         }
  136 | 
  137 |         test('dashboard preview: the spotlighted control is clickable while the tour stays open', async ({
  138 |             page,
  139 |         }) => {
  140 |             // Regression: the old backdrop overlaid the target, so clicking the
  141 |             // button a step pointed at closed the tour instead.
  142 |             await startTour(page, DASHBOARD_TOUR);
  143 |             for (let step = 0; step < DASHBOARD_TOUR.actionStep; step++) {
  144 |                 await page.getByRole('dialog').getByRole('button', { name: /Next/i }).click();
  145 |             }
  146 |             await expect(
  147 |                 page.getByText(`Step ${DASHBOARD_TOUR.actionStep + 1} of ${DASHBOARD_TOUR.stepCount}`),
  148 |             ).toBeVisible();
  149 |             await page.waitForTimeout(900);
  150 | 
  151 |             await page
  152 |                 .locator('[data-tutorial="inflow-guided-proof"]')
  153 |                 .getByRole('button', { name: 'Run trace' })
  154 |                 .click();
  155 | 
  156 |             await expect(page.getByRole('dialog')).toBeVisible();
  157 |         });
  158 |     });
  159 | }
  160 | 
```