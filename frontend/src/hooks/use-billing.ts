/**
 * Billing API React Query Hooks
 *
 * Client-side hooks for the billing service API.
 * Uses React Query for caching and mutation management.
 */

import { useMutation, useQuery } from '@tanstack/react-query';
import { getServiceURL } from '@/lib/api-config';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

// Legacy billing helpers still route through the admin proxy when those
// endpoints exist there. Subscription status is fetched separately from the
// ingestion billing API because that is where the live route now lives.
const BILLING_API_BASE = '/api/admin';

// ── API Client Functions ──────────────────────────────────────────

async function billingFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${BILLING_API_BASE}${path}`;
    const res = await fetchWithCsrf(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options?.headers,
        },
        ...options,
    });

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `Billing API error: ${res.status}`);
    }

    return res.json();
}

// getApiKey removed — callers must pass apiKey from useAuth().apiKey

function getCheckoutContext(): { tenantId?: string; customerEmail?: string } {
    if (typeof window === 'undefined') {
        return {};
    }

    // tenant_id and user are non-sensitive — safe to read from localStorage
    const tenantId = localStorage.getItem('regengine_tenant_id') || undefined;
    const rawUser = localStorage.getItem('regengine_user');
    if (!rawUser) {
        return { tenantId };
    }

    try {
        const parsed = JSON.parse(rawUser) as { email?: string };
        return { tenantId, customerEmail: parsed.email };
    } catch {
        return { tenantId };
    }
}

async function createIngestionCheckout(
    params: { tier_id: string; billing_cycle?: string; credit_code?: string; apiKey?: string },
): Promise<CheckoutSessionData> {
    const { tenantId, customerEmail } = getCheckoutContext();
    const billingCycle = params.billing_cycle || 'annual';
    // Credentials are in HTTP-only cookies — proxy injects them
    const res = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/billing/checkout`, {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            plan_id: params.tier_id,
            billing_period: billingCycle,
            tenant_id: tenantId,
            customer_email: customerEmail,
        }),
    });

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `Billing API error: ${res.status}`);
    }

    const payload = await res.json() as {
        session_id: string;
        checkout_url: string;
        plan: string;
        billing_period: string;
        amount: number;
    };

    return {
        session_id: payload.session_id,
        checkout_url: payload.checkout_url,
        tier: payload.plan,
        billing_cycle: payload.billing_period,
        subtotal: String(payload.amount),
        credits_applied: null,
        total: String(payload.amount),
        sandbox_mode: false,
    };
}

// ── Types ─────────────────────────────────────────────────────────

export interface PricingTier {
    id: string;
    name: string;
    description: string;
    monthly_price: number | null;
    annual_price: number | null;
    cte_limit: string;
    features: { text: string; included: boolean }[];
    highlighted: boolean;
}

export interface TiersResponse {
    tiers: PricingTier[];
    billing_cycles: string[];
    annual_discount: string;
}

export interface SubscriptionData {
    tenant_id: string;
    plan: string;
    status: string;
    billing_period?: string | null;
    current_period_end: string | null;
    events_used: number;
    events_limit: number;
    facilities_used: number;
    facilities_limit: number;
}

export interface CreditBalanceData {
    balance_cents: number;
    balance_display: string;
    total_earned_cents: number;
    total_redeemed_cents: number;
    transaction_count: number;
}

export interface CheckoutSessionData {
    session_id: string;
    checkout_url: string;
    tier: string;
    billing_cycle: string;
    subtotal: string;
    credits_applied: string | null;
    total: string;
    sandbox_mode: boolean;
}

export interface RedeemResult {
    success: boolean;
    amount_cents: number;
    credit_type: string | null;
    new_balance_cents: number;
    message: string;
}

export interface CreditProgram {
    code: string;
    type: string;
    description: string;
    amount_display: string;
    expires_at: string | null;
    available: boolean;
}

// ── Query Hooks ───────────────────────────────────────────────────

/** Fetch available pricing tiers from the billing service */
export function usePricingTiers() {
    return useQuery<TiersResponse>({
        queryKey: ['billing', 'tiers'],
        queryFn: () => billingFetch('/v1/billing/subscriptions/tiers'),
        staleTime: 60_000, // Cache for 1 minute
    });
}

async function fetchCurrentSubscription(
    tenantId: string,
    apiKey?: string | null,
): Promise<SubscriptionData> {
    const headers = new Headers({
        'Content-Type': 'application/json',
    });

    if (apiKey) {
        headers.set('X-RegEngine-API-Key', apiKey);
    }

    const res = await fetchWithCsrf(
        `${getServiceURL('ingestion')}/api/v1/billing/subscription/${tenantId}`,
        { headers },
    );

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `Billing API error: ${res.status}`);
    }

    return res.json();
}

/** Fetch current subscription for the tenant */
export function useCurrentSubscription(tenantId?: string, apiKey?: string | null) {
    return useQuery<SubscriptionData>({
        queryKey: ['billing', 'subscription', tenantId],
        queryFn: () => fetchCurrentSubscription(tenantId!, apiKey),
        enabled: !!tenantId,
        staleTime: 30_000,
    });
}

/** Fetch credit balance for the tenant */
export function useCreditBalance() {
    return useQuery<CreditBalanceData>({
        queryKey: ['billing', 'credits', 'balance'],
        queryFn: () => billingFetch('/v1/billing/credits/balance'),
        staleTime: 30_000,
    });
}

/** Fetch available credit programs */
export function useAvailablePrograms() {
    return useQuery<{ programs: CreditProgram[] }>({
        queryKey: ['billing', 'credits', 'programs'],
        queryFn: () => billingFetch('/v1/billing/credits/available-programs'),
        staleTime: 300_000,
    });
}

// ── Mutation Hooks ────────────────────────────────────────────────

/** Create a Stripe Checkout session */
export function useCreateCheckout() {
    return useMutation<
        CheckoutSessionData,
        Error,
        { tier_id: string; billing_cycle?: string; credit_code?: string; apiKey?: string }
    >({
        mutationFn: createIngestionCheckout,
    });
}

/** Redeem a credit code */
export function useRedeemCredit() {
    return useMutation<RedeemResult, Error, { code: string }>({
        mutationFn: (params) =>
            billingFetch('/v1/billing/credits/redeem', {
                method: 'POST',
                body: JSON.stringify({ code: params.code }),
            }),
    });
}

/** Create a new subscription */
export function useCreateSubscription() {
    return useMutation<
        { subscription: SubscriptionData | null; message: string },
        Error,
        { tier_id: string; billing_cycle?: string }
    >({
        mutationFn: (params) =>
            billingFetch('/v1/billing/subscriptions/create', {
                method: 'POST',
                body: JSON.stringify({
                    tier_id: params.tier_id,
                    billing_cycle: params.billing_cycle || 'annual',
                }),
            }),
    });
}

/** Cancel current subscription */
export function useCancelSubscription() {
    return useMutation<{ message: string }, Error>({
        mutationFn: () =>
            billingFetch('/v1/billing/subscriptions/cancel', { method: 'POST' }),
    });
}
