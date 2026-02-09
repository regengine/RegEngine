import { NextRequest, NextResponse } from 'next/server';

/**
 * POST /api/alpha-signup
 * 
 * Captures Alpha waitlist signups. Stores to Supabase if configured,
 * otherwise logs to stdout for development.
 */
export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { email, company, role } = body;

        if (!email || typeof email !== 'string' || !email.includes('@')) {
            return NextResponse.json(
                { error: 'A valid email is required.' },
                { status: 400 }
            );
        }

        const signup = {
            email: email.trim().toLowerCase(),
            company: company?.trim() || null,
            role: role?.trim() || null,
            source: 'alpha-page',
            created_at: new Date().toISOString(),
            ip: request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip') || 'unknown',
            user_agent: request.headers.get('user-agent') || 'unknown',
        };

        // Try Supabase if configured
        const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
        const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

        if (supabaseUrl && supabaseKey) {
            const res = await fetch(`${supabaseUrl}/rest/v1/alpha_signups`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'apikey': supabaseKey,
                    'Authorization': `Bearer ${supabaseKey}`,
                    'Prefer': 'return=minimal',
                },
                body: JSON.stringify(signup),
            });

            if (!res.ok) {
                const text = await res.text();
                // Table might not exist yet — log and continue gracefully
                console.warn('[alpha-signup] Supabase insert failed:', res.status, text);
                console.log('[alpha-signup] Captured (fallback):', JSON.stringify(signup));
            } else {
                console.log('[alpha-signup] Saved to Supabase:', signup.email);
            }
        } else {
            // No Supabase — log to stdout so signups aren't lost
            console.log('[alpha-signup] Captured:', JSON.stringify(signup));
        }

        return NextResponse.json(
            { success: true, message: 'Thank you! We\'ll be in touch within 48 hours.' },
            { status: 201 }
        );
    } catch (err) {
        console.error('[alpha-signup] Error:', err);
        return NextResponse.json(
            { error: 'Something went wrong. Please try again.' },
            { status: 500 }
        );
    }
}
