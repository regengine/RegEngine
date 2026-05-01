# Sitewide Design Review - 2026-05-01

## Scope

Reviewed representative public surfaces after the homepage/login refresh:

- `/product`
- `/pricing`
- `/tools`
- `/docs`
- `/docs/api`
- `/developers`
- `/security`
- `/about`
- `/blog`

Desktop viewport: `1440x1100`.
Mobile viewport: `390x1100`.

## Findings

1. Product and tools hero panels stretched to match oversized left-column hero copy, producing large empty right-side panels on desktop.
2. Shared section rhythm was too loose across downstream pages, pushing useful content below the first viewport and making pages feel less complete than the homepage/login surfaces.
3. The first-visit cookie consent banner needed to remain compact so it did not dominate pricing, tools, and documentation pages during QA.
4. The developers page had a centered marketing-only opening, while its technical proof lived too far below the fold; on mobile, the code sample dominated the viewport and clipped visually.
5. API docs mobile needed confirmation after the endpoint-row repair; no horizontal overflow was detected after waiting for render.

## Repairs

- Tightened shared RegEngine section spacing and introduced reusable `re-hero-title` / `re-hero-copy` classes.
- Changed product and tools hero grids to align to content height instead of stretching panels into empty blocks.
- Rebalanced the developers hero into a product-and-proof layout with an integration path panel above the fold.
- Reduced mobile code sample density on the developers page.

## Verification

Screenshots are stored under `frontend/output/playwright/sitewide-design-audit/`.

Automated checks run:

- Rendered route screenshots before and after at desktop and mobile sizes.
- Checked document/body horizontal overflow for the full route sample at `390px` and `1440px`; all sampled routes reported `overflow=0`.

