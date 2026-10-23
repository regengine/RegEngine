import { describe, expect, it } from 'vitest';

const nextConfig = require('../../../next.config.js');

type Redirect = { source: string; destination: string; permanent: boolean };

// SEL-412: guessed trace URLs and the old team path must land on real pages,
// not 404.
describe('navigation redirects', () => {
    it.each([
        ['/dashboard/traceability', '/trace'],
        ['/dashboard/lot-trace', '/trace'],
        ['/dashboard/trace', '/trace'],
        ['/settings/users', '/dashboard/settings/users'],
    ])('redirects %s to %s', async (source, destination) => {
        const redirects: Redirect[] = await nextConfig.redirects();
        const match = redirects.find((r) => r.source === source);
        expect(match).toEqual({ source, destination, permanent: true });
    });

    it('keeps the other /settings sub-pages unredirected', async () => {
        const redirects: Redirect[] = await nextConfig.redirects();
        const sources = redirects.map((r) => r.source);
        expect(sources).not.toContain('/settings/:path*');
        expect(sources).not.toContain('/settings/profile');
        expect(sources).not.toContain('/settings/security');
    });
});
