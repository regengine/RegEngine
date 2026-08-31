/**
 * Canonical list of published blog posts.
 *
 * Single source of truth for the blog index (`src/app/blog/page.tsx`) and the
 * XML sitemap (`src/app/sitemap.ts`). Four posts were live but absent from the
 * sitemap because the two lists were maintained by hand; `BlogPostSlug` now
 * makes that drift a type error instead of a silent crawl gap.
 *
 * Add the slug here first, then the index entry.
 */
export const BLOG_POST_TITLES = {
    'fsma-204-compliance-guide': 'FSMA 204 Compliance: The Complete Guide for Food Businesses (2026)',
    'fsma-204-mid-market-guide': 'FSMA 204 for Mid-Market: Compliance Strategies for Growing Food Companies',
    'fda-food-traceability-requirements': 'FDA Food Traceability Requirements: Complete Guide to FSMA 204 Rules',
    'fsma-204-compliance-checklist-2026': 'FSMA 204 Compliance Checklist for 2026: Actionable Steps for July 2028',
    'regengine-vs-spreadsheets-traceability': 'RegEngine vs Spreadsheets: Why Food Companies Outgrow Excel for Traceability',
    'food-traceability-software': 'Food Traceability Software: How to Choose the Right Platform',
    'fsma-204-cte-kde-guide': 'CTEs and KDEs Explained: A Practical Guide to FSMA 204 Data Requirements',
    'fsma-204-traceability-lot-codes': 'FSMA 204 Traceability Lot Codes (TLCs): A Complete Guide',
    '24-hour-rule': 'The FSMA 204 24-Hour Rule Explained',
} as const;

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

// Keys and slugs must agree in both directions: a post added to one list but
// not the other is a typecheck failure, not a missing social card.
const _titlesCoverEverySlug: Record<BlogPostSlug, string> = BLOG_POST_TITLES;
const _slugsCoverEveryTitle: Record<keyof typeof BLOG_POST_TITLES, string> = _titlesCoverEverySlug;
void _slugsCoverEveryTitle;
