/**
 * Tests for safeNextPath — the `next` query-param validator used by
 * relative-redirect call sites.
 *
 * Closes RE-FE-AUDIT-002 / OQ-2 (next-param redirect hygiene).
 *
 * The control-character cases pin a live bypass: the previous validator
 * accepted `/<TAB>/evil.com`, `/<LF>/evil.com` and `/<CR>/evil.com`. The WHATWG
 * URL parser deletes tab, LF and CR wherever they appear, so a browser read
 * each of them as `//evil.com` and navigated to another origin.
 */
import { describe, it, expect } from 'vitest';
import { safeNextPath } from '@/lib/safe-redirect';

const FALLBACK = '/dashboard';
const ORIGIN = 'https://regengine.co';
const LOGIN_DENY = ['/login', '/auth/verify'] as const;

describe('safeNextPath', () => {
    describe('accepts clean same-app paths', () => {
        it.each([
            '/dashboard',
            '/foo/bar',
            '/foo/bar?x=y&z=1',
            '/foo#anchor',
            '/developer/portal',
            '/developer/portal/keys',
            '/x?a=b#c',
            '/'.padEnd(256, 'a'), // exactly 256 chars — boundary
        ])('returns input for %s', (input) => {
            expect(safeNextPath(input, FALLBACK)).toBe(input);
        });

        it('returns the input unchanged (no trimming, no normalisation)', () => {
            const input = '/developer/portal/keys?tab=a%20b#top';
            expect(safeNextPath(input, FALLBACK)).toBe(input);
        });
    });

    describe('rejects empty / nullish inputs', () => {
        it('returns fallback for null', () => {
            expect(safeNextPath(null, FALLBACK)).toBe(FALLBACK);
        });
        it('returns fallback for undefined', () => {
            expect(safeNextPath(undefined, FALLBACK)).toBe(FALLBACK);
        });
        it('returns fallback for empty string', () => {
            expect(safeNextPath('', FALLBACK)).toBe(FALLBACK);
        });
    });

    describe('rejects open-redirect bypass attempts', () => {
        it.each([
            ['protocol-relative //evil.com', '//evil.com'],
            ['protocol-relative with path', '//evil.com/path'],
            ['absolute https URL', 'https://evil.com'],
            ['absolute http URL', 'http://evil.com'],
            ['javascript: scheme', 'javascript:alert(1)'],
            ['data: scheme', 'data:text/html,<script>alert(1)</script>'],
            ['backslash double', '\\\\evil.com'],
            ['embedded backslash', '/foo\\bar'],
            ['leading backslash host', '/\\evil.com'],
            ['relative path no leading slash', 'relative-path'],
            ['leading dot-dot', '../etc/passwd'],
            ['TAB between slashes', '/\t/evil.com'],
            ['LF between slashes', '/\n/evil.com'],
            ['CR between slashes', '/\r/evil.com'],
            ['leading space before //', ' //evil.com'],
            ['trailing space', '/dashboard '],
            ['NUL byte', '/dash\u0000board'],
            ['DEL byte', '/dash\u007fboard'],
            ['absolute URL smuggled in a query', '/x?u=https://evil.com'],
        ])('returns fallback for %s', (_label, input) => {
            expect(safeNextPath(input, FALLBACK)).toBe(FALLBACK);
        });
    });

    describe('rejects every control character at every position', () => {
        // 0x00-0x20 (C0 controls and space) and 0x7f (DEL), inserted at every
        // index of '/x/y' including before the leading slash and at the end.
        const base = '/x/y';
        const codes = [...Array.from({ length: 0x21 }, (_, i) => i), 0x7f];

        it('covers 34 characters x 5 positions', () => {
            expect(codes).toHaveLength(34);
            expect(base.length + 1).toBe(5);
        });

        it.each(codes)('char code %i is rejected at all positions', (code) => {
            const ch = String.fromCharCode(code);
            for (let pos = 0; pos <= base.length; pos++) {
                const candidate = base.slice(0, pos) + ch + base.slice(pos);
                const result = safeNextPath(candidate, FALLBACK);
                // Contract: the fallback, or at worst a result that still
                // resolves to our own origin. The validator is stricter than
                // that contract and returns the fallback every time.
                expect(result).toBe(FALLBACK);
                expect(new URL(result, ORIGIN).origin).toBe(ORIGIN);
            }
        });
    });

    describe('never yields a cross-origin URL', () => {
        it.each([
            '//evil.com',
            '/\t/evil.com',
            '/\n/evil.com',
            '/\r/evil.com',
            '/\\evil.com',
            ' //evil.com',
            'https://evil.com',
            'javascript:alert(1)',
            '/.//evil.com',
            '/%2F/evil.com',
            '/%09/evil.com',
            '/a/../../evil.com',
        ])('result for %j resolves to our origin', (input) => {
            const result = safeNextPath(input, FALLBACK);
            expect(new URL(result, ORIGIN).origin).toBe(ORIGIN);
        });
    });

    describe('denyPrefixes', () => {
        it.each([
            '/login',
            '/login?next=/dashboard',
            '/login/',
            '/auth/verify',
            '/auth/verify?next=%2Fdashboard',
        ])('returns fallback for %s when it is denied', (input) => {
            expect(safeNextPath(input, FALLBACK, LOGIN_DENY)).toBe(FALLBACK);
        });

        it('still accepts paths that do not start with a denied prefix', () => {
            expect(safeNextPath('/developer/portal', FALLBACK, LOGIN_DENY)).toBe('/developer/portal');
            expect(safeNextPath('/auth/sso/mock', FALLBACK, LOGIN_DENY)).toBe('/auth/sso/mock');
        });

        it('does not deny anything by default', () => {
            expect(safeNextPath('/login', FALLBACK)).toBe('/login');
        });

        it('still applies every other rule when a deny list is given', () => {
            expect(safeNextPath('//evil.com', FALLBACK, LOGIN_DENY)).toBe(FALLBACK);
            expect(safeNextPath('/\t/evil.com', FALLBACK, LOGIN_DENY)).toBe(FALLBACK);
        });
    });

    describe('length cap (defense in depth)', () => {
        it('returns fallback for a 257-char path', () => {
            const tooLong = '/' + 'a'.repeat(256);
            expect(tooLong.length).toBe(257);
            expect(safeNextPath(tooLong, FALLBACK)).toBe(FALLBACK);
        });
    });
});
