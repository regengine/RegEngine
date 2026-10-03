# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: rbac-gates.spec.ts >> RBAC Gates >> Unauthenticated users are redirected to login
- Location: tests/e2e/rbac-gates.spec.ts:45:9

# Error details

```
Test timeout of 45000ms exceeded.
```

```
Error: locator.click: Test timeout of 45000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: /^Password$/ })

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - link "Skip to content" [ref=e2] [cursor=pointer]:
    - /url: "#main-content"
  - main "Page content" [ref=e3]:
    - generic [ref=e5]:
      - link "RegEngine" [ref=e7] [cursor=pointer]:
        - /url: /
      - heading "Continue to RegEngine" [level=1] [ref=e14]
      - paragraph [ref=e15]: Enter your email to receive a one-time code, or use a registered passkey.
      - generic [ref=e16]:
        - generic [ref=e17]:
          - generic [ref=e18]:
            - generic [ref=e19]: Email address
            - textbox "Email address" [ref=e21]:
              - /placeholder: name@company.com
          - button "Continue" [ref=e22]
        - generic [ref=e26]: or
        - button "Sign in with passkey" [ref=e29]
      - generic [ref=e40]: Enterprise policy is enforced before codes are sent.
      - link "Return to RegEngine.co" [ref=e49] [cursor=pointer]:
        - /url: /
  - region "Notifications (F8)":
    - list
  - alert [ref=e50]
  - button "Open accessibility settings" [ref=e51]
```

# Test source

```ts
  1  | import { expect, type Page } from '@playwright/test';
  2  | 
  3  | export async function selectPasswordLogin(page: Page): Promise<void> {
> 4  |     await page.getByRole('button', { name: /^Password$/ }).click();
     |                                                            ^ Error: locator.click: Test timeout of 45000ms exceeded.
  5  |     await expect(page.locator('input[type="password"]')).toBeVisible();
  6  | }
  7  | 
  8  | export async function fillPasswordLogin(page: Page, email: string, password: string): Promise<void> {
  9  |     await selectPasswordLogin(page);
  10 |     await page.fill('input[type="email"]', email);
  11 |     await page.fill('input[type="password"]', password);
  12 | }
  13 | 
```