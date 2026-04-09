/**
 * Proxy for tool email verification — forwards to backend and sets
 * the re_tool_access HTTP-only cookie on successful code confirmation.
 *
 * POST /api/tools/verify
 *   body: { action: "verify" | "confirm", email, code?, tool_name? }
 *
 * On confirm success, sets re_tool_access cookie (30-day, httpOnly, lax).
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL || getServerServiceURL('admin');

const THIRTY_DAYS = 60 * 60 * 24 * 30;

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { action, ...payload } = body;

        const endpoint =
            action === 'confirm'
                ? '/api/v1/tools/confirm-code'
                : '/api/v1/tools/verify-email';

        const res = await fetch(`${BACKEND_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const data = await res.json();

        if (!res.ok) {
            return NextResponse.json(
                { error: data.detail || 'Verification failed' },
                { status: res.status },
            );
        }

        // On successful confirmation, set the HTTP-only cookie
        if (action === 'confirm' && data.token) {
            const response = NextResponse.json({ status: 'verified' });
            response.cookies.set('re_tool_access', data.token, {
                httpOnly: true,
                secure: process.env.NODE_ENV === 'production',
                sameSite: 'lax',
                maxAge: THIRTY_DAYS,
                path: '/',
            });
            return response;
        }

        return NextResponse.json(data);
    } catch (err) {
        console.error('[api/tools/verify] error:', err);
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 },
        );
    }
}
