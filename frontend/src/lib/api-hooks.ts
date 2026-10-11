/**
 * API hooks for all new sprint endpoints.
 * Routes through the Next.js ingestion proxy (/api/ingestion) which
 * reads credentials from HTTP-only cookies — no client-side API key needed.
 *
 * The `apiKey` parameter is kept for backward compatibility but is ignored.
 * Internal callers can omit it entirely and rely on cookie-backed auth.
 */

import { getServiceURL } from './api-config';
import { fetchWithCsrf } from './fetch-with-csrf';

const BASE = () => getServiceURL('ingestion');
const API_FETCH_TIMEOUT_MS = 8000;

function isAbortError(err: unknown): boolean {
    return err instanceof Error && (err.name === 'AbortError' || err.name === 'TimeoutError');
}

/** Methods safe to retry: replaying them cannot cause a duplicate side effect. */
const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']);

function isIdempotentMethod(method: string | undefined): boolean {
    return IDEMPOTENT_METHODS.has((method || 'GET').toUpperCase());
}

/** Shared fetch helper with retry logic. Credentials are in HTTP-only cookies.
 * Only idempotent methods are retried; POST and PATCH are attempted once so
 * a slow upstream cannot turn one user action into two side effects. */
async function apiFetch<T>(path: string, _apiKey?: string | null, options: RequestInit = {}): Promise<T> {
    const retryable = isIdempotentMethod(options.method);
    const MAX_RETRIES = retryable ? 2 : 0;
    const RETRY_DELAYS = [500, 1500];
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        let res: Response | undefined;
        try {
            res = await fetchWithCsrf(`${BASE()}${path}`, {
                ...options,
                credentials: 'include', // Send HTTP-only cookies
                signal: options.signal ?? AbortSignal.timeout(API_FETCH_TIMEOUT_MS),
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers,
                },
            });
        } catch (err) {
            lastError = err instanceof Error ? err : new Error('Network request failed');
            if (isAbortError(err)) {
                throw lastError;
            }
        }

        if (res === undefined) {
            // Transport failure — retry with backoff.
            if (attempt < MAX_RETRIES) {
                await new Promise(resolve => setTimeout(resolve, RETRY_DELAYS[attempt]));
            }
            continue;
        }

        if (res.ok) {
            return res.json();
        }

        // Don't retry client errors (4xx): the request itself is wrong, so
        // resending it only repeats the failure. Thrown outside the
        // try/catch above so this throw is never mistaken for a retryable
        // transport failure.
        if (res.status >= 400 && res.status < 500) {
            throw new Error(`API error: ${res.status} ${res.statusText}`);
        }

        // Server error (5xx) — retry with backoff.
        lastError = new Error(`API error: ${res.status} ${res.statusText}`);
        if (attempt < MAX_RETRIES) {
            await new Promise(resolve => setTimeout(resolve, RETRY_DELAYS[attempt]));
        }
    }

    throw lastError!;
}

// ── Alerts ──

export async function fetchAlerts(tenantId: string, apiKey?: string | null, params?: {
    severity?: string; category?: string; acknowledged?: boolean;
}) {
    const search = new URLSearchParams();
    if (params?.severity) search.set('severity', params.severity);
    if (params?.category) search.set('category', params.category);
    if (params?.acknowledged !== undefined) search.set('acknowledged', String(params.acknowledged));
    const qs = search.toString() ? `?${search}` : '';
    return apiFetch(`/api/v1/alerts/${encodeURIComponent(tenantId)}${qs}`, apiKey);
}

export async function acknowledgeAlert(tenantId: string, apiKey: string | null | undefined, alertId: string) {
    return apiFetch(`/api/v1/alerts/${encodeURIComponent(tenantId)}/${encodeURIComponent(alertId)}/acknowledge`, apiKey, { method: 'POST' });
}

export async function fetchAlertSummary(tenantId: string, apiKey?: string | null) {
    return apiFetch(`/api/v1/alerts/${encodeURIComponent(tenantId)}/summary`, apiKey);
}

// ── Compliance ──

export async function fetchComplianceScore(tenantId: string, apiKey?: string | null) {
    return apiFetch(`/api/v1/compliance/score/${encodeURIComponent(tenantId)}`, apiKey);
}

export interface WorkbenchReadinessSnapshot {
    tenant_id: string;
    score: number | null;
    label: string | null;
    run_id: string | null;
    saved_at: string | null;
    unresolved_fix_count: number;
    export_eligible: boolean;
    source: string;
}

export async function fetchWorkbenchReadinessSummary(tenantId: string, apiKey?: string | null) {
    const query = new URLSearchParams({ tenant_id: tenantId });
    return apiFetch<WorkbenchReadinessSnapshot>(
        `/api/v1/inflow-workbench/readiness/summary?${query}`,
        apiKey,
    );
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

export async function createCheckout(_apiKey: string, planId: string, _tenantId: string, billingPeriod: string) {
    const res = await fetchWithCsrf('/api/billing/checkout', {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            plan_id: planId,
            billing_period: billingPeriod,
        }),
    });

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `API error: ${res.status} ${res.statusText}`);
    }

    return res.json();
}

export async function fetchSubscription(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/billing/subscription/${encodeURIComponent(tenantId)}`, apiKey);
}

// ── Supplier Management ──

export async function fetchSupplierDashboard(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/suppliers/${encodeURIComponent(tenantId)}`, apiKey);
}

export async function addSupplier(tenantId: string, apiKey: string, name: string, email: string, products: string[]) {
    return apiFetch(`/api/v1/suppliers/${encodeURIComponent(tenantId)}`, apiKey, {
        method: 'POST',
        body: JSON.stringify({ name, contact_email: email, products }),
    });
}

export async function sendPortalLink(tenantId: string, apiKey: string, supplierId: string) {
    return apiFetch(`/api/v1/suppliers/${encodeURIComponent(tenantId)}/${encodeURIComponent(supplierId)}/send-link`, apiKey, { method: 'POST' });
}

export async function fetchSupplierHealth(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/suppliers/${encodeURIComponent(tenantId)}/health`, apiKey);
}

// ── Recall Readiness ──

export async function fetchRecallReport(tenantId: string, apiKey?: string | null) {
    return apiFetch(`/api/v1/recall/${encodeURIComponent(tenantId)}/report`, apiKey);
}

// ── Onboarding ──

export async function fetchOnboardingSteps(apiKey: string) {
    return apiFetch('/api/v1/onboarding/steps', apiKey);
}

export async function fetchOnboardingProgress(tenantId: string, apiKey: string) {
    return apiFetch(`/api/v1/onboarding/${encodeURIComponent(tenantId)}/progress`, apiKey);
}

export async function completeOnboardingStep(tenantId: string, apiKey: string, stepId: string) {
    return apiFetch(`/api/v1/onboarding/${encodeURIComponent(tenantId)}/step/${encodeURIComponent(stepId)}`, apiKey, { method: 'POST' });
}

// ── Mock Audit ──

export async function startDrill(apiKey: string, scenario: string, tenantId: string) {
    return apiFetch('/api/v1/audit/drill/start', apiKey, {
        method: 'POST',
        body: JSON.stringify({ scenario_id: scenario, tenant_id: tenantId }),
    });
}

export async function fetchDrillStatus(apiKey: string, drillId: string) {
    return apiFetch(`/api/v1/audit/drill/${encodeURIComponent(drillId)}`, apiKey);
}

export async function submitDrillResponse(apiKey: string, drillId: string, checklist: Record<string, boolean>) {
    return apiFetch(`/api/v1/audit/drill/${encodeURIComponent(drillId)}/submit`, apiKey, {
        method: 'POST',
        body: JSON.stringify({ checklist }),
    });
}
