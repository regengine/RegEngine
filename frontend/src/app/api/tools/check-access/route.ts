/**
 * Verified check for tool access cookie.
 * Called by EmailGate on mount to decide whether to show the gate or the tool.
 *
 * The re_tool_access cookie holds a short-lived JWT minted by the admin
 * service (default 24-hour lifetime). Presence alone is not access:
 * this route asks the admin service to verify the signature, audience,
 * issuer, and unexpired exp before returning hasAccess: true. Anything
 * else, including an expired or forged cookie, returns hasAccess: false
 * and clears the stale cookie. Fail closed when the backend cannot be
 * reached; the tool content itself stays public, only the lead form shows.
 *
 * GET /api/tools/check-access → { hasAccess: boolean }
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';

function clearAccessCookie(response: NextResponse): NextResponse {
    response.cookies.set('re_tool_access', '', {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: 0,
        path: '/',
    });
    return response;
}

export async function GET(request: NextRequest) {
    const token = request.cookies.get('re_tool_access')?.value;
    if (!token) {
        return NextResponse.json({ hasAccess: false });
    }

    const backendUrl = getServerServiceURL('admin').replace(/\/+$/, '');
    if (process.env.VERCEL && !backendUrl) {
        console.error(
            '[api/tools/check-access] ADMIN_SERVICE_URL or NEXT_PUBLIC_API_BASE_URL must be set on Vercel',
        );
        return NextResponse.json({ hasAccess: false });
    }

    try {
        const res = await fetch(`${backendUrl}/api/v1/tools/check-access`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token }),
            redirect: 'manual',
        });

        if (res.status >= 300 && res.status < 400) {
            return clearAccessCookie(NextResponse.json({ hasAccess: false }));
        }

        const data = await res.json().catch(() => null);
        if (!res.ok || !data || data.hasAccess !== true) {
            return clearAccessCookie(NextResponse.json({ hasAccess: false }));
        }

        return NextResponse.json({ hasAccess: true });
    } catch {
        return NextResponse.json({ hasAccess: false });
    }
}
