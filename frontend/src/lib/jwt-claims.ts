/**
 * RegEngine JWT claim decoding (no signature verification).
 *
 * The admin backend (services/admin) owns `JWTKeyRegistry` and is the
 * authoritative verifier. The frontend used to re-verify signatures with
 * `JWT_SIGNING_KEY` / `AUTH_SECRET_KEY` env vars mirrored from the backend,
 * which broke silently whenever a `JWTKeyRegistry.rotate()` on the backend
 * minted a kid the frontend hadn't been told about — every authenticated
 * call 401'd until someone hand-copied the new secret into Vercel.
 *
 * We now decode claims, sanity-check issuer/audience/exp, and forward the
 * request to the backend. The backend's verify is the only one that matters.
 */
import { decodeJwt } from 'jose';

const EXPECTED_AUDIENCE = 'regengine-api';
const EXPECTED_ISSUER = 'regengine-admin';

export type RegEngineClaims = Record<string, unknown>;

export function decodeRegEngineClaims(token: string): RegEngineClaims | null {
    let payload: RegEngineClaims;
    try {
        payload = decodeJwt(token) as RegEngineClaims;
    } catch {
        return null;
    }

    const audience = payload.aud;
    if (typeof audience === 'string' && audience !== EXPECTED_AUDIENCE) return null;
    if (Array.isArray(audience) && !audience.includes(EXPECTED_AUDIENCE)) return null;

    const issuer = payload.iss;
    if (typeof issuer === 'string' && issuer !== EXPECTED_ISSUER) return null;

    const exp = payload.exp;
    if (typeof exp === 'number' && exp * 1000 < Date.now()) return null;

    return payload;
}

export function extractRegEngineTenantId(payload: RegEngineClaims): string | null {
    const value = payload.tenant_id ?? payload.tid;
    return typeof value === 'string' && value.length > 0 ? value : null;
}
