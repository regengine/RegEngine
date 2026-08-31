import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import sitemap from '@/app/sitemap';
import robots from '@/app/robots';
import { BLOG_POST_SLUGS } from '@/lib/blog-posts';

/**
 * Invariants for what we tell crawlers.
 *
 * Every case here is a defect that actually shipped: a static public/robots.txt
 * shadowing the route handler, four live posts missing from the sitemap,
 * redirect stubs advertised as canonical URLs (one of them a client-side
 * useEffect redirect into a disallowed path), and a duplicated <url> entry.
 * They drifted because nothing asserted any of it.
 */

const APP_DIR = path.join(process.cwd(), 'src', 'app');
const BASE_URL = 'https://regengine.co';

const entries = sitemap();
const paths = entries.map((e) => e.url.replace(BASE_URL, '') || '/');

/** Locate the page module backing a sitemap path, if any. */
function pageFileFor(urlPath: string): string | null {
    const file = path.join(APP_DIR, urlPath === '/' ? '' : urlPath, 'page.tsx');
    return fs.existsSync(file) ? file : null;
}

/** Metadata can live on the page or on a layout in the same segment. */
function segmentSource(urlPath: string): string {
    const dir = path.join(APP_DIR, urlPath === '/' ? '' : urlPath);
    return ['page.tsx', 'layout.tsx']
        .map((f) => path.join(dir, f))
        .filter((f) => fs.existsSync(f))
        .map((f) => fs.readFileSync(f, 'utf8'))
        .join('\n');
}

describe('sitemap', () => {
    it('lists every URL exactly once', () => {
        const duplicated = paths.filter((p, i) => paths.indexOf(p) !== i);
        expect(duplicated).toEqual([]);
    });

    it('lists only URLs backed by a real page', () => {
        expect(paths.filter((p) => pageFileFor(p) === null)).toEqual([]);
    });

    it('lists no redirect stubs — server-side or client-side', () => {
        const redirecting = paths.filter((p) => {
            const file = pageFileFor(p);
            if (!file) return false;
            const src = fs.readFileSync(file, 'utf8');
            return /\bredirect\(/.test(src) || /router\.(replace|push)\(/.test(src);
        });
        expect(redirecting).toEqual([]);
    });

    it('lists every published blog post', () => {
        for (const slug of BLOG_POST_SLUGS) {
            expect(paths).toContain(`/blog/${slug}`);
        }
    });

    it('gives every listed page a social card image', () => {
        // Next derives twitter:* from openGraph and only upgrades the card to
        // summary_large_image when an image is present, so a page with no
        // image is shared as a small card. Segment image files are NOT
        // inherited by child segments — each listed route needs its own.
        const cardless = paths.filter((p) => {
            if (p === '/') return false; // homepage ships the designed static PNG
            const dir = path.join(APP_DIR, p);
            const hasFile = fs.existsSync(path.join(dir, 'opengraph-image.tsx'));
            const declaresImage = /openGraph:[\s\S]*?images:/.test(segmentSource(p));
            return !hasFile && !declaresImage;
        });
        expect(cardless).toEqual([]);
    });

    it('restates url in every openGraph block a listed page declares', () => {
        // A segment's openGraph REPLACES the inherited root block wholesale,
        // so declaring one without `url` silently drops og:url (root's
        // relative './' is lost). All 10 blog pages shipped that way.
        const dropped = paths.filter((p) => {
            const src = segmentSource(p);
            const og = src.match(/openGraph:\s*\{[\s\S]*?\n\s*\},/);
            return og !== null && !/\burl:/.test(og[0]);
        });
        expect(dropped).toEqual([]);
    });

    it('gives every listed page its own openGraph block', () => {
        // Without one, a page inherits the root layout's card and advertises
        // the homepage's title and description as its own.
        const inheriting = paths.filter((p) => p !== '/' && !segmentSource(p).includes('openGraph'));
        expect(inheriting).toEqual([]);
    });
});

describe('robots', () => {
    const rules = robots();
    const rule = Array.isArray(rules.rules) ? rules.rules[0] : rules.rules;
    const disallow = ([] as string[]).concat(rule.disallow ?? []);

    it('is served from the route handler, not a static file that would shadow it', () => {
        // public/* resolves before metadata routes in production, so a static
        // copy silently wins and goes stale.
        expect(fs.existsSync(path.join(process.cwd(), 'public', 'robots.txt'))).toBe(false);
    });

    it('keeps authenticated and transactional surfaces out of the index', () => {
        for (const prefix of ['/api/', '/admin/', '/dashboard/', '/settings/', '/login', '/signup', '/checkout', '/onboarding/']) {
            expect(disallow).toContain(prefix);
        }
    });

    it('does not disallow anything the sitemap advertises', () => {
        const blocked = paths.filter((p) => disallow.some((d) => p.startsWith(d)));
        expect(blocked).toEqual([]);
    });

    it('points at the canonical sitemap', () => {
        expect(rules.sitemap).toBe(`${BASE_URL}/sitemap.xml`);
    });
});
