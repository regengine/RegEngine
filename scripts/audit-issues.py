#!/usr/bin/env python3
"""
RegEngine Full Audit — GitHub Issue Creator
Run: GITHUB_TOKEN=ghp_xxx python audit-issues.py
"""
import os
import sys
import time

try:
    from github import Github
except ImportError:
    print("pip install PyGithub")
    sys.exit(1)

REPO = "PetrefiedThunder/RegEngine"
TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    print("Set GITHUB_TOKEN env var first.")
    sys.exit(1)

from github import Auth
g = Github(auth=Auth.Token(TOKEN))
repo = g.get_repo(REPO)

# Try to create labels, skip if no permission
LABEL_COLORS = {"P0": "b60205", "P1": "d93f0b", "P2": "fbca04",
                "security": "e11d48", "frontend": "1d76db", "backend": "0e8a16",
                "marketing": "c5def5", "infra": "bfd4f2", "onboarding": "7057ff",
                "auth": "f9d0c4", "ux": "d4c5f9", "compliance": "006b75",
                "tech-debt": "ededed", "seo": "b4a7d6", "legal": "fef2c0"}

existing = {l.name for l in repo.get_labels()}
for name, color in LABEL_COLORS.items():
    if name not in existing:
        try:
            repo.create_label(name, color)
            print(f"  Created label: {name}")
        except Exception:
            print(f"  Skipped label (no permission): {name}")

ISSUES = [
    # ===================== P0 — BROKEN / BLOCKING =====================
    {
        "title": "[P0][security] Rotate exposed credentials in .env and .env.local",
        "labels": ["P0", "security", "infra"],
        "body": """## Problem
`.env` contains hardcoded secrets (DB passwords, API keys, admin master key, internal secrets). `.env.local` contains Supabase credentials. If either file is in git history, all secrets are compromised.

## Files
- `.env` — lines 6, 13, 16, 23, 32, 46, 49
- `frontend/.env.local`

## Action
1. Verify both files are in `.gitignore` (and not in git history)
2. Rotate ALL secrets: Supabase anon key, DB password, admin master key, internal secret, scheduler key, auth secret
3. Add `.env` validation that rejects default/dev values in production
4. Run `git log --all --full-history -- .env .env.local` to check exposure
""",
    },
    {
        "title": "[P0][security] Admin master key lacks rate limiting — brute force risk",
        "labels": ["P0", "security", "backend"],
        "body": """## Problem
`verify_admin_key()` in admin service compares against a single master key with no rate limiting, lockout, or audit logging. Allows unlimited brute-force attempts.

## File
- `services/admin/app/routes.py` — lines 121-143

## Action
1. Add rate limiting (e.g., 5 attempts per minute per IP)
2. Add audit logging for failed admin auth attempts
3. Consider replacing single master key with proper admin auth (OAuth, short-lived tokens)
""",
    },
    # ===================== P1 — SIGNIFICANT GAPS =====================
    {
        "title": "[P1][auth] Session cookie write failure silently ignored during login",
        "labels": ["P1", "auth", "frontend"],
        "body": """## Problem
If `/api/session` fails when writing HTTP-only cookies, `login()` and `signup()` still update React state and redirect to dashboard. User appears logged in client-side but has no server-side session — next page load fails.

## File
- `frontend/src/lib/auth-context.tsx` — lines 90-95

## Action
- Await `setSessionCookies()` result and block redirect on failure
- Show error toast if cookie write fails
""",
    },
    {
        "title": "[P1][auth] JWT revocation gap — revoked sessions valid for up to 15 min",
        "labels": ["P1", "security", "auth", "frontend"],
        "body": """## Problem
Middleware runs in Edge Runtime and cannot reach Redis for revocation checks. Revoked tokens remain valid until JWT `exp` claim (~15 min).

## File
- `frontend/src/middleware.ts` — lines 129-134 (documented in code comments)

## Action
- Reduce JWT TTL to <5 min to shrink revocation window
- Or implement lightweight revocation cache in Edge Runtime
- Document this tradeoff for the team
""",
    },
    {
        "title": "[P1][auth] CSRF exemption for Bearer tokens is too broad",
        "labels": ["P1", "security", "auth", "frontend"],
        "body": """## Problem
Any request with a Bearer token bypasses CSRF checks. If a compromised API token is used in a browser context (CORS), CSRF protection is defeated.

## File
- `frontend/src/middleware.ts` — lines 318-319

## Action
- Restrict CSRF exemption to non-browser contexts (check Origin/Referer headers)
- Or require API tokens to use a separate auth header
""",
    },
    {
        "title": "[P1][auth] Dual auth system (custom JWT + Supabase) creates inconsistency risk",
        "labels": ["P1", "auth", "tech-debt", "frontend"],
        "body": """## Problem
Middleware checks custom JWT first, then falls back to Supabase. If both exist and disagree (e.g., custom JWT valid but Supabase expired), behavior is unpredictable. Tenant status check only applies to custom JWT path — suspended tenants with Supabase sessions still get through.

## Files
- `frontend/src/lib/auth-context.tsx`
- `frontend/src/middleware.ts` — lines 227-291

## Action
- Add cross-validation: if custom JWT exists, verify Supabase session also exists
- Check tenant_status in both auth paths
- Document the preference order
""",
    },
    {
        "title": "[P1][onboarding] Incomplete facility form — placeholder address and invalid ZIP default",
        "labels": ["P1", "onboarding", "frontend"],
        "body": """## Problem
- Street address hardcoded as `'--'` with TODO comment "we'll add the street address input later"
- ZIP code defaults to `'00000'` when empty — writes invalid data to DB

## File
- `frontend/src/app/onboarding/setup/facility/page.tsx` — lines 66, 69

## Action
1. Implement street address input field
2. Make ZIP required with validation, or make it truly optional (null, not '00000')
""",
    },
    {
        "title": "[P1][onboarding] Facility ID not validated between onboarding steps",
        "labels": ["P1", "onboarding", "frontend"],
        "body": """## Problem
Facility ID passed as query param to next onboarding step is never validated. If the API call silently fails or returns unexpected format, user proceeds with invalid state.

## File
- `frontend/src/app/onboarding/setup/facility/page.tsx` — line 78

## Action
- Validate facility ID format before navigation
- Show error if facility creation failed
""",
    },
    {
        "title": "[P1][onboarding] completeOnboarding failure silently swallowed",
        "labels": ["P1", "onboarding", "frontend"],
        "body": """## Problem
If `completeOnboarding()` fails, the error is caught and the user is still redirected to `/dashboard`. Onboarding may be left incomplete server-side.

## File
- `frontend/src/app/onboarding/setup/ftl-check/page.tsx` — line 125

## Action
- Show error banner on failure with retry option
- Don't redirect to dashboard until onboarding is confirmed complete
""",
    },
    {
        "title": "[P1][frontend] Generic error messages across sign-up and onboarding",
        "labels": ["P1", "ux", "frontend"],
        "body": """## Problem
Multiple flows show generic "something went wrong" messages without distinguishing network errors, validation errors, rate limits, or server errors.

## Files
- `frontend/src/app/signup/page.tsx` — line 56
- `frontend/src/app/onboarding/setup/facility/page.tsx` — line 80

## Action
- Distinguish error categories (validation, network, server, rate limit)
- Include support link or troubleshooting guidance
""",
    },
    {
        "title": "[P1][security] CSP in report-only mode with unsafe-inline and unsafe-eval",
        "labels": ["P1", "security", "infra"],
        "body": """## Problem
Content-Security-Policy is set to report-only (not enforced). It also allows `'unsafe-inline'` and `'unsafe-eval'` for scripts, defeating XSS protection.

## File
- `frontend/next.config.js` — lines 53-66

## Action
1. Move from report-only to enforced CSP
2. Implement nonce-based script loading to remove `unsafe-inline`/`unsafe-eval`
3. Implement CSP violation reporting endpoint
""",
    },
    {
        "title": "[P1][security] Hardcoded production Railway URLs in vercel.json",
        "labels": ["P1", "security", "infra"],
        "body": """## Problem
Production service URLs (Railway endpoints) are hardcoded in `vercel.json`, exposing infrastructure topology. These should be environment variables.

## File
- `frontend/vercel.json` — lines 24-26

## Action
- Move service URLs to Vercel environment variables
- Reference via `$ENV_VAR` in vercel.json rewrites
""",
    },
    {
        "title": "[P1][security] Default credentials for Grafana, MinIO, and Postgres exporter",
        "labels": ["P1", "security", "infra"],
        "body": """## Problem
Multiple services use insecure defaults in docker-compose:
- Grafana defaults to `admin` password if env var not set
- MinIO uses `minioadmin/minioadmin123` fallback
- Postgres exporter has plaintext password in DATA_SOURCE_NAME

## File
- `docker-compose.yml` — lines 307-308, 448, 481-490

## Action
- Use `${VAR:?error}` syntax to require secrets (fail instead of defaulting)
- Move all passwords to Docker secrets or env files not in git
""",
    },
    {
        "title": "[P1][backend] FSMA 204 compliance requirements hardcoded in Python",
        "labels": ["P1", "compliance", "backend"],
        "body": """## Problem
All FSMA 204 compliance rules, required fields, and validation logic are hardcoded as Python constants. Updating compliance rules requires code changes and redeployment. Cannot customize per-tenant or per-framework version.

## File
- `services/compliance/app/routes.py` — lines 80-196

## Action
- Move compliance rules to database or configuration
- Support versioned rule sets (FSMA 204 may be updated)
- Allow per-tenant customization
""",
    },
    {
        "title": "[P1][backend] Compliance validation doesn't check data types, only presence",
        "labels": ["P1", "compliance", "backend"],
        "body": """## Problem
`validate_config()` only checks field presence, not types. A config with `{"tlc": null}` passes. No enum validation for `cte_type`. `.upper()` called without null check.

## File
- `services/compliance/app/routes.py` — lines 224-270

## Action
- Add type validation (reject null values)
- Validate cte_type against allowed enum
- Guard `.upper()` with existence check
""",
    },
    {
        "title": "[P1][backend] API key returned in plaintext on creation",
        "labels": ["P1", "security", "backend"],
        "body": """## Problem
`create_api_key()` endpoint returns the raw API key in response body. No audit trail or notification on key creation.

## File
- `services/admin/app/routes.py` — lines 276-285

## Action
- Show key only once (never in subsequent list operations)
- Add audit log entry for key creation
- Consider returning the key only in the response header
""",
    },
    {
        "title": "[P1][backend] SSRF risk in ingestion URL validation",
        "labels": ["P1", "security", "backend"],
        "body": """## Problem
`IngestRequest.url` uses Pydantic `HttpUrl` which validates format but doesn't block internal IPs (localhost, 10.x, 172.x, 192.168.x). Allows server-side request forgery.

## File
- `services/ingestion/app/models.py` — lines 14, 50

## Action
- Add URL allowlist or blocklist validator
- Block private IP ranges, localhost, and metadata endpoints
""",
    },
    {
        "title": "[P1][backend] NLP query plan lacks exhaustive routing — silent empty results",
        "labels": ["P1", "backend"],
        "body": """## Problem
`_execute_query_plan()` routes on `plan.intent` but has no default case. New intents added to QueryPlan without updating this function silently return empty results.

## File
- `services/nlp/app/routes.py` — lines 143-233

## Action
- Add exhaustive match with explicit error for unknown intents
- Log unhandled intents as warnings
""",
    },
    {
        "title": "[P1][backend] Graph query returns empty result on error — indistinguishable from no data",
        "labels": ["P1", "backend"],
        "body": """## Problem
Exception handler returns `{"count": 0, "items": []}` for any Neo4j error. Clients can't distinguish "no results" from "database failure."

## File
- `services/graph/app/routes.py` — lines 113-117

## Action
- Return 500 with error details on DB failure
- Reserve empty results for successful queries with no matches
""",
    },
    {
        "title": "[P1][marketing] No cookie consent banner — GDPR/CCPA risk",
        "labels": ["P1", "legal", "marketing", "frontend"],
        "body": """## Problem
Site loads Vercel Analytics but has no cookie consent banner. Privacy policy mentions cookies but no functional consent mechanism exists. Required by GDPR and CCPA.

## Files
- `frontend/src/app/layout.tsx` — lines 10, 96-97
- `frontend/src/app/privacy/page.tsx`

## Action
1. Add cookie consent banner component to root layout
2. Gate non-essential analytics behind consent
3. Store consent preference
""",
    },
    {
        "title": "[P1][marketing] Missing Data Processing Agreement (DPA) for enterprise customers",
        "labels": ["P1", "legal", "marketing"],
        "body": """## Problem
Privacy policy exists but no DPA is linked. Required for GDPR compliance when processing customer data in B2B context. Enterprise food safety customers will ask for this.

## Action
- Draft DPA (or use a standard template)
- Link from privacy policy and pricing pages
""",
    },
    {
        "title": "[P1][marketing] Competitor pricing data outdated (Jan 2026)",
        "labels": ["P1", "marketing"],
        "body": """## Problem
Pricing page comment states competitor data is from January 2026 (3 months old). Competitor features/pricing may have changed.

## File
- `frontend/src/app/pricing/page.tsx` — line 333

## Action
- Refresh competitor data quarterly
- Add last-updated date visible to team (not users)
""",
    },
    {
        "title": "[P1][marketing] Evidence metrics on landing page lack sourcing",
        "labels": ["P1", "marketing", "frontend"],
        "body": """## Problem
Landing page claims bold metrics (48hr, 100%, 24hr, EPCIS 2.0) with no sources or methodology. Could be perceived as unsubstantiated by prospects.

## File
- `frontend/src/app/page.tsx` — evidence section

## Action
- Add footnotes or links to verification
- Or rephrase as "designed to" / "capable of" rather than absolute claims
""",
    },
    {
        "title": "[P1][infra] No centralized logging — logs only in container stdout",
        "labels": ["P1", "infra"],
        "body": """## Problem
No centralized logging (ELK, Datadog, etc.) configured. Logs are only in container stdout. Debugging production issues requires SSH/container access.

## File
- `docker-compose.yml` — line 14

## Action
- Add log aggregation service (Railway logs may suffice for now, but add structured logging)
- Configure JSON log format for all services
""",
    },
    {
        "title": "[P1][infra] No caching headers for static assets",
        "labels": ["P1", "infra", "frontend"],
        "body": """## Problem
Next.js config includes security headers but no Cache-Control directives for static assets or API responses.

## File
- `frontend/next.config.js` — lines 40-68

## Action
- Add immutable caching for hashed static assets
- Add short TTL for API responses where appropriate
""",
    },
    {
        "title": "[P1][infra] Image optimization disabled in static deploy mode",
        "labels": ["P1", "infra", "frontend"],
        "body": """## Problem
`images: { unoptimized: isStatic }` disables Next.js image optimization in static export. Leads to large unoptimized images for static deployments.

## File
- `frontend/next.config.js` — line 38

## Action
- Use a build-time image optimization plugin (sharp, next-optimized-images)
- Or ensure Vercel deployment uses non-static mode
""",
    },
    # ===================== P2 — POLISH / IMPROVEMENTS =====================
    {
        "title": "[P2][onboarding] Add progress indicator across onboarding steps",
        "labels": ["P2", "ux", "onboarding", "frontend"],
        "body": """## Problem
Onboarding has 3 steps (welcome → facility → ftl-check) but no visual progress bar. Users can't see where they are or how many steps remain.

## Files
- `frontend/src/app/onboarding/setup/welcome/page.tsx`
- `frontend/src/app/onboarding/setup/facility/page.tsx`
- `frontend/src/app/onboarding/setup/ftl-check/page.tsx`

## Action
- Add a step indicator component (e.g., "Step 1 of 3")
- Show across all onboarding pages
""",
    },
    {
        "title": "[P2][frontend] Hardcoded reference data in components (plans, states, roles)",
        "labels": ["P2", "tech-debt", "frontend"],
        "body": """## Problem
Multiple components hardcode reference data that should be configurable:
- Plan labels in signup page
- US states in facility form
- Supply chain roles in facility form
- Compliance status options in welcome page

## Files
- `frontend/src/app/signup/page.tsx` — lines 14-20
- `frontend/src/app/onboarding/setup/facility/page.tsx` — lines 21-34
- `frontend/src/app/onboarding/setup/welcome/page.tsx` — lines 19-40

## Action
- Move to shared constants file or fetch from backend
""",
    },
    {
        "title": "[P2][frontend] Remove console.log statements from production code",
        "labels": ["P2", "tech-debt", "frontend"],
        "body": """## Problem
Multiple files contain console.log, console.warn, and console.info statements:
- Developer portal codegen page (10+ instances)
- Playground page (8+ instances)
- Middleware JWT debugging

## Action
- Remove or wrap in `process.env.NODE_ENV === 'development'` guards
- Use structured logging (Sentry breadcrumbs) instead of console
""",
    },
    {
        "title": "[P2][backend] Health check leaks connection string details on error",
        "labels": ["P2", "security", "backend"],
        "body": """## Problem
Admin health check catches PostgreSQL exceptions but returns error string directly without sanitization. Could leak connection string details.

## File
- `services/admin/app/routes.py` — lines 154-227

## Action
- Sanitize error messages before returning
- Return generic "database unavailable" to clients, log full error server-side
""",
    },
    {
        "title": "[P2][backend] Internal secret exposed in forwarded headers",
        "labels": ["P2", "security", "backend"],
        "body": """## Problem
NLP service forwards `X-RegEngine-Internal-Secret` header to graph service. Could be logged by proxies or exposed in error responses.

## File
- `services/nlp/app/routes.py` — lines 256-258

## Action
- Use mutual TLS or service mesh auth instead of header-based secrets
- At minimum, ensure proxies strip this header from logs
""",
    },
    {
        "title": "[P2][backend] Graph query LIMIT 100 hardcoded — no pagination",
        "labels": ["P2", "backend"],
        "body": """## Problem
Cypher query in graph service has hardcoded `LIMIT 100`. No cursor-based pagination. Could return massive datasets or silently truncate results.

## File
- `services/graph/app/routes.py` — line 96

## Action
- Add pagination parameters (offset/limit or cursor)
- Return total count alongside results
""",
    },
    {
        "title": "[P2][marketing] Pricing page — unclear founding partner terms and no free trial",
        "labels": ["P2", "marketing"],
        "body": """## Problem
- 50% founding partner discount has no visible terms (permanent? time-limited? which tiers?)
- No free trial or money-back guarantee mentioned for $999-$1499 tiers
- Fallback pricing uses unclear abbreviations ("GA")
- No payment method visibility (Stripe, wire, etc.)

## File
- `frontend/src/app/pricing/page.tsx`

## Action
- Clarify discount terms
- Add free trial or guarantee language
- Show accepted payment methods
""",
    },
    {
        "title": "[P2][marketing] No conversion tracking or A/B testing infrastructure",
        "labels": ["P2", "marketing", "frontend"],
        "body": """## Problem
- Vercel Analytics loaded but no custom event tracking for CTAs, sign-ups, or form submissions
- No Google Analytics 4, Facebook Pixel, or LinkedIn Insight Tag
- No A/B testing framework
- No exit-intent or retargeting mechanism

## Files
- `frontend/src/app/layout.tsx` — lines 10, 96-97
- `frontend/src/app/page.tsx`

## Action
1. Add custom event tracking for key conversion points
2. Add GA4 or equivalent
3. Consider PostHog or similar for A/B testing
""",
    },
    {
        "title": "[P2][marketing] Landing page copy — weak CTAs, missing case studies, unverified FSMA date",
        "labels": ["P2", "marketing", "frontend"],
        "body": """## Problem
- Feature descriptions use generic language ("Transform", "Verify", "Scale") without specifics
- No case studies or customer success stories — just "5+ Founding Partners" with no names/logos
- TODO comment: "Verify FSMA 204 enforcement date"
- Missing email capture above the fold

## File
- `frontend/src/app/page.tsx`

## Action
- Add specific metrics and customer proof points
- Verify FSMA 204 date and remove TODO
- Add email newsletter signup in hero section
""",
    },
    {
        "title": "[P2][seo] Missing structured data, manifest.json, and hreflang tags",
        "labels": ["P2", "seo", "frontend"],
        "body": """## Problem
- Only Organization and WebSite schema implemented — missing BreadcrumbList, Product, Offer schemas
- No PWA manifest.json
- No hreflang tags for internationalization
- Robots.txt may conflict with sitemap tool page priorities

## Files
- `frontend/src/app/layout.tsx`
- `frontend/src/app/robots.ts`
- `frontend/src/app/sitemap.ts`

## Action
- Add structured data for products/tools
- Create manifest.json
- Verify robots.txt doesn't block sitemap URLs
""",
    },
    {
        "title": "[P2][infra] Pin critical dependencies to exact versions",
        "labels": ["P2", "infra", "frontend"],
        "body": """## Problem
`package.json` uses `^` (caret) ranges for critical deps like Next.js, Sentry, and Supabase. Minor updates could introduce breaking changes.

## File
- `frontend/package.json`

## Action
- Pin Next.js, Sentry, and Supabase to exact versions
- Use Dependabot or Renovate for controlled updates
""",
    },
    {
        "title": "[P2][infra] Redis has no memory limit — unbounded growth risk",
        "labels": ["P2", "infra"],
        "body": """## Problem
Redis configured with AOF persistence but no `maxmemory` or eviction policy. Could consume unbounded memory.

## File
- `docker-compose.yml` — lines 398-410

## Action
- Set `maxmemory` and `maxmemory-policy` (e.g., `allkeys-lru`)
""",
    },
    {
        "title": "[P2][marketing] Verify all 12 tool pages in sitemap have working implementations",
        "labels": ["P2", "marketing", "frontend"],
        "body": """## Problem
Sitemap lists 12 tools (ftl-checker, cte-mapper, kde-checker, etc.) with 0.7 priority. Unknown whether all have functional implementations or are placeholder pages.

## File
- `frontend/src/app/sitemap.ts` — lines 22-39

## Action
- Audit each tool page for working content
- Remove or noindex any placeholder pages
""",
    },
]

print(f"\nCreating {len(ISSUES)} issues on {REPO}...\n")

created = []
for i, issue in enumerate(ISSUES, 1):
    try:
        result = repo.create_issue(
            title=issue["title"],
            body=issue["body"],
            labels=issue["labels"],
        )
        print(f"  [{i}/{len(ISSUES)}] #{result.number} — {issue['title'][:60]}...")
        created.append(result.number)
        time.sleep(1)  # rate limit courtesy
    except Exception as e:
        print(f"  [{i}/{len(ISSUES)}] FAILED — {e}")

print(f"\nDone. Created {len(created)}/{len(ISSUES)} issues.")
print(f"View at: https://github.com/{REPO}/issues")
