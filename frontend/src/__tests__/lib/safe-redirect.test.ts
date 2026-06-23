/**
 * Tests for safeNextPath — the `next` query-param validator used by
 * relative-redirect call sites.
 *
 * Closes RE-FE-AUDIT-002 / OQ-2 (next-param redirect hygiene).
 */
import { describe, it, expect } from 'vitest';
import { safeNextPath } from '@/lib/safe-redirect';

const FALLBACK = '/dashboard';

describe('safeNextPath', () => {
    describe('accepts clean same-app paths', () => {
        it.each([
            '/dashboard',
            '/foo/bar',
            '/foo/bar?x=y&z=1',
            '/foo#anchor',
            '/developer/portal',
            '/'.padEnd(256, 'a'), // exactly 256 chars — boundary
        ])('returns input for %s', (input) => {
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
            ['relative path no leading slash', 'relative-path'],
            ['leading dot-dot', '../etc/passwd'],
        ])('returns fallback for %s', (_label, input) => {
            expect(safeNextPath(input, FALLBACK)).toBe(FALLBACK);
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
