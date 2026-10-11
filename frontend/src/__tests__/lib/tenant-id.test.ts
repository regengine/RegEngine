import { describe, expect, it } from 'vitest';

import { DEFAULT_TENANT_ID, isSafeTenantId } from '@/lib/tenant-context';

describe('isSafeTenantId', () => {
    it('accepts the default system tenant id', () => {
        expect(isSafeTenantId(DEFAULT_TENANT_ID)).toBe(true);
    });

    it('accepts versioned UUIDs and short deployment slugs', () => {
        expect(isSafeTenantId('e88a23d7-1f2e-46f5-9727-a931b5074bdc')).toBe(true);
        expect(isSafeTenantId('tenant-123')).toBe(true);
        expect(isSafeTenantId('a')).toBe(true);
    });

    it('rejects path traversal, absolute URLs and header-splitting input', () => {
        expect(isSafeTenantId('../admin')).toBe(false);
        expect(isSafeTenantId('/api/admin')).toBe(false);
        expect(isSafeTenantId('https://evil.example/t')).toBe(false);
        expect(isSafeTenantId('tenant\r\nX-Injected: 1')).toBe(false);
        expect(isSafeTenantId('tenant id')).toBe(false);
    });

    it('rejects empty, overlong and non-string values', () => {
        expect(isSafeTenantId('')).toBe(false);
        expect(isSafeTenantId('a'.repeat(129))).toBe(false);
        expect(isSafeTenantId(undefined)).toBe(false);
        expect(isSafeTenantId(null)).toBe(false);
        expect(isSafeTenantId(42)).toBe(false);
    });
});
