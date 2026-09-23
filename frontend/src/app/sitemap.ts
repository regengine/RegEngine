import type { MetadataRoute } from 'next';
import { BLOG_POST_PUBLISHED, BLOG_POST_SLUGS } from '@/lib/blog-posts';
import { EXPERIMENTAL_TOOL_SLUGS, isExperimentalToolEnabled } from '@/lib/experimental-features';
import { isSandboxEnabled } from '@/lib/sandbox-cta';

/**
 * XML sitemap.
 *
 * Includes all public-facing pages: marketing, tools, content, docs, and resources.
 *
 * Only canonical URLs that answer 200 belong here — never a route that
 * redirects, and never the same URL twice. Both cost crawl budget and teach
 * Search Console that the sitemap is unreliable.
 */
export default function sitemap(): MetadataRoute.Sitemap {
    const baseUrl = 'https://regengine.co';

    // Core marketing pages
    const marketingPages = [
        { url: `${baseUrl}/`, changeFrequency: 'weekly' as const, priority: 1.0 },
        { url: `${baseUrl}/pricing`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/security`, changeFrequency: 'monthly' as const, priority: 0.8 },
        // /alpha, /verticals/food-safety and /developer/register are redirect
        // stubs (the last one client-side, into robots-disallowed /signup), so
        // they are deliberately absent: a sitemap entry must resolve to a 200.
        { url: `${baseUrl}/why-regengine`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/about`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/product`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/demo`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/buyer-programs`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/supplier-compliance`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/compare/foodlogiq`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/compare/repositrak`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/compare/tracegains`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/integrations`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/trust`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/contact`, changeFrequency: 'yearly' as const, priority: 0.5 },
        // #2757 — only advertise the sandbox when its (experimental) router is
        // mounted; listing a page that answers "not enabled here" is worse for
        // search than not listing it.
        ...(isSandboxEnabled()
            ? [{ url: `${baseUrl}/sandbox`, changeFrequency: 'monthly' as const, priority: 0.9 }]
            : []),
        { url: `${baseUrl}/privacy`, changeFrequency: 'yearly' as const, priority: 0.3 },
        { url: `${baseUrl}/terms`, changeFrequency: 'yearly' as const, priority: 0.3 },
        { url: `${baseUrl}/dpa`, changeFrequency: 'yearly' as const, priority: 0.3 },
        { url: `${baseUrl}/legal/vulnerability-disclosure`, changeFrequency: 'yearly' as const, priority: 0.3 },
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
        // Added Sep 2026 — built after the April curation, never listed.
        // ask, label-scanner and inflow-lab are experimental and drop out of
        // the list below unless their flags are enabled.
        'records-request-checklist',
        'self-reported-checklist',
        'scan',
        'export',
        'ask',
        'label-scanner',
        'inflow-lab',
    ]
        .filter((tool) => !EXPERIMENTAL_TOOL_SLUGS.has(tool) || isExperimentalToolEnabled(tool))
        .map((tool) => ({
        url: `${baseUrl}/tools/${tool}`,
        changeFrequency: 'monthly' as const,
        priority: 0.7,
    }));

    // Content pages (high SEO value)
    const contentPages = [
        { url: `${baseUrl}/fsma-204`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/walkthrough`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/case-studies`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/developers`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/blog`, changeFrequency: 'weekly' as const, priority: 0.8 },
        // Every published post, from the same list the blog index renders —
        // four posts were live but uncrawled while these were hand-maintained.
        ...BLOG_POST_SLUGS.map((slug) => ({
            url: `${baseUrl}/blog/${slug}`,
            lastModified: BLOG_POST_PUBLISHED[slug],
            changeFrequency: 'monthly' as const,
            priority: 0.8,
        })),
    ];

    // Resource pages
    const resourcePages = [
        { url: `${baseUrl}/tools`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/docs`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/docs/fsma-204`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/docs/quickstart`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/docs/walkthrough`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/docs/api`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/authentication`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/sdks`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/webhooks`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/errors`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/rate-limits`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/changelog`, changeFrequency: 'weekly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs/connectors/inflow-lab`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/trust/architecture`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/trust/retention`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/trust/support`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/proof`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/proof/transformation`, changeFrequency: 'monthly' as const, priority: 0.5 },
    ];

    // No blanket lastModified: stamping every URL "now" on every request
    // teaches crawlers the field is meaningless. Blog entries carry their real
    // publication dates; other pages omit the field, which is valid.
    return [...marketingPages, ...contentPages, ...toolPages, ...resourcePages];
}
