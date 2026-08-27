/**
 * #2886 — structural guard: every GATED_DEV_ROUTES entry must name a real page.
 *
 * isGatedRoute() matches `pathname === route || pathname.startsWith(route + '/')`,
 * so an entry that corresponds to no page under src/app gates nothing and
 * raises no error — the list simply stops protecting what a reader assumes it
 * protects. That is exactly how the playground came to be publicly reachable:
 * the list said '/api-keys' and '/playground' while the pages had moved to
 * /developer/portal/keys and /developer/portal/playground, and the mismatch
 * was invisible because a stale gate entry is silently inert.
 *
 * proxy-csp-nonce.test.ts pins the behavior of the two entries that exist
 * today — it asserts those paths redirect to /login. It cannot catch the
 * failure mode this file exists for: an entry ADDED to the list that matches
 * nothing, which passes every behavioral test while gating nothing. This test
 * checks the list itself against the filesystem, so a gate that protects
 * nothing fails the build instead of failing silently.
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { GATED_DEV_ROUTES } from '@/proxy';

const APP_DIR = path.resolve(__dirname, '../app');
const PAGE_FILES = ['page.tsx', 'page.ts', 'page.jsx', 'page.js'];

/** True when Next.js renders a page for this exact pathname. */
function hasRenderedPage(route: string): boolean {
    const dir = path.join(APP_DIR, route.replace(/^\//, ''));
    return PAGE_FILES.some((file) => existsSync(path.join(dir, file)));
}

describe('#2886 GATED_DEV_ROUTES structural guard', () => {
    it('is not empty', () => {
        // An empty list would pass every per-entry check below while gating
        // nothing at all.
        expect(GATED_DEV_ROUTES.length).toBeGreaterThan(0);
    });

    it('contains only routes that resolve to a page under src/app', () => {
        const inert = GATED_DEV_ROUTES.filter((route) => !hasRenderedPage(route));
        expect(
            inert,
            `GATED_DEV_ROUTES entries that match no page under src/app and so `
            + `gate nothing: ${JSON.stringify(inert)}. Either point the entry at `
            + `the real rendered path or remove it.`,
        ).toEqual([]);
    });

    it('uses absolute paths with no trailing slash', () => {
        // isGatedRoute() appends '/' itself; a stored trailing slash makes both
        // the equality and the startsWith test miss the page.
        for (const route of GATED_DEV_ROUTES) {
            expect(route.startsWith('/')).toBe(true);
            expect(route.endsWith('/')).toBe(false);
        }
    });

    it('still covers the two developer surfaces that make real API calls', () => {
        // Key generation and the playground are the reason the list exists.
        expect(GATED_DEV_ROUTES).toContain('/developer/portal/keys');
        expect(GATED_DEV_ROUTES).toContain('/developer/portal/playground');
    });
});
