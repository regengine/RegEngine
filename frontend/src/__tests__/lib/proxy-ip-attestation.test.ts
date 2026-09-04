import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import {
    attestPrivilegedProxyClientIp,
    PROXY_CLIENT_IP_HEADER,
    PROXY_IP_SIGNATURE_HEADER,
    PROXY_IP_TIMESTAMP_HEADER,
} from '@/lib/proxy-ip-attestation';

const HMAC_KEY = 'test-proxy-ip-hmac-key-material-32-bytes'; // pragma: allowlist secret
const NOW_SECONDS = 1_786_000_000;

function makeRequest(
    headers: Record<string, string> = {},
    method = 'POST',
): NextRequest {
    return new NextRequest('https://regengine.co/api/admin/v1/admin/keys', {
        method,
        headers,
    });
}

describe('privileged proxy client-IP attestation', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(NOW_SECONDS * 1000);
        vi.stubEnv('VERCEL', '1');
        vi.stubEnv('VERCEL_ENV', 'production');
        vi.stubEnv('REGENGINE_PROXY_IP_HMAC_KEY', HMAC_KEY);
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllEnvs();
    });

    it('replaces spoofable forwarding metadata with a signed canonical platform IP', () => {
        const outgoing = new Headers({
            'x-forwarded-for': '192.0.2.10',
            'x-real-ip': '192.0.2.11',
            [PROXY_CLIENT_IP_HEADER]: '192.0.2.12',
            [PROXY_IP_TIMESTAMP_HEADER]: '1',
            [PROXY_IP_SIGNATURE_HEADER]: 'v1=attacker',
        });
        const request = makeRequest({
            'x-vercel-forwarded-for': '2001:0db8:0:0:0:0:0:1',
            'x-request-id': 'request-123',
        });

        const error = attestPrivilegedProxyClientIp(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.has('x-forwarded-for')).toBe(false);
        expect(outgoing.has('x-real-ip')).toBe(false);
        expect(outgoing.get(PROXY_CLIENT_IP_HEADER)).toBe('2001:db8::1');
        expect(outgoing.get(PROXY_IP_TIMESTAMP_HEADER)).toBe(String(NOW_SECONDS));
        expect(outgoing.get('x-request-id')).toBe('request-123');
        expect(outgoing.get(PROXY_IP_SIGNATURE_HEADER)).toBe(
            'v1=1Y7_BGRt1lVOWOqB8hw-L9J4VkdJ2jtL_z3r9aWoNIY', // pragma: allowlist secret
        );
    });

    it('uses the shared all-hex wire form for IPv4-mapped IPv6', () => {
        const outgoing = new Headers();
        const request = makeRequest({
            'x-vercel-forwarded-for': '::ffff:192.0.2.128',
            'x-request-id': 'mapped-request',
        });

        const error = attestPrivilegedProxyClientIp(outgoing, request);

        expect(error).toBeNull();
        expect(outgoing.get(PROXY_CLIENT_IP_HEADER)).toBe('::ffff:c000:280');
        expect(outgoing.get(PROXY_IP_SIGNATURE_HEADER)).toBe(
            'v1=qVJMaVaSaoPwYjonRlfFP8QZzhHkFWHdRj-Gxq6BNnA', // pragma: allowlist secret
        );
    });

    it.each([
        ['missing platform IP', undefined],
        ['an IP chain', '198.51.100.10, 198.51.100.11'],
        ['a malformed IP', 'not-an-ip'],
    ])('fails closed on Vercel for %s', (_label, platformIp) => {
        const outgoing = new Headers({
            [PROXY_CLIENT_IP_HEADER]: '192.0.2.12',
            [PROXY_IP_SIGNATURE_HEADER]: 'v1=attacker',
        });
        const request = makeRequest(platformIp ? { 'x-vercel-forwarded-for': platformIp } : {});

        const error = attestPrivilegedProxyClientIp(outgoing, request);

        expect(error?.status).toBe(503);
        expect(outgoing.has(PROXY_CLIENT_IP_HEADER)).toBe(false);
        expect(outgoing.has(PROXY_IP_TIMESTAMP_HEADER)).toBe(false);
        expect(outgoing.has(PROXY_IP_SIGNATURE_HEADER)).toBe(false);
    });

    it.each([
        ['missing', undefined],
        ['short', 'too-short'],
    ])('fails closed on Vercel when the HMAC key is %s', (_label, key) => {
        if (key === undefined) {
            vi.stubEnv('REGENGINE_PROXY_IP_HMAC_KEY', '');
        } else {
            vi.stubEnv('REGENGINE_PROXY_IP_HMAC_KEY', key);
        }
        const outgoing = new Headers();
        const request = makeRequest({ 'x-vercel-forwarded-for': '198.51.100.20' });

        const error = attestPrivilegedProxyClientIp(outgoing, request);

        expect(error?.status).toBe(503);
        expect(outgoing.has(PROXY_CLIENT_IP_HEADER)).toBe(false);
    });

    it('preserves local development while stripping caller-controlled IP headers', () => {
        vi.stubEnv('VERCEL', '');
        vi.stubEnv('VERCEL_ENV', '');
        vi.stubEnv('VERCEL_URL', '');
        vi.stubEnv('REGENGINE_PROXY_IP_HMAC_KEY', '');
        const outgoing = new Headers({
            'x-forwarded-for': '192.0.2.10',
            'x-real-ip': '192.0.2.11',
            [PROXY_CLIENT_IP_HEADER]: '192.0.2.12',
            [PROXY_IP_TIMESTAMP_HEADER]: '1',
            [PROXY_IP_SIGNATURE_HEADER]: 'v1=attacker',
        });

        const error = attestPrivilegedProxyClientIp(outgoing, makeRequest());

        expect(error).toBeNull();
        expect(outgoing.has('x-forwarded-for')).toBe(false);
        expect(outgoing.has('x-real-ip')).toBe(false);
        expect(outgoing.has(PROXY_CLIENT_IP_HEADER)).toBe(false);
        expect(outgoing.has(PROXY_IP_TIMESTAMP_HEADER)).toBe(false);
        expect(outgoing.has(PROXY_IP_SIGNATURE_HEADER)).toBe(false);
    });
});
