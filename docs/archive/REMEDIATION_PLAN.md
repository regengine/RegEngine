# RegEngine Production Remediation Plan

**Date:** March 20, 2026
**Site:** regengine.co
**Prepared for:** Christopher Sellers, Founder

---

## Root Cause Analysis

### The #1 Problem: Vercel Dashboard Env Vars Override vercel.json

Your `vercel.json` has the **correct** public Railway URLs:

```
COMPLIANCE_SERVICE_URL = https://intelligent-essence-production.up.railway.app
INGESTION_SERVICE_URL  = https://believable-respect-production-2fb3.up.railway.app
NEXT_PUBLIC_API_BASE_URL = https://regengine-production.up.railway.app
```

But the **Vercel dashboard** has Railway **internal** URLs that override them:

```
COMPLIANCE_SERVICE_URL = http://intelligent-essence.railway.internal:8888  ← WRONG
INGESTION_SERVICE_URL  = http://believable-respect.railway.internal:8888  ← WRONG
```

Vercel dashboard env vars take precedence over `vercel.json` env vars. So the internal URLs win, and Vercel serverless functions can't reach them (`.railway.internal` is only accessible from within Railway's private network).

**Additionally:** `ADMIN_SERVICE_URL` is missing entirely — the admin API proxy falls back to `http://localhost:8400` which is unreachable from Vercel.

### Impact Chain

```
Wrong service URLs → All backend API calls fail →
  → Compliance returns 500
  → Suppliers returns 401 (admin service unreachable)
  → System health fails
  → Dashboard shows seed data (no real data available)
```

---

## Immediate Fix (15 minutes)

### Step 1: Delete or update these Vercel dashboard env vars

Go to: https://vercel.com/petrefiedthunders-projects/regengine/settings/environment-variables

For **Production** environment, update these three values:

| Variable | Current (WRONG) | Correct Value |
|----------|-----------------|---------------|
| `COMPLIANCE_SERVICE_URL` | `http://intelligent-essence.railway.internal:8888` | `https://intelligent-essence-production.up.railway.app` |
| `INGESTION_SERVICE_URL` | `http://believable-respect.railway.internal:8888` | `https://believable-respect-production-2fb3.up.railway.app` |

**Option A (recommended):** Delete these two vars from the Vercel dashboard entirely. The correct values in `vercel.json` will then be used automatically.

**Option B:** Update the values to match the public URLs above.

### Step 2: Add missing ADMIN_SERVICE_URL

Add a new env var for **all environments**:

```
ADMIN_SERVICE_URL = https://regengine-production.up.railway.app
```

(This is your main Railway app URL that serves the admin API.)

### Step 3: Redeploy

After updating env vars, trigger a redeployment:

```bash
# From the frontend directory:
git push  # or trigger via Vercel dashboard
```

Vercel reads env vars at build time for `NEXT_PUBLIC_*` vars and at runtime for server-side vars. A fresh deployment ensures everything picks up the new values.

---

## Code Fixes Applied (This Session)

### 1. Settings Page — Removed Hardcoded Seed Data

**File:** `frontend/src/app/dashboard/settings/page.tsx`

**Before:** Company profile hardcoded to "Acme Food Distribution" with fake contact info. Plan card hardcoded to "Growth Plan $1,079/mo".

**After:**
- Profile populated from tenant context (`useOrganizations()`) and auth user (`useAuth()`)
- Plan card reads from `useCurrentSubscription()` hook (fetches from Stripe via billing API)
- Shows loading state while subscription data loads
- Empty fields for new accounts instead of fake data

### 2. Dashboard — Removed Hardcoded Retailer Type

**File:** `frontend/src/app/dashboard/page.tsx`

**Before:** `getQuickActions('retailer')` — always showed retailer-specific actions regardless of tenant type.

**After:** Derives tenant type from `currentOrg?.plan` with sensible defaults. Supplier and system admin tenants now see their correct quick actions.

### 3. Dashboard Sidebar — Removed Hardcoded "Growth" Plan

**File:** `frontend/src/app/dashboard/layout.tsx`

**Before:** Sidebar footer hardcoded "Growth" plan with "5 facilities · 50K events/mo".

**After:** Generic "Manage Plan" link to settings page. No misleading plan information.

---

## Remaining Issues & Long-Term Fixes

### F-003: Compliance Dashboard 500 Error

**Root cause:** `COMPLIANCE_SERVICE_URL` points to Railway internal address.
**Fix:** Update the env var (Step 1 above). Once the URL is correct, the compliance proxy will reach the service.
**Verify:** After fixing, visit `/dashboard/compliance` — should load without 500.

### F-004: Suppliers 401 Unauthorized

**Root cause:** `ADMIN_SERVICE_URL` is missing. The admin proxy falls back to `localhost:8400`.
**Fix:** Add `ADMIN_SERVICE_URL` (Step 2 above).
**Secondary concern:** Even with the correct URL, the admin service needs to accept the API key being sent (`x-regengine-api-key`). Verify the admin service's auth middleware matches.

### F-005: System Health "Failed to Load"

**Root cause:** Health endpoint calls admin service, which is unreachable.
**Fix:** Resolves automatically after ADMIN_SERVICE_URL is set correctly.
**Long-term:** Implement a `/health` aggregation endpoint that returns partial results when some services are down.

### F-006: FSMA Dashboard Redirect

**Root cause:** Unclear. The FSMA page exists at `src/app/fsma/dashboard/page.tsx` and no explicit redirect was found in code. Possible causes:
1. The `useComplianceScore()` hook fails (compliance service unreachable) and an error boundary redirects
2. The page is not deployed on the `main` branch (only on `feat/billing-checkout-auth-flow`)
3. Supabase auth check in the page fails silently

**Action:** After fixing the service URLs, test `/fsma/dashboard` again. If still redirecting, check:
- Is the file present on the deployed branch?
- Does `useComplianceScore()` throw an unhandled error?

### F-007: Footer Missing Developer Links

**Root cause:** PR #175 / `feat/billing-checkout-auth-flow` branch has the updated footer but hasn't been merged to `main`.
**Fix:** Merge the feature branch to main.

### F-008: Ghost Button on Homepage

**Root cause:** Not found in static code analysis. Both CTA buttons have visible styling. May be:
- A conditional render based on feature flag or user state
- A CSS specificity issue in production build
- An element from a third-party script (Posthog, Sentry, etc.)

**Action:** Inspect with Chrome DevTools on production after other fixes are deployed.

---

## Architecture Recommendations (Long-Term)

### 1. Service URL Management

**Problem:** Service URLs are duplicated across `vercel.json`, Vercel dashboard, and `.env` files. Dashboard overrides `vercel.json`, creating silent conflicts.

**Recommendation:**
- Use `vercel.json` as the single source of truth for service URLs
- Remove all service URL overrides from the Vercel dashboard
- Or: remove URLs from `vercel.json` and only use dashboard (pick one, not both)

### 2. Add Health Check Middleware

Create a `/api/health` endpoint that tests connectivity to each backend service before the app starts serving traffic. This turns "mysterious 500s" into clear "service X is unreachable" messages.

```typescript
// frontend/src/app/api/health/route.ts
export async function GET() {
    const services = {
        admin: process.env.ADMIN_SERVICE_URL || process.env.NEXT_PUBLIC_ADMIN_URL,
        compliance: process.env.COMPLIANCE_SERVICE_URL,
        ingestion: process.env.INGESTION_SERVICE_URL,
    };

    const results = await Promise.allSettled(
        Object.entries(services).map(async ([name, url]) => {
            if (!url) return { name, status: 'not_configured' };
            try {
                const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
                return { name, status: res.ok ? 'healthy' : 'unhealthy', code: res.status };
            } catch {
                return { name, status: 'unreachable', url: url.replace(/\/\/.*@/, '//***@') };
            }
        })
    );

    return Response.json({ services: results.map(r => r.status === 'fulfilled' ? r.value : r.reason) });
}
```

### 3. Graceful Degradation in UI Components

Every dashboard component that fetches from a backend service should handle failure gracefully:

```typescript
// Instead of showing a raw error or crashing:
if (error) return <ServiceUnavailable service="compliance" />;

// Show a clear message with retry:
function ServiceUnavailable({ service }: { service: string }) {
    return (
        <Card>
            <CardContent className="py-8 text-center">
                <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-3" />
                <p className="text-sm font-medium">Unable to reach {service} service</p>
                <p className="text-xs text-muted-foreground mt-1">This feature requires backend connectivity.</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => window.location.reload()}>
                    Retry
                </Button>
            </CardContent>
        </Card>
    );
}
```

### 4. Tenant Data Architecture

The `Organization` type only has `id`, `name`, `slug`, `plan`. For proper multi-tenant support, extend it:

```typescript
interface Organization {
    id: string;
    name: string;
    slug: string;
    plan: string;
    type: 'retailer' | 'supplier' | 'manufacturer' | 'distributor' | 'grower' | 'importer';
    primary_contact?: string;
    contact_email?: string;
    phone?: string;
    address?: string;
    fei_number?: string;
}
```

And create a Supabase migration to add these columns to `fsma.organizations`.

### 5. Billing Display from Stripe

The `useCurrentSubscription()` hook already exists and calls `/v1/billing/subscriptions/current`. Once the ingestion service is reachable (after fixing URLs), this will return real Stripe data. The settings page code fix in this session already uses this hook.

Long-term: also wire up `usePricingTiers()` in the CheckoutWizard component to replace the hardcoded PLANS array.

---

## Execution Priority

| Priority | Action | Time | Impact |
|----------|--------|------|--------|
| 1 | Fix/delete Vercel dashboard service URLs | 5 min | Unblocks compliance, suppliers, health |
| 2 | Add ADMIN_SERVICE_URL to Vercel | 2 min | Unblocks admin API, suppliers, review |
| 3 | Redeploy to production | 5 min | Activates all URL fixes |
| 4 | Merge feat/billing-checkout-auth-flow to main | 15 min | Footer, route fixes |
| 5 | Commit code fixes from this session | 5 min | Seed data, billing display |
| 6 | Test all pages end-to-end | 30 min | Verify everything works |
| 7 | Extend Organization schema | 1-2 days | Proper multi-tenant profiles |
| 8 | Add health check endpoint | 1 day | Operational visibility |
