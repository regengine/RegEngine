/**
 * Billing checkout proxy — creates a Stripe Checkout session.
 *
 * This Next.js API route proxies caller-owned credentials to the backend and
 * attaches authenticated source-IP metadata for the shared abuse budget.
 *
 * POST /api/billing/checkout
 * Body: { plan_id, billing_period, customer_email?, tenant_id?, tenant_name? }
 * Returns: { checkout_url, session_id, plan, billing_period, amount, currency }
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    enforceTenantMatch,
    hasRealCallerCredential,
    isUsableCallerCredential,
    rejectRetiredPrivilegedCredential,
    validateProxySession,
    validateUuid,
} from '@/lib/api-proxy';
import {
    appendOpaqueSessionCookies,
    applyCookieCredentials,
    passthroughRequestHeaders,
    prepareTenantScopedProxyHeaders,
    rejectUpstreamRedirect,
} from '@/lib/proxy-factory';
import { attestPrivilegedProxyClientIp } from '@/lib/proxy-ip-attestation';

const BILLING_BACKEND_URL = process.env.INGESTION_SERVICE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || getServerServiceURL('ingestion');

export async function POST(request: NextRequest) {
    try {
        const retiredCredentialError = rejectRetiredPrivilegedCredential(request);
        if (retiredCredentialError) return retiredCredentialError;

        const body = await request.json();
        const { plan_id, billing_period, customer_email, tenant_id, tenant_name } = body;

        if (!plan_id) {
            return NextResponse.json({ error: 'plan_id is required' }, { status: 400 });
        }

        const rawBodyTenantId = typeof tenant_id === 'string' ? tenant_id : undefined;
        const rawCookieTenantId = request.cookies.get('re_tenant_id')?.value;
        const bodyTenantId = rawBodyTenantId ? validateUuid(rawBodyTenantId) : null;
        const cookieTenantId = rawCookieTenantId ? validateUuid(rawCookieTenantId) : null;
        if ((rawBodyTenantId && !bodyTenantId) || (rawCookieTenantId && !cookieTenantId)) {
            return NextResponse.json({ error: 'Invalid tenant identifier' }, { status: 400 });
        }

        const hasCallerCredential = hasRealCallerCredential(request);
        if (hasCallerCredential) {
            const sessionError = await validateProxySession(request);
            if (sessionError) return sessionError;
        }
        if (hasCallerCredential && bodyTenantId && cookieTenantId && bodyTenantId !== cookieTenantId) {
            return NextResponse.json(
                { error: 'Tenant context does not match authenticated session' },
                { status: 403 },
            );
        }

        // Unauthenticated self-serve checkout intentionally carries no tenant
        // identity. For authenticated callers, a body tenant is only an
        // assertion and must agree with the server-validated caller context.
        const authenticatedTenantId = hasCallerCredential ? (cookieTenantId || bodyTenantId) : null;
        if (authenticatedTenantId) {
            const tenantError = await enforceTenantMatch(request, authenticatedTenantId);
            if (tenantError) return tenantError;
        }

        const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://regengine.co';
        const encodedPlanId = encodeURIComponent(String(plan_id));

        // Build the request to the backend billing service
        const checkoutPayload = {
            plan_id,
            billing_period: billing_period || 'monthly',
            customer_email: customer_email || undefined,
            tenant_id: authenticatedTenantId || undefined,
            tenant_name: tenant_name || undefined,
            success_url: `${siteUrl}/signup?checkout=success&plan=${encodedPlanId}`,
            cancel_url: `${siteUrl}/pricing?checkout=cancelled`,
        };

        const headers = new Headers({ 'Content-Type': 'application/json' });
        if (hasCallerCredential && authenticatedTenantId) {
            const credentialError = prepareTenantScopedProxyHeaders(
                headers,
                request,
                authenticatedTenantId,
            );
            if (credentialError) return credentialError;
        } else if (hasCallerCredential) {
            // A tenant-bound API key can still authenticate the backend when
            // the caller omitted an optional assertion. Never inject an env
            // key without an independently validated tenant.
            passthroughRequestHeaders(headers, request, [
                'authorization',
                'x-regengine-api-key',
                'x-api-key',
            ]);
            applyCookieCredentials(headers, request, { respectExistingAuthHeader: true });
            appendOpaqueSessionCookies(headers, request);
        }

        // Never downgrade a credential-bearing request to the anonymous
        // checkout path after browser-controlled headers are sanitized. A
        // forged browser API-key header must be rejected, not silently removed
        // and replaced by the public caller contract.
        if (
            hasCallerCredential &&
            !isUsableCallerCredential(headers.get('x-regengine-api-key')) &&
            !isUsableCallerCredential(headers.get('authorization')) &&
            !headers.has('cookie')
        ) {
            return NextResponse.json({ error: 'Invalid caller credential' }, { status: 401 });
        }

        const attributionError = attestPrivilegedProxyClientIp(headers, request);
        if (attributionError) return attributionError;

        const backendResponse = await fetch(`${BILLING_BACKEND_URL}/api/v1/billing/checkout`, {
            method: 'POST',
            headers,
            body: JSON.stringify(checkoutPayload),
            redirect: 'manual',
        });
        const redirectError = rejectUpstreamRedirect(backendResponse, 'billing');
        if (redirectError) return redirectError;

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
