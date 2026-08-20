/**
 * Canonical list of published blog post slugs.
 *
 * Single source of truth for the blog index (`src/app/blog/page.tsx`) and the
 * XML sitemap (`src/app/sitemap.ts`). Four posts were live but absent from the
 * sitemap because the two lists were maintained by hand; `BlogPostSlug` now
 * makes that drift a type error instead of a silent crawl gap.
 *
 * Add the slug here first, then the index entry.
 */
export const BLOG_POST_SLUGS = [
    'fsma-204-compliance-guide',
    'fsma-204-mid-market-guide',
    'fda-food-traceability-requirements',
    'fsma-204-compliance-checklist-2026',
    'regengine-vs-spreadsheets-traceability',
    'food-traceability-software',
    'fsma-204-cte-kde-guide',
    'fsma-204-traceability-lot-codes',
    '24-hour-rule',
] as const;

export type BlogPostSlug = (typeof BLOG_POST_SLUGS)[number];
