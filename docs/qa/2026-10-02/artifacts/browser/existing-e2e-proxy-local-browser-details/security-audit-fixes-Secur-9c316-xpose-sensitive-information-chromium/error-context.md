# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: security-audit-fixes.spec.ts >> Security Audit Fixes >> Auth Guard Visibility & Error Handling >> Error pages do not expose sensitive information
- Location: tests/e2e/security-audit-fixes.spec.ts:749:13

# Error details

```
Error: expect(received).toBeFalsy()

Received: ["config"]
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
        - generic [ref=e25]: or
        - button "Sign in with passkey" [ref=e28]
      - generic [ref=e38]: Enterprise policy is enforced before codes are sent.
      - link "Return to RegEngine.co" [ref=e45] [cursor=pointer]:
        - /url: /
  - region "Notifications (F8)":
    - list
  - alert [ref=e46]
  - button "Open accessibility settings" [ref=e47]
```

# Test source

```ts
  665 |                 // Deliberately omitting CSRF headers — /api/session POST is CSRF-exempt
  666 |                 // (it IS the CSRF token issuance endpoint). Test a different guarded endpoint.
  667 |             });
  668 | 
  669 |             // /api/session POST is CSRF-exempt; it should succeed (200) or fail with auth (401/403)
  670 |             // We just verify it's not a 500.
  671 |             expect(response.status()).not.toBe(500);
  672 |         });
  673 | 
  674 |     });
  675 | 
  676 |     // ============================================================================
  677 |     // 5. AUTH GUARD VISIBILITY & ERROR HANDLING
  678 |     // ============================================================================
  679 | 
  680 |     test.describe('Auth Guard Visibility & Error Handling', () => {
  681 | 
  682 |         test('Unauthenticated users redirected from protected routes', async ({ page, context }) => {
  683 |             test.setTimeout(60000);
  684 | 
  685 |             // Create a new context without authentication
  686 |             const unauthContext = await context.browser()?.newContext() ?? context;
  687 | 
  688 |             // Access protected route without logging in
  689 |             const unauthPage = await unauthContext.newPage();
  690 | 
  691 |             await unauthPage.goto('/dashboard', { waitUntil: 'networkidle' });
  692 | 
  693 |             // Should redirect to login
  694 |             const isOnLoginPage =
  695 |                 unauthPage.url().includes('/login') ||
  696 |                 unauthPage.url().includes('/auth') ||
  697 |                 (await unauthPage.getByText(/sign in|log in|login/i).count()) > 0;
  698 | 
  699 |             expect(isOnLoginPage).toBe(true);
  700 | 
  701 |             // Try other protected routes
  702 |             await unauthPage.goto('/sysadmin', { waitUntil: 'networkidle' });
  703 |             const isRedirected =
  704 |                 unauthPage.url().includes('/login') ||
  705 |                 unauthPage.url().includes('/auth');
  706 | 
  707 |             expect(isRedirected).toBe(true);
  708 | 
  709 |             await unauthPage.close();
  710 |         });
  711 | 
  712 |         test('Protected API responses do not leak data in error messages', async ({ page, context }) => {
  713 |             test.setTimeout(60000);
  714 | 
  715 |             // Intercept API responses to check error messages
  716 |             const apiErrors: { url: string; message: string }[] = [];
  717 | 
  718 |             context.on('response', async response => {
  719 |                 if (!response.ok() && response.url().includes('/api')) {
  720 |                     const text = await response.text();
  721 |                     apiErrors.push({
  722 |                         url: response.url(),
  723 |                         message: text
  724 |                     });
  725 |                 }
  726 |             });
  727 | 
  728 |             // Try to access protected API without auth via the Next.js proxy
  729 |             const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001';
  730 |             const response = await context.request.get(`${baseURL}/api/admin/v1/users`);
  731 | 
  732 |             // Verify error response doesn't leak sensitive info
  733 |             const responseText = await response.text();
  734 | 
  735 |             // Should not contain:
  736 |             // - User IDs, emails, or names
  737 |             // - Database details
  738 |             // - Internal paths or config
  739 |             // - SQL errors
  740 |             const leaksData =
  741 |                 /users?\.id|users?\.email|SELECT|FROM|WHERE|table|database|config|api_key|secret/i.test(responseText);
  742 | 
  743 |             expect(leaksData).toBe(false);
  744 | 
  745 |             // Should return appropriate error status (401 = unauthenticated, 403 = forbidden, 404 = not found)
  746 |             expect([401, 403, 404]).toContain(response.status());
  747 |         });
  748 | 
  749 |         test('Error pages do not expose sensitive information', async ({ page }) => {
  750 |             test.setTimeout(60000);
  751 | 
  752 |             // Navigate to non-existent protected route
  753 |             await page.goto('/admin/nonexistent', { waitUntil: 'networkidle' });
  754 | 
  755 |             // Get page content
  756 |             const pageContent = await page.textContent('body');
  757 | 
  758 |             // Error messages should not contain sensitive backend details.
  759 |             // Note: "password" is excluded — it legitimately appears as a form
  760 |             // label on the login page (which is where auth redirects land).
  761 |             const leaksSensitiveInfo = pageContent?.match(
  762 |                 /database|config|api_key|secret_key|sql|stack trace|internal server/i
  763 |             );
  764 | 
> 765 |             expect(leaksSensitiveInfo).toBeFalsy();
      |                                        ^ Error: expect(received).toBeFalsy()
  766 |         });
  767 | 
  768 |         test('Login page redirects authenticated users', async ({ page }) => {
  769 |             test.skip(!hasAdminAuthenticatedE2E, adminAuthenticatedE2ESkipReason);
  770 |             test.setTimeout(60000);
  771 | 
  772 |             await loginAsAdmin(page);
  773 | 
  774 |             // Now try to navigate to /login
  775 |             await page.goto('/login');
  776 |             await page.waitForLoadState('networkidle');
  777 | 
  778 |             // Should redirect to dashboard/home, OR the login page should
  779 |             // at least not show the login form (some apps keep the /login URL
  780 |             // but show a "you're already logged in" message or auto-redirect).
  781 |             // Client-side redirect from LoginClient.tsx fires after network idle.
  782 |             const isRedirected =
  783 |                 page.url().includes('/dashboard') ||
  784 |                 page.url().includes('/sysadmin') ||
  785 |                 page.url().includes('/home') ||
  786 |                 page.url().includes('/onboarding');
  787 | 
  788 |             if (!isRedirected) {
  789 |                 // If still on /login, verify at least the login form isn't
  790 |                 // asking for credentials (some SPAs redirect client-side)
  791 |                 await page.waitForTimeout(2000);
  792 |                 const isRedirectedAfterWait =
  793 |                     page.url().includes('/dashboard') ||
  794 |                     page.url().includes('/sysadmin');
  795 |                 // Accept either redirect or staying on login (app design choice)
  796 |                 expect(isRedirectedAfterWait || page.url().includes('/login')).toBe(true);
  797 |             }
  798 |         });
  799 | 
  800 |     });
  801 | 
  802 |     // ============================================================================
  803 |     // 6. INTEGRATION TESTS
  804 |     // ============================================================================
  805 | 
  806 |     test.describe('Integration: Full Auth & Security Flow', () => {
  807 | 
  808 |         test('Complete login, navigate, security settings, logout flow', async ({ page, context }) => {
  809 |             test.skip(!hasAdminAuthenticatedE2E, adminAuthenticatedE2ESkipReason);
  810 |             test.setTimeout(90000);
  811 | 
  812 |             // 1. Login
  813 |             await loginAsAdmin(page);
  814 | 
  815 |             // Verify re_access_token HTTP-only cookie is set
  816 |             let cookies = await context.cookies();
  817 |             const authCookie = cookies.find(isReAccessToken);
  818 |             expect(authCookie).toBeDefined();
  819 |             expect(authCookie?.httpOnly).toBe(true);
  820 | 
  821 |             // 2. Navigate to security settings
  822 |             // /settings/security renders real security content (wildcard redirect removed).
  823 |             await page.goto('/settings/security');
  824 |             await page.waitForLoadState('networkidle');
  825 | 
  826 |             // Should not lose session
  827 |             const urlAfterNav = page.url();
  828 |             expect(urlAfterNav).toMatch(/\/settings\/security|\/dashboard\/settings/);
  829 |             expect(urlAfterNav).not.toContain('/login');
  830 | 
  831 |             // 3. Verify no tokens in localStorage
  832 |             await verifyNoTokensInLocalStorage(page);
  833 | 
  834 |             // 4. Navigate to dashboard
  835 |             await page.goto('/dashboard');
  836 | 
  837 |             // 5. Attempt logout
  838 |             const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]').first();
  839 |             await expect(logoutButton).toBeVisible();
  840 |             await logoutButton.click();
  841 | 
  842 |             // Should redirect to login
  843 |             await expect(page).toHaveURL(/\/login|\/auth/);
  844 | 
  845 |             // re_access_token cookie should be cleared
  846 |             cookies = await context.cookies();
  847 |             const authCleared = !cookies.some(isReAccessToken);
  848 |             expect(authCleared).toBe(true);
  849 |         });
  850 | 
  851 |         test('Sysadmin can access admin routes, regular user cannot', async ({ browser }) => {
  852 |             // Requires a dedicated sysadmin account (is_sysadmin=true).
  853 |             // The test user created by globalSetup is a regular org owner — not sysadmin.
  854 |             // The /sysadmin page checks user.is_sysadmin client-side and redirects non-sysadmins.
  855 |             test.skip(!hasDedicatedAdmin, 'Requires a dedicated sysadmin account — set TEST_ADMIN_EMAIL + TEST_ADMIN_PASSWORD');
  856 |             test.skip(!hasAuthenticatedE2E, authenticatedE2ESkipReason);
  857 |             test.setTimeout(120000);
  858 | 
  859 |             // Test as admin
  860 |             const adminContext = await browser.newContext();
  861 |             const adminPage = await adminContext.newPage();
  862 | 
  863 |             await adminPage.goto('/login');
  864 |             await fillPasswordLogin(adminPage, ADMIN_EMAIL, ADMIN_PASSWORD);
  865 |             await adminPage.click('button[type="submit"]');
```