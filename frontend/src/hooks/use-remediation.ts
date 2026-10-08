'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { POLL_CONTROL_PLANE_MS } from '@/lib/polling-config';

// ---------------------------------------------------------------------------
// Supplier manifest remediation hooks — same proxy pattern as
// use-control-plane.ts: HTTP-only cookies via the ingestion proxy.
// ---------------------------------------------------------------------------

const INGESTION_API = '/api/ingestion';

async function remFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetchWithCsrf(`${INGESTION_API}${endpoint}`, {
        ...options,
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            ...options?.headers,
        },
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

export interface ManifestSummary {
    ingestion_run_id: string;
    original_filename: string;
    source_sha256: string;
    run_status: string;
    total_rows: number;
    started_at: string | null;
    completed_at: string | null;
    ready_to_release: number;
    blocked: number;
    released: number;
    data_hold: boolean;
}

export interface RecordFailure {
    issue_id: string;
    rule_id: string;
    rule_title: string;
    severity: string;
    why_failed: string;
    remediation: string | null;
}

export interface ManifestRecord {
    record_id: string;
    row_number: number;
    validation_status: string;
    release_status: string;
    released_event_id: string | null;
    remediation_case_id: string | null;
    case: {
        case_id: string;
        case_status: string;
        due_at: string | null;
        notified: boolean;
    } | null;
    failures: RecordFailure[];
}

export interface ManifestDetail {
    ingestion_run_id: string;
    source_sha256: string;
    original_filename: string;
    run_status: string;
    counts: { total: number; accepted: number; rejected: number };
    records: ManifestRecord[];
}

export interface RemediationMetrics {
    total_records_processed: number;
    first_pass_acceptance_rate: number | null;
    exceptions_by_rule: Record<string, number>;
    supplier_action_cases: number;
    supplier_corrections_submitted: number;
    cases_released: number;
    resolved_without_buyer_intervention: number;
    resolved_without_buyer_intervention_rate: number | null;
    median_remediation_seconds: number | null;
}

export interface OutboxPreview {
    id: string;
    case_id: string | null;
    recipient: string | null;
    subject: string;
    body: string;
    status: string;
    created_at: string | null;
    sent_at: string | null;
    last_error: string | null;
}

export function useRemediationManifests(tenantId: string) {
    const { isAuthenticated } = useAuth();
    return useQuery({
        queryKey: ['remediation', 'manifests', tenantId],
        queryFn: () =>
            remFetch<{ manifests: ManifestSummary[] }>('/api/v1/remediation/manifests'),
        enabled: !!tenantId && isAuthenticated,
        refetchInterval: POLL_CONTROL_PLANE_MS,
    });
}

export function useRemediationManifest(tenantId: string, runId: string | null) {
    const { isAuthenticated } = useAuth();
    return useQuery({
        queryKey: ['remediation', 'manifest', tenantId, runId],
        queryFn: () => remFetch<ManifestDetail>(`/api/v1/remediation/manifests/${encodeURIComponent(runId)}`),
        enabled: !!tenantId && !!runId && isAuthenticated,
        refetchInterval: POLL_CONTROL_PLANE_MS,
    });
}

export function useRemediationMetrics(tenantId: string) {
    const { isAuthenticated } = useAuth();
    return useQuery({
        queryKey: ['remediation', 'metrics', tenantId],
        queryFn: () => remFetch<RemediationMetrics>('/api/v1/remediation/metrics'),
        enabled: !!tenantId && isAuthenticated,
        refetchInterval: POLL_CONTROL_PLANE_MS,
    });
}

export function useRemediationOutbox(tenantId: string) {
    const { isAuthenticated } = useAuth();
    return useQuery({
        queryKey: ['remediation', 'outbox', tenantId],
        queryFn: () =>
            remFetch<{ notifications: OutboxPreview[] }>('/api/v1/remediation/outbox'),
        enabled: !!tenantId && isAuthenticated,
        refetchInterval: POLL_CONTROL_PLANE_MS,
    });
}

export function useReleaseManifest(tenantId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (runId: string) =>
            remFetch<{ released: unknown[]; skipped: unknown[] }>(
                `/api/v1/remediation/manifests/${encodeURIComponent(runId)}/release`,
                { method: 'POST', body: JSON.stringify({}) },
            ),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: ['remediation'] });
        },
    });
}

export function useIssueCorrectionLink(tenantId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ caseId, supplierEmail }: { caseId: string; supplierEmail?: string }) =>
            remFetch<{ correction_url: string; expires_at: string; token: string }>(
                `/api/v1/remediation/cases/${encodeURIComponent(caseId)}/link`,
                {
                    method: 'POST',
                    body: JSON.stringify(supplierEmail ? { supplier_email: supplierEmail } : {}),
                },
            ),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: ['remediation'] });
        },
    });
}
