/**
 * API hooks for all new sprint endpoints.
 * Uses getServiceURL('ingestion') for backend calls.
 * Falls back to mock data when backend is unavailable.
 */

import { getServiceURL } from './api-config';

const BASE = () => getServiceURL('ingestion');

function getApiKey(): string {
    // API key is provided via environment variable only.
    // Never store API keys in localStorage (XSS-accessible).
    return process.env.NEXT_PUBLIC_API_KEY || '';
}

/** Shared fetch helper with API key */
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const apiKey = getApiKey();

    const res = await fetch(`${BASE()}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'X-RegEngine-API-Key': apiKey,
            ...options.headers,
        },
    });

    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
    }

    return res.json();
}

// ── Alerts ──

export async function fetchAlerts(tenantId: string, params?: {
    severity?: string; category?: string; acknowledged?: boolean;
}) {
    const search = new URLSearchParams();
    if (params?.severity) search.set('severity', params.severity);
    if (params?.category) search.set('category', params.category);
    if (params?.acknowledged !== undefined) search.set('acknowledged', String(params.acknowledged));
    const qs = search.toString() ? `?${search}` : '';
    return apiFetch(`/api/v1/alerts/${tenantId}${qs}`);
}

export async function acknowledgeAlert(tenantId: string, alertId: string) {
    return apiFetch(`/api/v1/alerts/${tenantId}/${alertId}/acknowledge`, { method: 'POST' });
}

export async function fetchAlertSummary(tenantId: string) {
    return apiFetch(`/api/v1/alerts/${tenantId}/summary`);
}

// ── Compliance ──

export async function fetchComplianceScore(tenantId: string) {
    return apiFetch(`/api/v1/compliance/score/${tenantId}`);
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

export async function generateSOP(request: SOPRequest) {
    return apiFetch('/api/v1/sop/generate', {
        method: 'POST',
        body: JSON.stringify(request),
    });
}

// ── EPCIS Export ──

export async function exportEPCIS(tenantId: string, retailer?: string) {
    return apiFetch('/api/v1/export/epcis', {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId, target_retailer: retailer }),
    });
}

export async function exportFDA(tenantId: string) {
    return apiFetch('/api/v1/export/fda', {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId }),
    });
}

export async function fetchExportFormats() {
    return apiFetch('/api/v1/export/formats');
}

// ── Billing ──

export async function fetchPlans() {
    return apiFetch('/api/v1/billing/plans');
}

export async function createCheckout(planId: string, tenantId: string, billingPeriod: string) {
    return apiFetch('/api/v1/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({
            plan_id: planId,
            tenant_id: tenantId,
            billing_period: billingPeriod,
        }),
    });
}

export async function fetchSubscription(tenantId: string) {
    return apiFetch(`/api/v1/billing/subscription/${tenantId}`);
}

// ── Supplier Management ──

export async function fetchSupplierDashboard(tenantId: string) {
    return apiFetch(`/api/v1/suppliers/${tenantId}`);
}

export async function addSupplier(tenantId: string, name: string, email: string, products: string[]) {
    return apiFetch(`/api/v1/suppliers/${tenantId}`, {
        method: 'POST',
        body: JSON.stringify({ name, contact_email: email, products }),
    });
}

export async function sendPortalLink(tenantId: string, supplierId: string) {
    return apiFetch(`/api/v1/suppliers/${tenantId}/${supplierId}/send-link`, { method: 'POST' });
}

export async function fetchSupplierHealth(tenantId: string) {
    return apiFetch(`/api/v1/suppliers/${tenantId}/health`);
}

// ── Recall Readiness ──

export async function fetchRecallReport(tenantId: string) {
    return apiFetch(`/api/v1/recall/${tenantId}/report`);
}

// ── Onboarding ──

export async function fetchOnboardingSteps() {
    return apiFetch('/api/v1/onboarding/steps');
}

export async function fetchOnboardingProgress(tenantId: string) {
    return apiFetch(`/api/v1/onboarding/${tenantId}/progress`);
}

export async function completeOnboardingStep(tenantId: string, stepId: string) {
    return apiFetch(`/api/v1/onboarding/${tenantId}/step/${stepId}`, { method: 'POST' });
}

// ── Mock Audit ──

export async function startDrill(scenario: string, tenantId: string) {
    return apiFetch('/api/v1/audit/drill/start', {
        method: 'POST',
        body: JSON.stringify({ scenario_id: scenario, tenant_id: tenantId }),
    });
}

export async function fetchDrillStatus(drillId: string) {
    return apiFetch(`/api/v1/audit/drill/${drillId}`);
}

export async function submitDrillResponse(drillId: string, checklist: Record<string, boolean>) {
    return apiFetch(`/api/v1/audit/drill/${drillId}/submit`, {
        method: 'POST',
        body: JSON.stringify({ checklist }),
    });
}
