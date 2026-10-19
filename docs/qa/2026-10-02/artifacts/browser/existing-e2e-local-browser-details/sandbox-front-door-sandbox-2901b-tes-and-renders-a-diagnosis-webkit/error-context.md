# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: sandbox-front-door.spec.ts >> sandbox front door (#2757) >> sample FTL CSV evaluates and renders a diagnosis
- Location: tests/e2e/sandbox-front-door.spec.ts:80:9

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('FSMA 204 Sandbox Diagnosis')
Expected: visible
Timeout: 30000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByText('FSMA 204 Sandbox Diagnosis') with timeout 30000ms
  - waiting for getByText('FSMA 204 Sandbox Diagnosis')

```

```yaml
- link "Skip to content":
  - /url: "#main-content"
- navigation "Main navigation":
  - link "RegEngine":
    - /url: /
  - link "Product":
    - /url: /product
  - link "Integrations":
    - /url: /integrations
  - link "Readiness":
    - /url: /retailer-readiness
  - link "Pricing":
    - /url: /pricing
  - link "FSMA 204":
    - /url: /fsma-204
  - button "Tools"
  - link "Developers":
    - /url: /developer/portal
  - link "Docs":
    - /url: /docs
  - button "Switch to dark mode"
  - link "Log In":
    - /url: /login
  - link "Free Tools":
    - /url: /tools
- main "Page content":
  - heading "FSMA 204 Sandbox" [level=1]
  - paragraph: Upload a CSV of traceability events and see which §1.1455 key data elements are missing, which rules fail, and what to fix first. No signup. Nothing is stored — the evaluation is stateless and the file never leaves the request.
  - paragraph: "Up to 500 events and 2 MB per file. Column headers are matched flexibly, so “Lot #”, “Event Type”, and “UOM” are understood as written."
  - text: Choose a CSV of traceability events
  - button "Choose a CSV of traceability events"
  - text: No file handy?
  - button "Run a sample FTL chain"
  - alert:
    - paragraph: The sandbox could not evaluate that file (HTTP 502).
    - link "Explore the interactive demo instead":
      - /url: /demo
- contentinfo "Site footer":
  - link "RegEngine home":
    - /url: /
    - text: RegEngine
  - paragraph: Food traceability compliance for farms and food companies.
  - heading "Product" [level=2]
  - link "Pricing":
    - /url: /pricing
  - link "Product Validation":
    - /url: /case-studies
  - link "Integrations":
    - /url: /integrations
  - link "Get Started":
    - /url: /signup
  - heading "Free Tools" [level=2]
  - link "FTL List Checker":
    - /url: /tools/ftl-checker
  - link "View all tools →":
    - /url: /tools
  - heading "Developers" [level=2]
  - link "Developer Portal":
    - /url: /developer/portal
  - link "API Docs":
    - /url: /docs/api
  - link "Quickstart":
    - /url: /docs/quickstart
  - link "SDKs":
    - /url: /docs/sdks
  - link "Verify (Proof)":
    - /url: /proof
  - link "Changelog":
    - /url: /docs/changelog
  - heading "Company" [level=2]
  - link "About":
    - /url: /about
  - link "Blog":
    - /url: /blog
  - link "Contact":
    - /url: /contact
  - link "Security":
    - /url: /security
  - link "Trust Center":
    - /url: /trust
  - link "Privacy":
    - /url: /privacy
  - link "DPA":
    - /url: /dpa
  - link "Terms":
    - /url: /terms
  - link "Log In":
    - /url: /login
  - link "Sign Up":
    - /url: /signup
  - text: "FSMA 204 Enforcement: July 20, 2028 © 2026 RegEngine LLC All rights reserved."
  - link "DPA":
    - /url: /dpa
  - button "Manage cookie preferences": Cookie Preferences
  - text: "Verify our exports yourself:"
  - code: verify_chain.py
- region "Notifications (F8)":
  - list
- alert
- button "Open accessibility settings"
- dialog "Cookie consent":
  - heading "We use cookies" [level=2]
  - paragraph:
    - text: Essential sessions. Analytics only if accepted.
    - link "Privacy Policy":
      - /url: /privacy
    - text: .
  - button "Accept analytics"
  - button "Essential only"
```

# Test source

```ts
  1   | /**
  2   |  * Sandbox front door E2E — #2757.
  3   |  *
  4   |  * Walks the funnel the compare pages advertise: comparison CTA → sandbox →
  5   |  * rendered FSMA 204 diagnosis for a sample FTL chain.
  6   |  *
  7   |  * The sandbox evaluator is an experimental router (server/main.py
  8   |  * _EXPERIMENTAL_ROUTERS) and is auto-disabled in production, so this spec
  9   |  * probes it at runtime and asserts the correct behaviour for whichever state
  10  |  * the target deployment is in — same convention as demo-smoke.spec.ts:
  11  |  *
  12  |  *   mounted    → CTA lands on /sandbox and the sample CSV evaluates end to end.
  13  |  *   unmounted  → CTA lands on /demo, no page promises a CSV sandbox, and a
  14  |  *                direct visit to /sandbox explains itself instead of 404ing.
  15  |  *
  16  |  * Either way the invariant under test is the one #2730 broke: CTA copy and CTA
  17  |  * destination must agree.
  18  |  */
  19  | import { expect, test, type Page } from '@playwright/test';
  20  | 
  21  | const COMPARE_PAGES = ['/compare/tracegains', '/compare/foodlogiq', '/compare/repositrak'];
  22  | 
  23  | const SANDBOX_PROMISE = /drop your csv in the sandbox/i;
  24  | 
  25  | async function sandboxEvaluatorMounted(page: Page): Promise<boolean> {
  26  |     const res = await page.request.post('/api/ingestion/api/v1/sandbox/evaluate', {
  27  |         data: { csv: 'cte_type\nshipping\n' },
  28  |         failOnStatusCode: false,
  29  |     });
  30  |     // 404 = router not mounted on this deployment. Anything else (200, 400,
  31  |     // 429) means the endpoint is there and answering.
  32  |     return res.status() !== 404;
  33  | }
  34  | 
  35  | test.describe('sandbox front door (#2757)', () => {
  36  |     test('/sandbox is a real route, never a 404', async ({ page }) => {
  37  |         const res = await page.goto('/sandbox');
  38  |         expect(res?.status()).toBe(200);
  39  |         // Whichever state we are in, the page says something specific.
  40  |         await expect(
  41  |             page.getByRole('heading', { name: /FSMA 204 Sandbox|not enabled on this deployment/i }),
  42  |         ).toBeVisible();
  43  |     });
  44  | 
  45  |     for (const comparePath of COMPARE_PAGES) {
  46  |         test(`${comparePath} CTA copy matches where it goes`, async ({ page }) => {
  47  |             const mounted = await sandboxEvaluatorMounted(page);
  48  |             await page.goto(comparePath);
  49  | 
  50  |             const cta = page
  51  |                 .getByRole('link', { name: mounted ? /Try the Sandbox/i : /interactive demo/i })
  52  |                 .first();
  53  |             await expect(cta).toBeVisible();
  54  | 
  55  |             const body = await page.locator('body').innerText();
  56  |             if (mounted) {
  57  |                 expect(body).toMatch(SANDBOX_PROMISE);
  58  |             } else {
  59  |                 // The #2730 failure: sandbox prose above a button going elsewhere.
  60  |                 expect(body).not.toMatch(SANDBOX_PROMISE);
  61  |             }
  62  | 
  63  |             await cta.click();
  64  |             await expect(page).toHaveURL(new RegExp(mounted ? '/sandbox$' : '/demo'));
  65  |         });
  66  |     }
  67  | 
  68  |     test('homepage #sandbox anchor resolves to the same destination', async ({ page }) => {
  69  |         const mounted = await sandboxEvaluatorMounted(page);
  70  |         await page.goto('/#sandbox');
  71  | 
  72  |         const section = page.locator('#sandbox');
  73  |         await expect(section).toBeVisible();
  74  | 
  75  |         const cta = section.getByRole('link').first();
  76  |         await cta.click();
  77  |         await expect(page).toHaveURL(new RegExp(mounted ? '/sandbox$' : '/demo'));
  78  |     });
  79  | 
  80  |     test('sample FTL CSV evaluates and renders a diagnosis', async ({ page }) => {
  81  |         test.skip(
  82  |             !(await sandboxEvaluatorMounted(page)),
  83  |             'sandbox router not mounted on this deployment (experimental, prod-disabled)',
  84  |         );
  85  | 
  86  |         await page.goto('/sandbox');
  87  |         await page.getByRole('button', { name: /Run a sample FTL chain/i }).click();
  88  | 
> 89  |         await expect(page.getByText('FSMA 204 Sandbox Diagnosis')).toBeVisible({ timeout: 30_000 });
      |                                                                    ^ Error: expect(locator).toBeVisible() failed
  90  | 
  91  |         // The sample chain is deliberately imperfect — a clean result would mean
  92  |         // the rules did not run.
  93  |         await expect(page.getByText('SV-20260115-001').first()).toBeVisible();
  94  |         await expect(page.getByText(/need attention|NEEDS CORRECTION/i).first()).toBeVisible();
  95  |     });
  96  | 
  97  |     test('unmounted evaluator explains itself instead of hanging', async ({ page }) => {
  98  |         test.skip(
  99  |             await sandboxEvaluatorMounted(page),
  100 |             'sandbox router is mounted — the unavailable path does not apply',
  101 |         );
  102 | 
  103 |         await page.goto('/sandbox');
  104 |         await expect(page.getByText(/not enabled on this deployment/i)).toBeVisible();
  105 |         await expect(page.getByRole('link', { name: /interactive demo/i })).toBeVisible();
  106 |     });
  107 | });
  108 | 
```