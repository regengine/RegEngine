import { describe, expect, it } from 'vitest';

import { encodePathSegment } from '@/lib/api-path';

describe('encodePathSegment', () => {
    it('leaves plain IDs unchanged', () => {
        expect(encodePathSegment('tenant-123')).toBe('tenant-123');
        expect(encodePathSegment('11111111-1111-4111-8111-111111111111')).toBe(
            '11111111-1111-4111-8111-111111111111',
        );
    });

    it('encodes characters that would break a request path', () => {
        expect(encodePathSegment('case/01')).toBe('case%2F01');
        expect(encodePathSegment('a b')).toBe('a%20b');
        expect(encodePathSegment('a?b=c&d')).toBe('a%3Fb%3Dc%26d');
        expect(encodePathSegment('a#b')).toBe('a%23b');
        expect(encodePathSegment('100%')).toBe('100%25');
    });

    it('accepts numeric IDs', () => {
        expect(encodePathSegment(42)).toBe('42');
    });
});
