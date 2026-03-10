import type { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
    const baseUrl = 'https://www.regengine.co';
    const now = new Date().toISOString();

    // Core marketing pages
    const marketingPages = [
        { url: `${baseUrl}/`, changeFrequency: 'weekly' as const, priority: 1.0 },
        { url: `${baseUrl}/product`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/pricing`, changeFrequency: 'monthly' as const, priority: 0.9 },
        { url: `${baseUrl}/security`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/about`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/developers`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/alpha`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/contact`, changeFrequency: 'yearly' as const, priority: 0.5 },
        { url: `${baseUrl}/privacy`, changeFrequency: 'yearly' as const, priority: 0.3 },
        { url: `${baseUrl}/terms`, changeFrequency: 'yearly' as const, priority: 0.3 },
    ];

    // Free tools (high-value PLG pages)
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
        'bias-checker',
        'notice-validator',
        'obligation-scanner',
        'fsma-unified',
    ].map((tool) => ({
        url: `${baseUrl}/tools/${tool}`,
        changeFrequency: 'monthly' as const,
        priority: 0.7,
    }));

    // Resource pages
    const resourcePages = [
        { url: `${baseUrl}/tools`, changeFrequency: 'monthly' as const, priority: 0.8 },
        { url: `${baseUrl}/retailer-readiness`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/resources`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/resources/guides`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/resources/whitepapers`, changeFrequency: 'monthly' as const, priority: 0.5 },
        { url: `${baseUrl}/docs`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/docs/api`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/docs/quickstart`, changeFrequency: 'monthly' as const, priority: 0.7 },
        { url: `${baseUrl}/docs/fsma-204`, changeFrequency: 'monthly' as const, priority: 0.6 },
        { url: `${baseUrl}/verticals/food-safety`, changeFrequency: 'monthly' as const, priority: 0.6 },
    ];

    return [...marketingPages, ...toolPages, ...resourcePages].map((page) => ({
        ...page,
        lastModified: now,
    }));
}
