import { describe, expect, it } from 'vitest';

import { decodeRegEngineClaims, extractRegEngineTenantId } from '@/lib/jwt-claims';

function base64Url(value: string): string {
    return Buffer.from(value, 'utf8')
        .toString('base64')
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
}

function mintToken(payload: Record<string, unknown>): string {
    const header = base64Url(JSON.stringify({ alg: 'none', typ: 'JWT' }));
    const body = base64Url(JSON.stringify(payload));
    return `${header}.${body}.`;
}

const VALID_PAYLOAD = {
    aud: 'regengine-api',
    iss: 'regengine-admin',
    exp: 4102444800,
    tenant_id: 'tenant-123',
    sub: 'user-1',
};

describe('decodeRegEngineClaims', () => {
    it('accepts a token with the expected audience, issuer and a future expiry', () => {
        const claims = decodeRegEngineClaims(mintToken(VALID_PAYLOAD));
        expect(claims).toMatchObject({ tenant_id: 'tenant-123', sub: 'user-1' });
    });

    it('accepts an audience list that contains the API audience', () => {
        const claims = decodeRegEngineClaims(mintToken({ ...VALID_PAYLOAD, aud: ['other', 'regengine-api'] }));
        expect(claims).not.toBeNull();
    });

    it('rejects a token minted for a different audience', () => {
        expect(decodeRegEngineClaims(mintToken({ ...VALID_PAYLOAD, aud: 'someone-else' }))).toBeNull();
        expect(decodeRegEngineClaims(mintToken({ ...VALID_PAYLOAD, aud: ['a', 'b'] }))).toBeNull();
    });

    it('rejects a token from an unexpected issuer', () => {
        expect(decodeRegEngineClaims(mintToken({ ...VALID_PAYLOAD, iss: 'evil-issuer' }))).toBeNull();
    });

    it('rejects an expired token', () => {
        expect(decodeRegEngineClaims(mintToken({ ...VALID_PAYLOAD, exp: 1000 }))).toBeNull();
    });

    it('rejects malformed input instead of throwing', () => {
        expect(decodeRegEngineClaims('not-a-jwt')).toBeNull();
        expect(decodeRegEngineClaims('')).toBeNull();
        expect(decodeRegEngineClaims(`${base64Url('not-json')}.${base64Url('also-not-json')}.`)).toBeNull();
    });
});

describe('extractRegEngineTenantId', () => {
    it('prefers tenant_id over tid', () => {
        expect(extractRegEngineTenantId({ tenant_id: 't-1', tid: 't-2' })).toBe('t-1');
    });

    it('falls back to tid when tenant_id is absent', () => {
        expect(extractRegEngineTenantId({ tid: 't-2' })).toBe('t-2');
    });

    it('returns null for missing, empty or non-string tenant values', () => {
        expect(extractRegEngineTenantId({})).toBeNull();
        expect(extractRegEngineTenantId({ tenant_id: '' })).toBeNull();
        expect(extractRegEngineTenantId({ tenant_id: 42 })).toBeNull();
    });
});
