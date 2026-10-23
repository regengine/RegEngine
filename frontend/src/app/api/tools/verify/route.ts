/**
 * Proxy for tool email verification - forwards to backend and sets
 * the re_tool_access HTTP-only cookie on successful code confirmation.
 *
 * POST /api/tools/verify
 *   body: { action: "verify" | "confirm", email, code?, tool_name? }
 *
 * On confirm success, sets re_tool_access cookie (httpOnly, lax) with a
 * maxAge matching the minted token lifetime (default 24 hours, reported
 * by the backend as expires_in_seconds).
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';

/** Default tool-access cookie lifetime: 24 hours, matching the backend mint. */
const DEFAULT_TOOL_ACCESS_MAX_AGE = 60 * 60 * 24;

function resolveCookieMaxAge(expiresInSeconds: unknown): number {
    if (
        typeof expiresInSeconds === 'number' &&
        Number.isFinite(expiresInSeconds) &&
        expiresInSeconds >= 60 &&
        expiresInSeconds <= DEFAULT_TOOL_ACCESS_MAX_AGE
    ) {
        return Math.floor(expiresInSeconds);
    }
    return DEFAULT_TOOL_ACCESS_MAX_AGE;
}

function getBackendUrl(): string {
    return getServerServiceURL('admin').replace(/\/+$/, '');
}

export async function POST(request: NextRequest) {
    // On Vercel, localhost fallback will never work - fail fast with a clear error.
    const backendUrl = getBackendUrl();
    if (process.env.VERCEL && !backendUrl) {
        console.error(
            '[api/tools/verify] ADMIN_SERVICE_URL or NEXT_PUBLIC_API_BASE_URL must be set on Vercel; cannot reach localhost from serverless functions',
        );
        return NextResponse.json(
            { error: 'Backend not configured. Contact support' },
            { status: 503 },
        );
    }

    try {
        let body: unknown;
        try {
            body = await request.json();
        } catch {
            return NextResponse.json(
                { error: 'Invalid request body' },
                { status: 400 },
            );
        }
        if (!body || typeof body !== 'object' || Array.isArray(body)) {
            return NextResponse.json(
                { error: 'Invalid request body' },
                { status: 400 },
            );
        }
        const { action, ...payload } = body as Record<string, unknown>;

        const endpoint =
            action === 'confirm'
                ? '/api/v1/tools/confirm-code'
                : '/api/v1/tools/verify-email';

        const res = await fetch(`${backendUrl}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            redirect: 'manual',
        });

        if (res.status >= 300 && res.status < 400) {
            return NextResponse.json(
                { error: 'Verification service redirect refused' },
                { status: 502 },
            );
        }

        const data = await res.json();

        if (!res.ok) {
            return NextResponse.json(
                { error: data.detail || 'Verification failed' },
                { status: res.status },
            );
        }

        // On successful confirmation, set the HTTP-only cookie with a
        // lifetime matching the minted token, so the cookie stops
        // granting access when the JWT itself expires.
        if (action === 'confirm' && data.token) {
            const response = NextResponse.json({ status: 'verified' });
            response.cookies.set('re_tool_access', data.token, {
                httpOnly: true,
                secure: process.env.NODE_ENV === 'production',
                sameSite: 'lax',
                maxAge: resolveCookieMaxAge(data.expires_in_seconds),
                path: '/',
            });
            return response;
        }

        return NextResponse.json(data);
    } catch (err) {
        console.error('[api/tools/verify] request failed', {
            errorClass: err instanceof Error ? err.name : 'UnknownError',
        });
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 },
        );
    }
}
