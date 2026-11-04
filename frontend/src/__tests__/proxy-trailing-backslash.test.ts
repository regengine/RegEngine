/**
 * Paths ending in backslashes (`/pricing%5C`, `/docs%5C%5C%5C`) used to reach
 * the Next.js page lookup, which threw MODULE_NOT_FOUND and answered 500.
 * Vercel runtime errors showed dozens of these across marketing and tool
 * pages. The proxy now sends them to the clean path with a 308.
 */

import { describe, it, expect } from 'vitest';
import { NextRequest } from 'next/server';
import { proxy, stripTrailingBackslashes } from '@/proxy';

describe('stripTrailingBackslashes', () => {
    it.each([
        ['/pricing%5C', '/pricing'],
        ['/pricing%5C%5C%5C', '/pricing'],
        ['/tools/ftl-checker%5c', '/tools/ftl-checker'],
        ['/docs\\', '/docs'],
        ['/%5C', '/'],
    ])('%s -> %s', (input, expected) => {
        expect(stripTrailingBackslashes(input)).toBe(expected);
    });

    it.each(['/pricing', '/', '/docs/a%5Cb', '/tools/'])('leaves %s alone', (input) => {
        expect(stripTrailingBackslashes(input)).toBeNull();
    });

    it('strips a mixed run of raw and encoded backslashes', () => {
        expect(stripTrailingBackslashes('/docs%5C\\%5c')).toBe('/docs');
    });

    it('stays linear on a long run of %5C that does not reach the end', () => {
        // The regex this replaced took about 260 ms on a path this long. The
        // bound leaves room for a paused test process and still fails on it.
        const path = `/${'%5C'.repeat(50_000)}x`;
        const start = performance.now();

        expect(stripTrailingBackslashes(path)).toBeNull();
        expect(performance.now() - start).toBeLessThan(150);
    });
});

describe('proxy trailing-backslash redirect', () => {
    it('does not redirect an uppercase /API/ path, which still carries a lot code', async () => {
        const res = await proxy(
            new NextRequest(new URL('http://localhost/API/v1/fda/trace/LOT%5C')),
        );

        expect(res.status).not.toBe(308);
        expect(res.headers.get('location')).toBeNull();
    });

    it('308-redirects a GET to the clean path and keeps the query string', async () => {
        const res = await proxy(
            new NextRequest(new URL('http://localhost/pricing%5C%5C%5C?plan=pro')),
        );

        expect(res.status).toBe(308);
        expect(res.headers.get('location')).toBe('http://localhost/pricing?plan=pro');
        expect(res.headers.get('content-security-policy')).toBeTruthy();
    });

    it('redirects HEAD as well', async () => {
        const res = await proxy(
            new NextRequest(new URL('http://localhost/docs%5C'), { method: 'HEAD' }),
        );

        expect(res.status).toBe(308);
        expect(res.headers.get('location')).toBe('http://localhost/docs');
    });

    it('does not redirect writes', async () => {
        const res = await proxy(
            new NextRequest(new URL('http://localhost/contact%5C'), { method: 'POST' }),
        );

        expect(res.headers.get('location')).toBeNull();
    });

    it('stays on the same host when the stripped path starts with //', async () => {
        const res = await proxy(
            new NextRequest(new URL('http://localhost//evil.example%5C')),
        );

        expect(res.status).toBe(308);
        expect(new URL(res.headers.get('location')!).host).toBe('localhost');
    });

    it.each([
        '/api/v1/fda/trace/LOT%5C',
        '/api/v1/fda/trace/LOT%5C%5C',
        '/01/00012345678905/10/LOT%5C/21/SERIAL%5C',
    ])('keeps identifiers exact: does not redirect %s', async (pathname) => {
        const res = await proxy(new NextRequest(new URL(`http://localhost${pathname}`)));

        expect(res.status).not.toBe(308);
        expect(res.headers.get('location')).toBeNull();
    });

    it('does not touch normal paths', async () => {
        const res = await proxy(new NextRequest(new URL('http://localhost/docs')));

        expect(res.status).not.toBe(308);
    });
});
