/**
 * Billing checkout proxy — creates a Stripe Checkout session.
 *
 * This Next.js API route proxies to the backend billing service,
 * adding the API key server-side so it never reaches the browser.
 *
 * POST /api/billing/checkout
 * Body: { plan_id, billing_period, customer_email?, tenant_id?, tenant_name? }
 * Returns: { checkout_url, session_id, plan, billing_period, amount, currency }
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';

const BILLING_BACKEND_URL = process.env.INGESTION_SERVICE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || getServerServiceURL('ingestion');

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { plan_id, billing_period, customer_email, tenant_id, tenant_name } = body;

        if (!plan_id) {
            return NextResponse.json({ error: 'plan_id is required' }, { status: 400 });
        }

        // Build the request to the backend billing service
        const checkoutPayload = {
            plan_id,
            billing_period: billing_period || 'monthly',
            customer_email: customer_email || undefined,
            tenant_id: tenant_id || undefined,
            tenant_name: tenant_name || undefined,
            success_url: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://regengine.co'}/signup?checkout=success&plan=${plan_id}&session_id={CHECKOUT_SESSION_ID}`,
            cancel_url: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://regengine.co'}/pricing?checkout=cancelled`,
        };

        // Get API key from HTTP-only cookie (set by /api/session) or env
        const apiKey = request.cookies.get('re_api_key')?.value
            || process.env.REGENGINE_SERVICE_API_KEY
            || process.env.REGENGINE_API_KEY
            || '';

        const backendResponse = await fetch(`${BILLING_BACKEND_URL}/api/v1/billing/checkout`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': apiKey,
            },
            body: JSON.stringify(checkoutPayload),
        });

        if (!backendResponse.ok) {
            const errorData = await backendResponse.json().catch(() => ({ detail: 'Billing service error' }));
            return NextResponse.json(
                { error: errorData.detail || 'Failed to create checkout session' },
                { status: backendResponse.status },
            );
        }

        const data = await backendResponse.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error('Billing checkout proxy error:', error);
        return NextResponse.json(
            { error: 'Unable to create checkout session. Please try again.' },
            { status: 500 },
        );
    }
}
