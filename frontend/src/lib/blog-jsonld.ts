import { BLOG_POST_PUBLISHED, BLOG_POST_TITLES, type BlogPostSlug } from './blog-posts';

/**
 * BlogPosting structured data for a post, rendered through the shared
 * <JSONLD> component so it picks up the CSP nonce. Title, date, and URL come
 * from the shared blog module — the same source the index, sitemap, and
 * social cards use — so a post cannot ship schema that disagrees with them.
 */
export function blogPostingJsonLd(slug: BlogPostSlug, description: string): Record<string, unknown> {
    return {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: BLOG_POST_TITLES[slug],
        description,
        datePublished: BLOG_POST_PUBLISHED[slug],
        url: `https://regengine.co/blog/${slug}`,
        mainEntityOfPage: `https://regengine.co/blog/${slug}`,
        image: `https://regengine.co/blog/${slug}/opengraph-image`,
        author: { '@type': 'Organization', name: 'RegEngine', url: 'https://regengine.co' },
        publisher: {
            '@type': 'Organization',
            name: 'RegEngine',
            url: 'https://regengine.co',
            logo: { '@type': 'ImageObject', url: 'https://regengine.co/icon.png' },
        },
    };
}
