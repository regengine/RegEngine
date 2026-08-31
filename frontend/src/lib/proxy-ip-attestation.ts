import { createHmac, randomUUID } from 'node:crypto';
import { isIP } from 'node:net';

import { NextRequest, NextResponse } from 'next/server';

export const PROXY_CLIENT_IP_HEADER = 'x-regengine-proxy-client-ip';
export const PROXY_IP_TIMESTAMP_HEADER = 'x-regengine-proxy-timestamp';
export const PROXY_IP_SIGNATURE_HEADER = 'x-regengine-proxy-signature';

const PLATFORM_CLIENT_IP_HEADER = 'x-vercel-forwarded-for';
const PROXY_IP_HMAC_ENV = 'REGENGINE_PROXY_IP_HMAC_KEY';
const MIN_HMAC_KEY_BYTES = 32;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const UNTRUSTED_IP_HEADERS = [
    'forwarded',
    'x-forwarded-for',
    'x-real-ip',
    PLATFORM_CLIENT_IP_HEADER,
    PROXY_CLIENT_IP_HEADER,
    PROXY_IP_TIMESTAMP_HEADER,
    PROXY_IP_SIGNATURE_HEADER,
] as const;

function clearUntrustedIpHeaders(headers: Headers): void {
    for (const name of UNTRUSTED_IP_HEADERS) headers.delete(name);
}

function isVercelRuntime(): boolean {
    return Boolean(process.env.VERCEL || process.env.VERCEL_ENV || process.env.VERCEL_URL);
}

function canonicalIp(value: string | null): string | null {
    if (!value) return null;
    const candidate = value.trim();
    if (!candidate || candidate.includes(',') || candidate.includes('%')) return null;

    const version = isIP(candidate);
    if (version === 4) {
        return candidate.split('.').map((octet) => String(Number(octet))).join('.');
    }
    if (version === 6) {
        try {
            const hostname = new URL(`http://[${candidate}]/`).hostname;
            return hostname.slice(1, -1).toLowerCase();
        } catch {
            return null;
        }
    }
    return null;
}

function unavailable(): NextResponse {
    return NextResponse.json(
        { error: 'Privileged proxy source attribution unavailable' },
        { status: 503 },
    );
}

/**
 * Attach authenticated client-IP metadata to a privileged Vercel BFF request.
 *
 * Raw forwarding and caller-supplied attestation headers are always removed.
 * On Vercel, the platform-derived singular client IP is canonicalized and
 * signed with a dedicated key shared only with the Railway backend. Local
 * development remains usable without Vercel headers or the deployment key.
 */
export function attestPrivilegedProxyClientIp(
    headers: Headers,
    request: NextRequest,
): NextResponse | null {
    clearUntrustedIpHeaders(headers);

    if (!isVercelRuntime()) return null;

    const clientIp = canonicalIp(request.headers.get(PLATFORM_CLIENT_IP_HEADER));
    const hmacKey = process.env[PROXY_IP_HMAC_ENV];
    if (
        !clientIp
        || !hmacKey
        || Buffer.byteLength(hmacKey, 'utf8') < MIN_HMAC_KEY_BYTES
    ) {
        return unavailable();
    }

    const incomingRequestId = headers.get('x-request-id') || request.headers.get('x-request-id');
    const requestId = incomingRequestId && REQUEST_ID_PATTERN.test(incomingRequestId)
        ? incomingRequestId
        : randomUUID();
    const timestamp = String(Math.floor(Date.now() / 1000));
    const method = request.method.toUpperCase();
    const payload = `v1\n${clientIp}\n${timestamp}\n${method}\n${requestId}`;
    const signature = createHmac('sha256', hmacKey)
        .update(payload, 'utf8')
        .digest('base64url');

    headers.set('x-request-id', requestId);
    headers.set(PROXY_CLIENT_IP_HEADER, clientIp);
    headers.set(PROXY_IP_TIMESTAMP_HEADER, timestamp);
    headers.set(PROXY_IP_SIGNATURE_HEADER, `v1=${signature}`);
    return null;
}
