/**
 * API hooks for all new sprint endpoints.
 * Uses getServiceURL('ingestion') for backend calls.
 *
 * All functions accept an `apiKey` parameter — callers should get this
 * from `useAuth().apiKey` so credentials flow through the auth context
 * instead of env vars or localStorage.
 */

import { getServiceURL } from './api-config';

const BASE = () => getServiceURL('ingestion');

const MAX_RETRIES = 2;
const RETRY_DELAYS = [500, 1500]; // ms — exponential backoff

/** Shared fetch helper with API key and retry logic */
async function apiFetch<T>(path: string, apiKey: string, options: RequestInit = {}): Promise<T> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
            const res = await fetch(`${BASE()}${path}`, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    'X-RegEngine-API-Key': apiKey,
                    ...options.headers,
                },
            });

            // Don't retry client errors (4xx) — only server/network errors
            if (res.ok) {
                return res.json();
            }

            if (res.status >= 400 && res.status < 500) {
                throw new Error(`API error: ${res.status} ${res.statusText}`);
            }

            // Server error (5xx) — retry
            lastError = new Error(`API error: ${res.status} ${res.statusText}`);
        } catch (err) {
            lastError = err instanceof Error ? err : new Error('Network request failed');
        }

        // Wait before retrying (skip delay after last attempt)
        if (attempt < MAX_RETRIES) {
            await new Promise(resolve => setTimeout(resolve, RETRY_DELAYS[attempt]));
        }
    }

    throw lastError!;
}

// ── Alerts ──

export async function fetchAlerts(tenantId: string, apiKey: string, params?: {
    severity?: string; category?: string; acknowledged?: boolean;
}) {
    const search = new URLSearchParams();
    if (params?.severity) search.set('severity', params.severity);
    if (params?.category) search.set('category', params.category);
    if (params?.acknowledged !== undefined) search.set('acknowledged', String(params.acknowledged));
    const qs = search.toString() ? `?${search}` : '';
    return apiFetch(`/api/v1/alerts/${tenantId}${qs}`, apiKey);
}

export async function acknowledgeAlert(tenantId: string, apiKey: string, alertId: string) {
    return apiFetch(`/api/v1/alerts/${tenantId}/${alertId}/acknowledge`, apiKey, { method: 'POST' });
}

export async function fetchAlertSummary(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/alerts/${tenantId}/summary`, apiKey);
}

// ── Compliance ──

export async function fetchComplianceScore(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/compliance/score/${tenantId}`, apiKey);
}

// ── SOP Generator ──

export interface SOPRequest {
    company_name: string;
    company_type: string;
    primary_contact: string;
    contact_title?: string;
    products: string[];
    facilities: string[];
    has_iot?: boolean;
    has_erp?: boolean;
    target_retailers?: string[];
}

export async function generateSOP(apiKey: string, request: SOPRequest) {
    return apiFetch('/api/v1/sop/generate', apiKey, {
        method: 'POST',
        body: JSON.stringify(request),
    });
}

// ── EPCIS Export ──

export async function exportEPCIS(tenantId: string, apiKey: string, retailer?: string) {
    return apiFetch('/api/v1/export/epcis', apiKey, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId, target_retailer: retailer }),
    });
}

export async function exportFDA(tenantId: string, apiKey: string) {
    return apiFetch('/api/v1/export/fda', apiKey, {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId }),
    });
}

export async function fetchExportFormats(apiKey: string) {
    return apiFetch('/api/v1/export/formats', apiKey);
}

// ── Billing ──

export async function fetchPlans(apiKey: string) {
    return apiFetch('/api/v1/billing/plans', apiKey);
}

export async function createCheckout(apiKey: string, planId: string, tenantId: string, billingPeriod: string) {
    return apiFetch('/api/v1/billing/checkout', apiKey, {
        method: 'POST',
        body: JSON.stringify({
            plan_id: planId,
            tenant_id: tenantId,
            billing_period: billingPeriod,
        }),
    });
}

export async function fetchSubscription(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/billing/subscription/${tenantId}`, apiKey);
}

// ── Supplier Management ──

export async function fetchSupplierDashboard(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/suppliers/${tenantId}`, apiKey);
}

export async function addSupplier(tenantId: string, apiKey: string, name: string, email: string, products: string[]) {
    return apiFetch(`/api/v1/suppliers/${tenantId}`, apiKey, {
        method: 'POST',
        body: JSON.stringify({ name, contact_email: email, products }),
    });
}

export async function sendPortalLink(tenantId: string, apiKey: string, supplierId: string) {
    return apiFetch(`/api/v1/suppliers/${tenantId}/${supplierId}/send-link`, apiKey, { method: 'POST' });
}

export async function fetchSupplierHealth(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/suppliers/${tenantId}/health`, apiKey);
}

// ── Recall Readiness ──

export async function fetchRecallReport(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/recall/${tenantId}/report`, apiKey);
}

// ── Onboarding ──

export async function fetchOnboardingSteps(apiKey: string) {
    return apiFetch('/api/v1/onboarding/steps', apiKey);
}

export async function fetchOnboardingProgress(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/onboarding/${tenantId}/progress`, apiKey);
}

export async function completeOnboardingStep(tenantId: string, apiKey: string, stepId: string) {
    return apiFetch(`/api/v1/onboarding/${tenantId}/step/${stepId}`, apiKey, { method: 'POST' });
}

// ── Mock Audit ──

export async function startDrill(apiKey: string, scenario: string, tenantId: string) {
    return apiFetch('/api/v1/audit/drill/start', apiKey, {
        method: 'POST',
        body: JSON.stringify({ scenario_id: scenario, tenant_id: tenantId }),
    });
}

export async function fetchDrillStatus(apiKey: string, drillId: string) {
    return apiFetch(`/api/v1/audit/drill/${drillId}`, apiKey);
}

export async function submitDrillResponse(apiKey: string, drillId: string, checklist: Record<string, boolean>) {
    return apiFetch(`/api/v1/audit/drill/${drillId}/submit`, apiKey, {
        method: 'POST',
        body: JSON.stringify({ checklist }),
    });
}
