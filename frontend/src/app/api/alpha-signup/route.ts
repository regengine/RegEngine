import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
    let body: { email?: string; name?: string; company?: string };
    try {
        body = await request.json();
    } catch {
        return NextResponse.json(
            { success: false, error: 'Invalid request body' },
            { status: 400 }
        );
    }

    const { email, name, company } = body;

    if (!email) {
        return NextResponse.json(
            { success: false, error: 'Email is required' },
            { status: 400 }
        );
    }

    const adminUrl = process.env.ADMIN_SERVICE_URL;
    if (!adminUrl) {
        console.error('[alpha-signup] ADMIN_SERVICE_URL is not configured');
        return NextResponse.json(
            { success: false, error: 'Alpha signup is not yet configured' },
            { status: 503 }
        );
    }

    try {
        const response = await fetch(`${adminUrl}/api/v1/alpha/signup`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, name, company }),
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            console.error('[alpha-signup] Backend error:', response.status, data);
            return NextResponse.json(
                { success: false, error: data.detail || data.error || 'Signup failed' },
                { status: response.status }
            );
        }

        console.info('[alpha-signup] Signup accepted for:', email);
        return NextResponse.json({ success: true, ...data });

    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Signup service unavailable';
        console.error('[alpha-signup] Backend unreachable:', error);
        return NextResponse.json(
            { success: false, error: message },
            { status: 503 }
        );
    }
}
