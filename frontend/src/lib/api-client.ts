import { getServiceURL } from './api-config';
import { getCsrfHeaders, CSRF_PROTECTED_METHODS } from './csrf';
import { DEFAULT_STEP_UP_REASON, emitStepUpRequired } from './step-up-events';
import type {
  HealthCheckResponse,
  APIKeyResponse,
  IngestURLRequest,
  IngestURLResponse,
  IngestCSVResponse,
  EpcisIngestResponse,
  EpcisValidateResponse,
  ComplianceChecklist,
  Industry,
  TenantResponse,
  User,
  Role,
  Invite,

  InviteCreate,
  AcceptInviteRequest,
  FTLCategory,
  SupplierFacilityCreateRequest,
  SupplierFacility,
  FacilityFTLScopingRequest,
  FacilityFTLScopingResponse,
  FacilityRemovalCheck,
  SupplierCTEEventCreateRequest,
  SupplierCTEEventResponse,
  SupplierComplianceGapsResponse,
  SupplierComplianceScore,
  SupplierGapTimeToFixResponse,
  SupplierDataQualityResponse,
  AgreedSendingHoursResponse,
  SupplierQualityDrilldownMetric,
  SupplierQualityRecordsResponse,
  SupplierBulkUploadCommitResponse,
  SupplierBulkUploadParseResponse,
  SupplierBulkUploadStatusResponse,
  SupplierBulkUploadValidateResponse,
  SupplierFDAExportPreviewResponse,
  SupplierTLC,
  SupplierTLCListResponse,
  SupplierTLCUpsertRequest,
  CreateIntegrationProfileRequest,
  IntegrationProfile,
  IntegrationProfilesResponse,
  MappingPreviewResponse,
  AnalysisSummary,
  DiscoveryQueueItem,
  DiscoveryActionResponse,
  BulkDiscoveryResponse,
  PortalLink,
  QAHealthResponse,
  OrganizationSsoPolicyResponse,
  OrganizationSsoPolicyUpdate,
} from '@/types/api';
import type {
  LabelBatchInitRequest,
  LabelBatchInitResponse,
} from '@/types/labels';
import type { ReviewItem } from '@/types/review';

const COOKIE_MANAGED_PLACEHOLDER = 'cookie-managed';

type ReviewQueueResponse = ReviewItemRaw[] | {
  items?: ReviewItemRaw[];
  total?: number;
  offset?: number;
  limit?: number;
};

type CollectionResponse<T> = T[] | {
  items?: T[];
  total?: number;
  skip?: number;
  offset?: number;
  limit?: number;
};

type ReviewItemRaw = {
  review_id?: string;
  id?: string;
  doc_hash?: string;
  confidence_score?: number;
  text_preview?: string;
  text_raw?: string;
  source_text?: string;
  extraction?: unknown;
  extracted_data?: unknown;
  status?: string;
  created_at?: string;
  updated_at?: string;
  tenant_id?: string;
};

function isCookieManagedCredential(value: string | null | undefined): boolean {
  return value?.trim().toLowerCase() === COOKIE_MANAGED_PLACEHOLDER;
}

function credentialHeader(name: string, value: string | null | undefined): Record<string, string> {
  if (!value || isCookieManagedCredential(value)) {
    return {};
  }
  return { [name]: value };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function normalizeCollection<T>(data: CollectionResponse<T> | undefined | null): T[] {
  if (Array.isArray(data)) {
    return data;
  }
  if (data && Array.isArray(data.items)) {
    return data.items;
  }
  return [];
}

function normalizeReviewStatus(status: string | undefined): ReviewItem['status'] {
  const normalized = status?.toUpperCase();
  if (normalized === 'APPROVED' || normalized === 'REJECTED') return normalized;
  return 'PENDING';
}

function normalizeReviewItem(item: ReviewItemRaw): ReviewItem {
  const createdAt = item.created_at || new Date(0).toISOString();
  const preview = item.text_preview || item.source_text || item.text_raw || '';

  return {
    id: item.review_id || item.id || '',
    confidence_score: typeof item.confidence_score === 'number' ? item.confidence_score : 0,
    source_text: preview,
    extracted_data: asRecord(item.extraction ?? item.extracted_data),
    status: normalizeReviewStatus(item.status),
    created_at: createdAt,
    updated_at: item.updated_at || createdAt,
    tenant_id: item.tenant_id || '',
  };
}

export interface SystemStatusResponse {
  overall_status: 'healthy' | 'degraded' | 'unhealthy';
  services: {
    name: string;
    status: 'healthy' | 'unhealthy';
    details: Record<string, unknown>;
  }[];
}

export interface SystemMetricsResponse {
  total_tenants: number;
  total_documents: number;
  active_jobs: number;
  compliance_score?: number | null;
  compliance_grade?: string | null;
  events_ingested?: number | null;
  chain_length?: number | null;
  chain_valid?: boolean | null;
  open_alerts?: number | null;
}

type RequestParams = Record<string, string | number | boolean | null | undefined>;

type RequestConfig = {
  headers?: Record<string, string>;
  params?: RequestParams;
  timeout?: number;
  responseType?: 'blob';
  /**
   * Opens the passkey step-up dialog with this sentence if the backend
   * answers requires_step_up. GETs without it fail quietly so page loads
   * never prompt; writes fall back to DEFAULT_STEP_UP_REASON.
   */
  stepUpReason?: string;
};

type ApiResponse<T = any> = {
  data: T;
  headers: Record<string, string>;
  status: number;
};

type ServiceClient = {
  get<T = any>(path: string, config?: RequestConfig): Promise<ApiResponse<T>>;
  post<T = any>(path: string, data?: unknown, config?: RequestConfig): Promise<ApiResponse<T>>;
  put<T = any>(path: string, data?: unknown, config?: RequestConfig): Promise<ApiResponse<T>>;
  patch<T = any>(path: string, data?: unknown, config?: RequestConfig): Promise<ApiResponse<T>>;
  delete<T = any>(path: string, config?: RequestConfig): Promise<ApiResponse<T>>;
};

function appendParams(url: string, params?: RequestParams): string {
  if (!params) return url;
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    search.append(key, String(value));
  });
  const query = search.toString();
  if (!query) return url;
  return `${url}${url.includes('?') ? '&' : '?'}${query}`;
}

function isBodyInit(value: unknown): value is BodyInit {
  return typeof value === 'string'
    || (typeof FormData !== 'undefined' && value instanceof FormData)
    || (typeof Blob !== 'undefined' && value instanceof Blob)
    || (typeof ArrayBuffer !== 'undefined' && value instanceof ArrayBuffer)
    || (typeof URLSearchParams !== 'undefined' && value instanceof URLSearchParams);
}

class APIClient {
  private adminClient: ServiceClient;
  private ingestionClient: ServiceClient;
  private complianceClient: ServiceClient;
  private graphClient: ServiceClient;

  // Current tenant for multi-tenancy
  private currentTenantId: string | null = null;
  private accessToken: string | null = null;
  private user: User | null = null;

  // Set the current tenant for all API calls
  setCurrentTenant(tenantId: string | null): void {
    this.currentTenantId = tenantId;
  }

  // Get current tenant ID
  getCurrentTenant(): string | null {
    return this.currentTenantId;
  }

  setAccessToken(token: string | null): void {
    this.accessToken = token;
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  setUser(user: User | null): void {
    this.user = user;
  }

  getUser(): User | null {
    return this.user;
  }

  private createClient(baseURL: string): ServiceClient {
    const request = async <T>(
      method: string,
      path: string,
      data?: unknown,
      config: RequestConfig = {},
    ): Promise<ApiResponse<T>> => {
      const trimmedBase = baseURL.replace(/\/+$/, '');
      const normalizedPath = path.startsWith('/') ? path : `/${path}`;
      const url = appendParams(`${trimmedBase}${normalizedPath}`, config.params);
      const headers: Record<string, string> = { ...(config.headers || {}) };

      // API keys are not injected by browser code. They live in HTTP-only
      // cookies and the server-side proxy reads them.
      if (this.accessToken && !isCookieManagedCredential(this.accessToken) && !headers.Authorization) {
        headers.Authorization = `Bearer ${this.accessToken}`;
      }

      if (this.currentTenantId && !headers['X-Tenant-ID']) {
        headers['X-Tenant-ID'] = this.currentTenantId;
      }

      if (CSRF_PROTECTED_METHODS.has(method.toUpperCase())) {
        Object.assign(headers, getCsrfHeaders());
      }

      let body: BodyInit | undefined;
      if (data !== undefined && data !== null) {
        if (isBodyInit(data)) {
          body = data;
        } else {
          body = JSON.stringify(data);
          if (!headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
          }
        }
      }

      const controller = new AbortController();
      const timeoutMs = config.timeout ?? 30000;
      const timeoutId = timeoutMs > 0
        ? globalThis.setTimeout(() => controller.abort(), timeoutMs)
        : undefined;

      try {
        const response = await fetch(url, {
          method,
          headers,
          body,
          credentials: 'include',
          signal: controller.signal,
        });
        const responseHeaders: Record<string, string> = {};
        response.headers.forEach((value, key) => {
          responseHeaders[key.toLowerCase()] = value;
        });

        const responseData = config.responseType === 'blob'
          ? await response.blob()
          : await response.text().then((text) => {
            if (!text) return null;
            try {
              return JSON.parse(text);
            } catch {
              return text;
            }
          });

        if (!response.ok) {
          const error = new Error(response.statusText || 'Request failed') as Error & {
            response?: ApiResponse<unknown>;
            isAxiosError?: boolean;
          };
          error.isAxiosError = true;
          error.response = { data: responseData, headers: responseHeaders, status: response.status };
          const stepUpReason = config.stepUpReason
            ?? (method.toUpperCase() === 'GET' ? undefined : DEFAULT_STEP_UP_REASON);
          if (response.status === 403 && stepUpReason) {
            emitStepUpRequired(responseData, { reason: stepUpReason });
          }
          throw error;
        }

        return { data: responseData as T, headers: responseHeaders, status: response.status };
      } finally {
        if (timeoutId !== undefined) {
          globalThis.clearTimeout(timeoutId);
        }
      }
    };

    return {
      get: (path, config) => request('GET', path, undefined, config),
      post: (path, data, config) => request('POST', path, data, config),
      put: (path, data, config) => request('PUT', path, data, config),
      patch: (path, data, config) => request('PATCH', path, data, config),
      delete: (path, config) => request('DELETE', path, undefined, config),
    };
  }


  constructor() {
    this.adminClient = this.createClient(getServiceURL('admin'));

    // For browser requests, use the Next.js API proxy
    // For server-side, use the backend service directly
    const ingestionBaseUrl = getServiceURL('ingestion');
    this.ingestionClient = this.createClient(ingestionBaseUrl);
    this.complianceClient = this.createClient(getServiceURL('compliance'));
    this.graphClient = this.createClient(getServiceURL('graph'));
  }

  // Admin API
  async getAdminHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.adminClient.get('/health');
    return data;
  }

  async getSystemStatus(): Promise<SystemStatusResponse> {
    const { data } = await this.adminClient.get('/v1/system/status');
    return data;
  }

  async getSystemMetrics(): Promise<SystemMetricsResponse> {
    const { data } = await this.adminClient.get('/v1/system/metrics', { timeout: 8000 });
    return data;
  }

  async getQAHealth(): Promise<QAHealthResponse> {
    const { data } = await this.adminClient.get('/v1/system/qa-health', { timeout: 8000 });
    return data;
  }


  async createAPIKey(params: {
    name: string;
    description?: string;
    tenantId?: string;
  }): Promise<APIKeyResponse> {
    const { data } = await this.adminClient.post(
      '/v1/admin/keys',
      {
        name: params.name,
        description: params.description,
        tenant_id: params.tenantId,
      },
      { stepUpReason: "Confirm it's you to create an API key." },
    );
    return data;
  }

  async generateAPIKey(tenantId?: string): Promise<APIKeyResponse> {
    const { data } = await this.adminClient.post(
      '/v1/admin/keys',
      {
        name: 'Developer Portal Generated Key',
        tenant_id: tenantId,
      },
      { stepUpReason: "Confirm it's you to generate an API key." },
    );
    return data;
  }

  async listAPIKeys(): Promise<APIKeyResponse[]> {
    const { data } = await this.adminClient.get<CollectionResponse<APIKeyResponse>>('/v1/admin/keys');
    return normalizeCollection(data);
  }

  async revokeAPIKey(keyId: string): Promise<void> {
    await this.adminClient.delete(`/v1/admin/keys/${encodeURIComponent(keyId)}`, {
      stepUpReason: "Confirm it's you to revoke this API key.",
    });
  }

  // Ingestion API
  async getIngestionHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.ingestionClient.get('/health');
    return data;
  }

  async ingestURL(apiKey: string | null | undefined, url: string, sourceSystem: string = 'generic'): Promise<IngestURLResponse> {
    const response = await this.ingestionClient.post<IngestURLResponse>(
      '/v1/ingest/url',
      { url, source_system: sourceSystem },
      {
        headers: credentialHeader('X-RegEngine-API-Key', apiKey),
        timeout: 30000
      }
    );
    return response.data;
  }


  async ingestFile(apiKey: string | null | undefined, file: File, sourceSystem: string = 'csv_upload', cteType?: string): Promise<IngestCSVResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('source', sourceSystem);
    // cte_type is optional - the backend auto-detects from a cte_type/event_type column
    if (cteType) {
      formData.append('cte_type', cteType);
    }

    try {
      const response = await this.ingestionClient.post<IngestCSVResponse>(
        '/api/v1/ingest/csv',
        formData,
        {
          headers: credentialHeader('X-RegEngine-API-Key', apiKey),
          timeout: 300000 // Longer timeout for large files (5 minutes)
        }
      );
      const result = response.data;
      const countsAreValid = result
        && [result.total, result.accepted, result.rejected].every(
          value => Number.isInteger(value) && value >= 0,
        )
        && result.total > 0
        && result.accepted + result.rejected === result.total;
      const isNonEmptyString = (value: unknown): value is string => (
        typeof value === 'string' && value.trim().length > 0
      );
      const isSha256 = (value: unknown): value is string => (
        typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value)
      );
      const eventsAreValid = Array.isArray(result?.events)
        && result.events.length === result.total
        && result.events.every(event => event
          && typeof event.traceability_lot_code === 'string'
          && typeof event.cte_type === 'string'
          && (event.status === 'accepted' || event.status === 'rejected')
          && Array.isArray(event.errors)
          && event.errors.every(error => typeof error === 'string')
          && [event.event_id, event.sha256_hash, event.chain_hash].every(
            value => value === undefined || value === null || typeof value === 'string',
          )
          && (event.status === 'rejected' || (
            isNonEmptyString(event.event_id)
            && isSha256(event.sha256_hash)
            && isSha256(event.chain_hash)
            && event.errors.length === 0
          )))
        && result.events.filter(event => event.status === 'accepted').length === result.accepted
        && result.events.filter(event => event.status === 'rejected').length === result.rejected;
      const warningsAreValid = result?.kde_warnings === undefined
        || (Array.isArray(result.kde_warnings)
          && result.kde_warnings.every(warning => typeof warning === 'string'));
      const warningCountIsValid = result?.kde_warning_count === undefined
        || (Number.isInteger(result.kde_warning_count)
          && result.kde_warning_count >= 0
          && result.kde_warning_count === (result.kde_warnings?.length ?? 0));
      if (!countsAreValid || !eventsAreValid
        || typeof result.ingestion_timestamp !== 'string' || !result.ingestion_timestamp.trim()
        || !warningsAreValid || !warningCountIsValid) {
        throw new Error('Unexpected CSV ingestion response');
      }
      return result;
    } catch (error) {
      // CSV parsing uses a detail object; request validation uses a detail array.
      // Keep the original HTTP response for callers while making its message safe to render.
      if (error instanceof Error) {
        const detail = asRecord(asRecord(asRecord(error).response).data).detail;
        const detailRecord = asRecord(detail);
        const messages = typeof detail === 'string' ? [detail]
          : Array.isArray(detail) ? detail.map(item => asRecord(item).msg)
          : [detailRecord.message, ...(Array.isArray(detailRecord.errors) ? detailRecord.errors : [])];
        const message = messages.filter((value): value is string => typeof value === 'string').join(': ');
        if (message) error.message = message;
      }
      throw error;
    }
  }

  // EPCIS 2.0 ingestion. All calls go through the same-origin Next.js
  // ingestion proxy as the CSV upload, with the API key carried the same
  // way (X-RegEngine-API-Key header unless the cookie-managed placeholder
  // is in use, in which case the proxy reads the cookie).
  async ingestEpcisEvent(apiKey: string | null | undefined, event: Record<string, unknown>): Promise<EpcisIngestResponse> {
    const response = await this.ingestionClient.post<EpcisIngestResponse>(
      '/api/v1/epcis/events',
      event,
      {
        headers: credentialHeader('X-RegEngine-API-Key', apiKey),
        timeout: 120000,
      },
    );
    return response.data;
  }

  async ingestEpcisBatch(apiKey: string | null | undefined, events: Record<string, unknown>[]): Promise<EpcisIngestResponse> {
    const response = await this.ingestionClient.post<EpcisIngestResponse>(
      '/api/v1/epcis/events/batch',
      { events },
      {
        headers: credentialHeader('X-RegEngine-API-Key', apiKey),
        timeout: 300000,
      },
    );
    return response.data;
  }

  async ingestEpcisXml(apiKey: string | null | undefined, xml: string): Promise<EpcisIngestResponse> {
    const response = await this.ingestionClient.post<EpcisIngestResponse>(
      '/api/v1/epcis/events/xml',
      xml,
      {
        headers: {
          ...credentialHeader('X-RegEngine-API-Key', apiKey),
          'Content-Type': 'application/xml',
        },
        timeout: 300000,
      },
    );
    return response.data;
  }

  async validateEpcisEvent(apiKey: string | null | undefined, event: Record<string, unknown>): Promise<EpcisValidateResponse> {
    const response = await this.ingestionClient.post<EpcisValidateResponse>(
      '/api/v1/epcis/validate',
      event,
      {
        headers: credentialHeader('X-RegEngine-API-Key', apiKey),
        timeout: 120000,
      },
    );
    return response.data;
  }

  async getIngestionJob(jobId: string): Promise<{ status: string; step?: string }> {
    // Polled every 2s from /ingest: bound each tick so a slow backend cannot
    // pile up overlapping requests. The page skips a tick while one is in flight.
    const { data } = await this.ingestionClient.get(`/v1/ingest/status/${encodeURIComponent(jobId)}`, {
      timeout: 8000,
    });
    return data;
  }

  // Discovery Queue (Phase 31)
  async getDiscoveryQueue(): Promise<DiscoveryQueueItem[]> {
    const { data } = await this.ingestionClient.get<DiscoveryQueueItem[]>('/v1/ingest/discovery/queue');
    return data;
  }

  async approveDiscovery(index: number): Promise<DiscoveryActionResponse> {
    const { data } = await this.ingestionClient.post<DiscoveryActionResponse>('/v1/ingest/discovery/approve', null, {
      params: { index }
    });
    return data;
  }

  async rejectDiscovery(index: number): Promise<DiscoveryActionResponse> {
    const { data } = await this.ingestionClient.post<DiscoveryActionResponse>('/v1/ingest/discovery/reject', null, {
      params: { index }
    });
    return data;
  }

  async bulkApproveDiscovery(indices: number[]): Promise<BulkDiscoveryResponse> {
    const { data } = await this.ingestionClient.post<BulkDiscoveryResponse>('/v1/ingest/discovery/bulk-approve', { indices });
    return data;
  }

  async bulkRejectDiscovery(indices: number[]): Promise<BulkDiscoveryResponse> {
    const { data } = await this.ingestionClient.post<BulkDiscoveryResponse>('/v1/ingest/discovery/bulk-reject', { indices });
    return data;
  }

  // Compliance API
  async getComplianceHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.complianceClient.get('/health');
    return data;
  }

  async getChecklists(industry?: string): Promise<ComplianceChecklist[]> {
    const { data } = await this.complianceClient.get('/checklists', {
      params: industry ? { industry } : undefined,
    });
    // API returns { checklists: [...], total: X } - extract the array
    return data.checklists || data || [];
  }

  async getChecklist(checklistId: string): Promise<ComplianceChecklist> {
    const { data } = await this.complianceClient.get(`/checklists/${encodeURIComponent(checklistId)}`);
    return data;
  }

  // validateConfig() was removed on 2026-04-17 (#1203). The compliance
  // service's POST /validate endpoint was orphaned: no component ever
  // invoked the hook, and the real compliance evaluation lives in the
  // ingestion service's /api/v1/rules/evaluate route via the versioned
  // RulesEngine.

  async getDocumentAnalysis(documentId: string, apiKey: string): Promise<AnalysisSummary> {
    const { data } = await this.ingestionClient.get(`/v1/ingest/documents/${encodeURIComponent(documentId)}/analysis`, {
      headers: credentialHeader('X-RegEngine-API-Key', apiKey)
    });
    return data;
  }

  async getIndustries(): Promise<Industry[]> {
    const { data } = await this.complianceClient.get('/industries');
    // API returns { industries: [...], total: X } - extract the array
    return data.industries || data || [];
  }

  // Graph API - Labels
  //
  // #2887 These paths must carry the full /api/v1 prefix. graphClient's base is
  // the same-origin proxy /api/graph, and src/app/api/graph/[...path]/route.ts:26
  // forwards verbatim: `${GRAPH_URL}/${path}`. The labels router is mounted at
  //   services/graph/app/routes.py:55
  //     v1_router.include_router(labels.router, prefix="/labels", ...)
  // and v1_router reaches the app via server/main.py:910
  //     app.include_router(graph_router, prefix="/api/v1", ...)
  // giving /api/v1/labels/* (services/graph/app/routers/labels.py:171
  // `@router.get("/health")`, :177 `@router.post("/batch/init")`). The old
  // '/v1/labels/...' paths resolved to /v1/labels/... on the backend, which is
  // registered by nothing and 404'd.
  async initializeLabelBatch(
    request: LabelBatchInitRequest,
    tenantId?: string
  ): Promise<LabelBatchInitResponse> {
    const headers: Record<string, string> = tenantId ? { 'X-Tenant-ID': tenantId } : {};
    const { data } = await this.graphClient.post('/api/v1/labels/batch/init', request, { headers });
    return data;
  }

  async getLabelsHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.graphClient.get('/api/v1/labels/health');
    return data;
  }

  /**
   * Ingest CTE events via the webhook endpoint - persists to fsma.cte_events + hash chain.
   * Use this for sample data loading and programmatic event ingestion.
   */
  async ingestWebhookEvents(
    apiKey: string,
    events: Array<{
      cte_type: string;
      traceability_lot_code: string;
      product_description: string;
      quantity: number;
      unit_of_measure: string;
      location_name?: string;
      location_gln?: string;
      timestamp: string;
      kdes?: Record<string, unknown>;
    }>,
    source: string = 'sample_data',
    tenantId: string = 'default',
  ): Promise<{ total: number; accepted: number; rejected: number }> {
    const { data } = await this.ingestionClient.post(
      '/api/v1/webhooks/ingest',
      { source, tenant_id: tenantId, events },
      {
        headers: {
          ...credentialHeader('X-RegEngine-API-Key', apiKey),
          'Content-Type': 'application/json',
        },
        timeout: 120000,
      },
    );
    return data;
  }

  async createTenant(name: string): Promise<TenantResponse> {
    const { data } = await this.adminClient.post(
      '/v1/admin/tenants',
      { name },
      { stepUpReason: "Confirm it's you to create a tenant." },
    );
    return data;
  }

  // Review Workflow
  async getReviewItems(status: string = 'PENDING'): Promise<ReviewItem[]> {
    const { data } = await this.adminClient.get<ReviewQueueResponse>('/v1/admin/review/flagged-extractions', {
      params: { status_filter: status, limit: 50 },
    });

    const items = normalizeCollection(data);
    return items.map(normalizeReviewItem).filter((item) => item.id);
  }

  async approveReviewItem(itemId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/review/flagged-extractions/${encodeURIComponent(itemId)}/approve`, {});
  }

  async rejectReviewItem(itemId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/review/flagged-extractions/${encodeURIComponent(itemId)}/reject`, {});
  }

  // --- User Management ---

  async getUsers(): Promise<User[]> {
    const { data } = await this.adminClient.get<CollectionResponse<User>>('/v1/admin/users');
    return normalizeCollection(data);
  }

  async updateUserRole(userId: string, roleId: string): Promise<void> {
    await this.adminClient.patch(`/v1/admin/users/${encodeURIComponent(userId)}/role`, { role_id: roleId });
  }

  async deactivateUser(userId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/users/${encodeURIComponent(userId)}/deactivate`);
  }

  async getRoles(): Promise<Role[]> {
    const { data } = await this.adminClient.get<CollectionResponse<Role>>('/v1/admin/roles');
    return normalizeCollection(data);
  }

  // --- Invites ---


  async getInvites(): Promise<Invite[]> {
    const { data } = await this.adminClient.get<CollectionResponse<Invite>>('/v1/admin/invites');
    return normalizeCollection(data);
  }

  async createInvite(invite: InviteCreate): Promise<Invite> {
    const { data } = await this.adminClient.post<Invite>('/v1/admin/invites', invite);
    return data;
  }

  async revokeInvite(inviteId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/invites/${encodeURIComponent(inviteId)}/revoke`);
  }

  async acceptInvite(data: AcceptInviteRequest): Promise<void> {
    await this.adminClient.post('/v1/auth/accept-invite', data);
  }

  async getFTLCategories(): Promise<FTLCategory[]> {
    const { data } = await this.adminClient.get<{ categories: FTLCategory[] }>('/v1/supplier/ftl-categories');
    return data.categories || [];
  }

  async listSupplierFacilities(): Promise<SupplierFacility[]> {
    // The backend paginates this route ({ items, total, skip, limit });
    // treating the envelope as the array made every downstream .map throw
    // and locked the Suppliers page on its error banner.
    const { data } = await this.adminClient.get<
      SupplierFacility[] | { items?: SupplierFacility[] }
    >('/v1/supplier/facilities');
    if (Array.isArray(data)) return data;
    return data?.items ?? [];
  }

  async createSupplierFacility(request: SupplierFacilityCreateRequest): Promise<SupplierFacility> {
    const { data } = await this.adminClient.post<SupplierFacility>('/v1/supplier/facilities', request);
    return data;
  }

  async checkFacilityRemoval(facilityId: string): Promise<FacilityRemovalCheck> {
    const { data } = await this.adminClient.get<FacilityRemovalCheck>(
      `/v1/supplier/facilities/${encodeURIComponent(facilityId)}/removal-check`
    );
    return data;
  }

  async getFacilityRemovalCheck(facilityId: string): Promise<FacilityRemovalCheck> {
    return this.checkFacilityRemoval(facilityId);
  }

  async deleteSupplierFacility(facilityId: string): Promise<{ status: string; id: string }> {
    const { data } = await this.adminClient.delete<{ status: string; id: string }>(
      `/v1/supplier/facilities/${encodeURIComponent(facilityId)}`
    );
    return data;
  }

  async setFacilityFTLCategories(
    facilityId: string,
    request: FacilityFTLScopingRequest,
  ): Promise<FacilityFTLScopingResponse> {
    const { data } = await this.adminClient.put<FacilityFTLScopingResponse>(
      `/v1/supplier/facilities/${encodeURIComponent(facilityId)}/ftl-categories`,
      request,
    );
    return data;
  }

  async getFacilityRequiredCTEs(facilityId: string): Promise<FacilityFTLScopingResponse> {
    const { data } = await this.adminClient.get<FacilityFTLScopingResponse>(
      `/v1/supplier/facilities/${encodeURIComponent(facilityId)}/required-ctes`,
    );
    return data;
  }

  async submitSupplierCTEEvent(
    facilityId: string,
    request: SupplierCTEEventCreateRequest,
  ): Promise<SupplierCTEEventResponse> {
    const { data } = await this.adminClient.post<SupplierCTEEventResponse>(
      `/v1/supplier/facilities/${encodeURIComponent(facilityId)}/cte-events`,
      request,
    );
    return data;
  }

  async createSupplierTLC(request: SupplierTLCUpsertRequest): Promise<SupplierTLC> {
    const { data } = await this.adminClient.post<SupplierTLC>('/v1/supplier/tlcs', request);
    return data;
  }

  async listSupplierTLCs(facilityId?: string): Promise<SupplierTLCListResponse> {
    // Paginated like /facilities ({ items, total, skip, limit }). Treating the
    // envelope as an array made `.length` undefined and the Suppliers page
    // render "Lot Codes Tracked: NaN". `total` is the full count; `items` is
    // only the first page.
    const { data } = await this.adminClient.get<
      SupplierTLC[] | Partial<SupplierTLCListResponse>
    >('/v1/supplier/tlcs', {
      params: facilityId ? { facility_id: facilityId } : undefined,
    });
    if (Array.isArray(data)) return { items: data, total: data.length };
    const items = Array.isArray(data?.items) ? data.items : [];
    const total = typeof data?.total === 'number' ? data.total : items.length;
    return { items, total };
  }

  async getSupplierComplianceScore(facilityId?: string): Promise<SupplierComplianceScore> {
    const { data } = await this.adminClient.get<SupplierComplianceScore>('/v1/supplier/compliance-score', {
      params: facilityId ? { facility_id: facilityId } : undefined,
    });
    return data;
  }

  async getSupplierComplianceGaps(facilityId?: string): Promise<SupplierComplianceGapsResponse> {
    const { data } = await this.adminClient.get<SupplierComplianceGapsResponse>('/v1/supplier/gaps', {
      params: facilityId ? { facility_id: facilityId } : undefined,
    });
    return data;
  }

  async getSupplierGapTimeToFix(): Promise<SupplierGapTimeToFixResponse> {
    const { data } = await this.adminClient.get<SupplierGapTimeToFixResponse>('/v1/supplier/gap-time-to-fix');
    return data;
  }

  async getSupplierDataQuality(windowDays?: number): Promise<SupplierDataQualityResponse> {
    const { data } = await this.adminClient.get<SupplierDataQualityResponse>('/v1/supplier/data-quality', {
      params: windowDays ? { window_days: windowDays } : undefined,
    });
    return data;
  }

  async setFacilityAgreedSendingHours(
    facilityId: string,
    agreedSendingHours: number | null,
  ): Promise<AgreedSendingHoursResponse> {
    const { data } = await this.adminClient.put<AgreedSendingHoursResponse>(
      `/v1/supplier/admin/facilities/${encodeURIComponent(facilityId)}/agreed-sending-hours`,
      { agreed_sending_hours: agreedSendingHours },
    );
    return data;
  }

  async getSupplierDataQualityRecords(
    facilityId: string,
    metric: SupplierQualityDrilldownMetric,
    options: { windowDays?: number; limit?: number; offset?: number } = {},
  ): Promise<SupplierQualityRecordsResponse> {
    const { data } = await this.adminClient.get<SupplierQualityRecordsResponse>(
      `/v1/supplier/data-quality/${encodeURIComponent(facilityId)}/records`,
      {
        params: {
          metric,
          window_days: options.windowDays,
          limit: options.limit,
          offset: options.offset,
        },
      },
    );
    return data;
  }

  async getSupplierFDAExportPreview(
    facilityId?: string,
    limit: number = 25,
    tlcCode?: string,
  ): Promise<SupplierFDAExportPreviewResponse> {
    const { data } = await this.adminClient.get<SupplierFDAExportPreviewResponse>('/v1/supplier/export/fda-records/preview', {
      params: {
        ...(facilityId ? { facility_id: facilityId } : {}),
        ...(tlcCode ? { tlc_code: tlcCode } : {}),
        limit,
      },
    });
    return data;
  }

  async downloadSupplierFDARecords(
    format: 'csv' | 'xlsx',
    facilityId?: string,
    tlcCode?: string,
  ): Promise<{ blob: Blob; filename: string; recordCount: number }> {
    const response = await this.adminClient.get('/v1/supplier/export/fda-records', {
      params: {
        format,
        ...(facilityId ? { facility_id: facilityId } : {}),
        ...(tlcCode ? { tlc_code: tlcCode } : {}),
      },
      responseType: 'blob',
    });

    const disposition = response.headers['content-disposition'] as string | undefined;
    const filenameMatch = disposition?.match(/filename=([^;]+)/i);
    const parsedFilename = filenameMatch?.[1]?.trim()?.replace(/^"|"$/g, '');
    const fallbackFilename = `fda_traceability_records.${format}`;

    const recordCountHeader = response.headers['x-fda-record-count'];
    const parsedRecordCount = Number(recordCountHeader);

    return {
      blob: response.data as Blob,
      filename: parsedFilename || fallbackFilename,
      recordCount: Number.isFinite(parsedRecordCount) ? parsedRecordCount : 0,
    };
  }

  // Bulk upload - uses adminClient (Vercel Pro proxy with maxDuration=300s)

  async parseSupplierBulkUpload(file: File): Promise<SupplierBulkUploadParseResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await this.adminClient.post<SupplierBulkUploadParseResponse>(
      '/v1/supplier/bulk-upload/parse',
      formData,
      {
        timeout: 300000,
      },
    );
    return data;
  }

  async validateSupplierBulkUpload(sessionId: string): Promise<SupplierBulkUploadValidateResponse> {
    const { data } = await this.adminClient.post<SupplierBulkUploadValidateResponse>(
      '/v1/supplier/bulk-upload/validate',
      null,
      {
        params: { session_id: sessionId },
        timeout: 300000,
      },
    );
    return data;
  }

  async commitSupplierBulkUpload(sessionId: string): Promise<SupplierBulkUploadCommitResponse> {
    const { data } = await this.adminClient.post<SupplierBulkUploadCommitResponse>(
      '/v1/supplier/bulk-upload/commit',
      null,
      {
        params: { session_id: sessionId },
        timeout: 300000,
      },
    );
    return data;
  }

  async getSupplierBulkUploadStatus(sessionId: string): Promise<SupplierBulkUploadStatusResponse> {
    const { data } = await this.adminClient.get<SupplierBulkUploadStatusResponse>(
      `/v1/supplier/bulk-upload/status/${encodeURIComponent(sessionId)}`,
    );
    return data;
  }

  // Portal Links - supplier portal link management
  async listPortalLinks(): Promise<{ links: PortalLink[]; total: number }> {
    const tenantId = this.currentTenantId;
    if (!tenantId) throw new Error('No tenant selected');
    const { data } = await this.ingestionClient.get('/api/v1/portal/links/list', {
      params: { tenant_id: tenantId },
    });
    return data;
  }

  async createPortalLink(request: {
    supplier_name: string;
    supplier_email?: string;
    expires_days?: number;
    integration_profile_id?: string;
  }): Promise<PortalLink> {
    const tenantId = this.currentTenantId;
    if (!tenantId) throw new Error('No tenant selected');
    const { data } = await this.ingestionClient.post('/api/v1/portal/links', {
      tenant_id: tenantId,
      supplier_name: request.supplier_name,
      supplier_email: request.supplier_email,
      expires_days: request.expires_days || 90,
      integration_profile_id: request.integration_profile_id,
    });
    return data;
  }

  async revokePortalLink(portalId: string): Promise<void> {
    await this.ingestionClient.patch(`/api/v1/portal/links/${encodeURIComponent(portalId)}/revoke`);
  }

  // Supplier Integration Profiles - saved field mappings for portal and file feeds
  async listIntegrationProfiles(): Promise<IntegrationProfilesResponse> {
    const tenantId = this.currentTenantId;
    if (!tenantId) throw new Error('No tenant selected');
    // Bound the integrations-page load: the default 30s left the page on
    // "Loading saved profiles..." until the BFF gave up.
    const { data } = await this.ingestionClient.get<IntegrationProfilesResponse>(
      `/api/v1/integrations/profiles/${encodeURIComponent(tenantId)}`,
      { timeout: 8000 },
    );
    return data;
  }

  async createIntegrationProfile(request: CreateIntegrationProfileRequest): Promise<IntegrationProfile> {
    const tenantId = this.currentTenantId;
    if (!tenantId) throw new Error('No tenant selected');
    const { data } = await this.ingestionClient.post<IntegrationProfile>(
      `/api/v1/integrations/profiles/${encodeURIComponent(tenantId)}`,
      request,
    );
    return data;
  }

  async previewIntegrationProfile(
    profileId: string,
    events: Record<string, unknown>[],
  ): Promise<MappingPreviewResponse> {
    const tenantId = this.currentTenantId;
    if (!tenantId) throw new Error('No tenant selected');
    const { data } = await this.ingestionClient.post<MappingPreviewResponse>(
      `/api/v1/integrations/profiles/${encodeURIComponent(tenantId)}/${encodeURIComponent(profileId)}/preview`,
      { events },
    );
    return data;
  }

  async downloadSupplierBulkUploadTemplate(
    format: 'csv' | 'xlsx',
  ): Promise<{ blob: Blob; filename: string }> {
    const response = await this.adminClient.get('/v1/supplier/bulk-upload/template', {
      params: { format },
      responseType: 'blob',
      timeout: 60000,
    });

    const disposition = response.headers['content-disposition'] as string | undefined;
    const filenameMatch = disposition?.match(/filename=([^;]+)/i);
    const parsedFilename = filenameMatch?.[1]?.trim()?.replace(/^"|"$/g, '');
    const fallbackFilename = `supplier_bulk_upload_template.${format}`;

    return {
      blob: response.data as Blob,
      filename: parsedFilename || fallbackFilename,
    };
  }

  // --- Tenant Settings & Onboarding ---

  async updateTenantSettings(tenantId: string, settings: Record<string, unknown>): Promise<void> {
    await this.adminClient.patch(`/v1/tenants/${encodeURIComponent(tenantId)}/settings`, settings, {
      stepUpReason: "Confirm it's you to change tenant settings.",
    });
  }

  async getOnboardingStatus(tenantId: string): Promise<{
    workspace_profile: Record<string, string>;
    onboarding: Record<string, boolean | string | null>;
    is_complete: boolean;
    partner_tier?: string | null;
  }> {
    const { data } = await this.adminClient.get(`/v1/tenants/${encodeURIComponent(tenantId)}/onboarding`);
    return data;
  }

  async updateOrganizationSsoPolicy(
    organizationId: string,
    payload: OrganizationSsoPolicyUpdate,
    options: { stepUpReason?: string } = {},
  ): Promise<OrganizationSsoPolicyResponse> {
    const { data } = await this.adminClient.put<OrganizationSsoPolicyResponse>(
      `/admin/organizations/${encodeURIComponent(organizationId)}/sso-policy`,
      payload,
      { stepUpReason: options.stepUpReason },
    );
    return data;
  }
}

export const apiClient = new APIClient();
