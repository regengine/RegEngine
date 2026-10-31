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
});

describe('proxy trailing-backslash redirect', () => {
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

    it('does not touch normal paths', async () => {
        const res = await proxy(new NextRequest(new URL('http://localhost/docs')));

        expect(res.status).not.toBe(308);
    });
});
