import type { MetadataRoute } from 'next';

/**
 * XML sitemap (#571).
 *
 * Changes from audit:
 * - Removed /about — page redirects to /contact (duplicate, causes 301 chain).
 * - Removed duplicate /developer/register — was listed in both marketingPages
 *   and resourcePages; kept the higher-priority marketing entry only.
 * - All 12 tool pages verified functional (53–426 lines each); none are
 *   placeholder-only so no noindex tags are needed.
 */
export default function sitemap(): MetadataRoute.Sitemap {
    const baseUrl = 'https://www.regengine.co';
    const now = new Date().toISOString();

    // Core marketing pages
    const marketingPages = [
        { url: `${baseUrl}/`, changeFrequency: 'weekly' as const, priority: 1.0 },
        { url: `${baseUrl}/pricing`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/security`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/developer/register`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/alpha`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/why-regengine`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/contact`, changeFrequency: 'yearly' as const, priority: 0.5 },
        { url: `${baseUrl}/privacy`, changeFrequency: 'yearly' as const, priority: 0.3 },
        { url: `${baseUrl}/terms`, changeFrequency: 'yearly' as const, priority: 0.3 },
    ];

    // Free tools (high-value PLG pages) — all verified functional Apr 2026
    const toolPages = [
        'ftl-checker',
        'cte-mapper',
        'kde-checker',
        'knowledge-graph',
        'recall-readiness',
        'roi-calculator',
        'tlc-validator',
        'drill-simulator',
        'sop-generator',
        'data-import',
        'readiness-assessment',
        'fsma-unified',
    ].map((tool) => ({
        url: `${baseUrl}/tools/${tool}`,
        changeFrequency: 'monthly' as const,
        priority: 0.7,
    }));

    // Content pages (high SEO value)
    const contentPages = [
        { url: `${baseUrl}/fsma-204`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/walkthrough`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/developers`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/blog`, changeFrequency: 'weekly' as const, priority: 0.8 },
        { url: `${baseUrl}/blog/24-hour-rule`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/blog/fsma-204-traceability-lot-codes`, changeFrequency: 'monthly' as const, priority: 0.8 },
    ];

    // Resource pages
    const resourcePages = [
        { url: `${baseUrl}/tools`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/retailer-readiness`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/docs`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/docs/fsma-204`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/verticals/food-safety`, changeFrequency: 'monthly' as const, priority: 0.6 },
    ];

    return [...marketingPages, ...contentPages, ...toolPages, ...resourcePages].map((page) => ({
        ...page,
        lastModified: now,
    }));
}
