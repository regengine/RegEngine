import axios, { AxiosInstance } from 'axios';
import { getServiceURL } from './api-config';
import type {
  HealthCheckResponse,
  APIKeyResponse,
  IngestURLRequest,
  IngestURLResponse,
  ComplianceChecklist,
  ValidationRequest,
  ValidationResult,
  OpportunityArbitrage,
  ComplianceGap,
  Industry,
  TenantResponse,
  LoginResponse,
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
  SupplierCTEEventCreateRequest,
  SupplierCTEEventResponse,
  SupplierComplianceGapsResponse,
  SupplierComplianceScore,
  SupplierDemoResetResponse,
  SupplierFunnelEventRequest,
  SupplierFunnelEventResponse,
  SupplierFunnelSummaryResponse,
  SupplierBulkUploadCommitResponse,
  SupplierBulkUploadParseResponse,
  SupplierBulkUploadStatusResponse,
  SupplierBulkUploadValidateResponse,
  SupplierFDAExportPreviewResponse,
  SupplierSocialProofResponse,
  SupplierTLC,
  SupplierTLCUpsertRequest,
  AnalysisSummary,
  TraceabilityEventRequest,
  TraceabilityEventResponse,
} from '@/types/api';
import type {
  LabelBatchInitRequest,
  LabelBatchInitResponse,
} from '@/types/labels';
import type { ReviewItem } from '@/types/review';

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
}

class APIClient {
  private adminClient: AxiosInstance;
  private ingestionClient: AxiosInstance;
  private opportunityClient: AxiosInstance;
  private complianceClient: AxiosInstance;
  private graphClient: AxiosInstance;

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

  private createClient(baseURL: string): AxiosInstance {
    const client = axios.create({
      baseURL,
      timeout: 30000,
    });

    // Default API key for development (test bypass token)
    const defaultApiKey = typeof window !== 'undefined'
      ? process.env.NEXT_PUBLIC_API_KEY || 'regengine-universal-test-key-2026'
      : process.env.NEXT_PUBLIC_API_KEY || 'regengine-universal-test-key-2026';

    client.interceptors.request.use((config) => {
      // Check for existing API key headers (case-insensitive since axios lowercases header names)
      const headerKeys = Object.keys(config.headers || {}).map(k => k.toLowerCase());
      const hasApiKey = headerKeys.some(k =>
        k === 'x-api-key' || k === 'x-admin-key' || k === 'x-regengine-api-key'
      );

      // Only add default API key if no API key header is already present
      if (!hasApiKey) {
        config.headers['X-RegEngine-API-Key'] = defaultApiKey;
      }

      // Add Bearer Token if available
      if (this.accessToken) {
        config.headers['Authorization'] = `Bearer ${this.accessToken}`;
      }

      // Add X-Tenant-ID header for multi-tenancy if tenant is set
      if (this.currentTenantId && !config.headers['X-Tenant-ID']) {
        config.headers['X-Tenant-ID'] = this.currentTenantId;
      }

      return config;
    });

    return client;
  }


  constructor() {
    this.adminClient = this.createClient(getServiceURL('admin'));
    // For browser requests, use the Next.js API proxy
    // For server-side, use the backend service directly
    const ingestionBaseUrl = getServiceURL('ingestion');
    this.ingestionClient = this.createClient(ingestionBaseUrl);
    this.opportunityClient = this.createClient(getServiceURL('opportunity'));
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
    const { data } = await this.adminClient.get('/v1/system/metrics');
    return data;
  }


  async createAPIKey(
    adminKey: string,
    params: { name: string; description?: string; tenantId?: string },
  ): Promise<APIKeyResponse> {
    const { data } = await this.adminClient.post(
      '/v1/admin/keys',
      {
        name: params.name,
        description: params.description,
        tenant_id: params.tenantId,
      },
      { headers: { 'X-Admin-Key': adminKey } },
    );
    return data;
  }

  async generateAPIKey(adminKey: string, tenantId?: string): Promise<APIKeyResponse> {
    const { data } = await this.adminClient.post(
      '/v1/admin/api-keys',
      {
        name: 'Developer Portal Generated Key',
        tenant_id: tenantId,
      },
      { headers: { 'X-Admin-Key': adminKey } },
    );
    return data;
  }

  async listAPIKeys(adminKey: string): Promise<APIKeyResponse[]> {
    const { data } = await this.adminClient.get('/v1/admin/keys', {
      headers: { 'X-Admin-Key': adminKey },
    });
    return data;
  }

  async revokeAPIKey(adminKey: string, keyId: string): Promise<void> {
    await this.adminClient.delete(`/v1/admin/keys/${keyId}`, {
      headers: { 'X-Admin-Key': adminKey },
    });
  }

  // Ingestion API
  async getIngestionHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.ingestionClient.get('/health');
    return data;
  }

  async ingestURL(apiKey: string, url: string, sourceSystem: string = 'generic'): Promise<IngestURLResponse> {
    // Make a direct axios call to avoid interceptor header conflicts
    const baseUrl = getServiceURL('ingestion');
    const response = await axios.post<IngestURLResponse>(
      `${baseUrl}/v1/ingest/url`,
      { url, source_system: sourceSystem },
      {
        headers: { 'X-RegEngine-API-Key': apiKey },
        timeout: 30000
      }
    );
    return response.data;
  }


  async getIngestionStatus(jobId: string): Promise<{ status: string; step?: string }> {
    const { data } = await this.ingestionClient.get(`/ingestion/status/${jobId}`);
    return data;
  }

  async ingestFile(apiKey: string, file: File, sourceSystem: string = 'generic'): Promise<IngestURLResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('source_system', sourceSystem);

    const baseUrl = getServiceURL('ingestion');
    const response = await axios.post<IngestURLResponse>(
      `${baseUrl}/v1/ingest/file`,
      formData,
      {
        headers: {
          'X-RegEngine-API-Key': apiKey,
          'Content-Type': 'multipart/form-data'
        },
        timeout: 300000 // Longer timeout for large files (5 minutes)
      }
    );
    return response.data;
  }

  async getIngestionJob(jobId: string): Promise<{ status: string; step?: string }> {
    const { data } = await this.ingestionClient.get(`/v1/ingestion/jobs/${jobId}`);
    return data;
  }

  // Discovery Queue (Phase 31)
  async getDiscoveryQueue(): Promise<any[]> {
    const { data } = await this.ingestionClient.get('/v1/ingest/discovery/queue');
    return data;
  }

  async approveDiscovery(index: number): Promise<any> {
    const { data } = await this.ingestionClient.post('/v1/ingest/discovery/approve', null, {
      params: { index }
    });
    return data;
  }

  async rejectDiscovery(index: number): Promise<any> {
    const { data } = await this.ingestionClient.post('/v1/ingest/discovery/reject', null, {
      params: { index }
    });
    return data;
  }

  async bulkApproveDiscovery(indices: number[]): Promise<any> {
    const { data } = await this.ingestionClient.post('/v1/ingest/discovery/bulk-approve', { indices });
    return data;
  }

  async bulkRejectDiscovery(indices: number[]): Promise<any> {
    const { data } = await this.ingestionClient.post('/v1/ingest/discovery/bulk-reject', { indices });
    return data;
  }

  // Opportunity API
  async getOpportunityHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.opportunityClient.get('/health');
    return data;
  }

  async getArbitrageOpportunities(params: {
    j1?: string;
    j2?: string;
    concept?: string;
    rel_delta?: number;
    limit?: number;
    since?: string;
  }): Promise<OpportunityArbitrage[]> {
    const { data } = await this.opportunityClient.get('/opportunities/arbitrage', { params });
    return data.items || [];
  }

  async getComplianceGaps(params: {
    j1?: string;
    j2?: string;
    limit?: number;
  }): Promise<ComplianceGap[]> {
    const { data } = await this.opportunityClient.get('/opportunities/gaps', { params });
    return data.items || [];
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
    const { data } = await this.complianceClient.get(`/checklists/${checklistId}`);
    return data;
  }

  async validateConfig(request: ValidationRequest): Promise<ValidationResult> {
    const { data } = await this.complianceClient.post('/validate', request);
    return data;
  }

  async getDocumentAnalysis(documentId: string, apiKey: string): Promise<AnalysisSummary> {
    const { data } = await this.complianceClient.get(`/documents/${documentId}/analysis`, {
      headers: { 'X-RegEngine-API-Key': apiKey }
    });
    return data;
  }

  async getIndustries(): Promise<Industry[]> {
    const { data } = await this.complianceClient.get('/industries');
    // API returns { industries: [...], total: X } - extract the array
    return data.industries || data || [];
  }

  // Graph API - Labels
  async initializeLabelBatch(
    request: LabelBatchInitRequest,
    tenantId?: string
  ): Promise<LabelBatchInitResponse> {
    const headers = tenantId ? { 'X-Tenant-ID': tenantId } : {};
    const { data } = await this.graphClient.post('/v1/labels/batch/init', request, { headers });
    return data;
  }

  async getLabelsHealth(): Promise<HealthCheckResponse> {
    const { data } = await this.graphClient.get('/v1/labels/health');
    return data;
  }

  async logTraceabilityEvent(request: TraceabilityEventRequest): Promise<TraceabilityEventResponse> {
    const { data } = await this.graphClient.post('/api/v1/fsma/traceability/event', request);
    return data;
  }

  async createTenant(adminKey: string, name: string): Promise<TenantResponse> {
    const { data } = await this.adminClient.post(
      '/v1/admin/tenants',
      { name },
      { headers: { 'X-Admin-Key': adminKey } },
    );
    return data;
  }

  // Review Workflow
  async getReviewItems(adminKey: string, status: string = 'PENDING'): Promise<ReviewItem[]> {
    // Call Admin API directly
    const { data } = await this.adminClient.get('/v1/review/items', {
      params: { status },
      headers: { 'X-Admin-Key': adminKey }
    });

    // The backend returns: review_id, text_raw, extraction
    // We map to the frontend expected format here if the backend differs
    return (data || []).map((item: any) => ({
      id: item.review_id || item.id,
      source_text: item.text_raw || item.source_text,
      extracted_data: item.extraction || item.extracted_data,
      status: item.status
    }));
  }

  async approveReviewItem(adminKey: string, itemId: string): Promise<void> {
    await this.adminClient.post(`/v1/review/${itemId}/approve`, {}, {
      headers: { 'X-Admin-Key': adminKey }
    });
  }

  async rejectReviewItem(adminKey: string, itemId: string): Promise<void> {
    await this.adminClient.post(`/v1/review/${itemId}/reject`, {}, {
      headers: { 'X-Admin-Key': adminKey }
    });
  }

  // Auth API
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await this.adminClient.post('/auth/login', { email, password });
    if (data.access_token) {
      this.setAccessToken(data.access_token);
      this.setUser(data.user);
      if (data.tenant_id) {
        this.setCurrentTenant(data.tenant_id);
      }
    }
    return data;
  }

  async getMe(): Promise<User> {
    const { data } = await this.adminClient.get('/auth/me');
    return data;
  }


  async checkPermission(permission: string, authorized: boolean = true): Promise<boolean> {
    try {
      await this.adminClient.get(`/auth/check-permission?authorized=${authorized}`);
      return true;
    } catch (e) {
      return false;
    }
  }

  // --- User Management ---

  async getUsers(): Promise<User[]> {
    const { data } = await this.adminClient.get<User[]>('/v1/admin/users');
    return data;
  }

  async updateUserRole(userId: string, roleId: string): Promise<void> {
    await this.adminClient.patch(`/v1/admin/users/${userId}/role`, { role_id: roleId });
  }

  async deactivateUser(userId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/users/${userId}/deactivate`);
  }

  async reactivateUser(userId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/users/${userId}/reactivate`);
  }

  async getRoles(): Promise<Role[]> {
    const { data } = await this.adminClient.get<Role[]>('/v1/admin/roles');
    return data;
  }

  // --- Invites ---


  async getInvites(): Promise<Invite[]> {
    const { data } = await this.adminClient.get<Invite[]>('/v1/admin/invites');
    return data;
  }

  async createInvite(invite: InviteCreate): Promise<Invite> {
    const { data } = await this.adminClient.post<Invite>('/v1/admin/invites', invite);
    return data;
  }

  async revokeInvite(inviteId: string): Promise<void> {
    await this.adminClient.post(`/v1/admin/invites/${inviteId}/revoke`);
  }

  async acceptInvite(data: AcceptInviteRequest): Promise<void> {
    await this.adminClient.post('/v1/auth/accept-invite', data);
  }

  async getFTLCategories(): Promise<FTLCategory[]> {
    const { data } = await this.adminClient.get<{ categories: FTLCategory[] }>('/v1/supplier/ftl-categories');
    return data.categories || [];
  }

  async createSupplierFacility(request: SupplierFacilityCreateRequest): Promise<SupplierFacility> {
    const { data } = await this.adminClient.post<SupplierFacility>('/v1/supplier/facilities', request);
    return data;
  }

  async setFacilityFTLCategories(
    facilityId: string,
    request: FacilityFTLScopingRequest,
  ): Promise<FacilityFTLScopingResponse> {
    const { data } = await this.adminClient.put<FacilityFTLScopingResponse>(
      `/v1/supplier/facilities/${facilityId}/ftl-categories`,
      request,
    );
    return data;
  }

  async getFacilityRequiredCTEs(facilityId: string): Promise<FacilityFTLScopingResponse> {
    const { data } = await this.adminClient.get<FacilityFTLScopingResponse>(
      `/v1/supplier/facilities/${facilityId}/required-ctes`,
    );
    return data;
  }

  async submitSupplierCTEEvent(
    facilityId: string,
    request: SupplierCTEEventCreateRequest,
  ): Promise<SupplierCTEEventResponse> {
    const { data } = await this.adminClient.post<SupplierCTEEventResponse>(
      `/v1/supplier/facilities/${facilityId}/cte-events`,
      request,
    );
    return data;
  }

  async createSupplierTLC(request: SupplierTLCUpsertRequest): Promise<SupplierTLC> {
    const { data } = await this.adminClient.post<SupplierTLC>('/v1/supplier/tlcs', request);
    return data;
  }

  async listSupplierTLCs(facilityId?: string): Promise<SupplierTLC[]> {
    const { data } = await this.adminClient.get<SupplierTLC[]>('/v1/supplier/tlcs', {
      params: facilityId ? { facility_id: facilityId } : undefined,
    });
    return data || [];
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

  async getSupplierFDAExportPreview(
    facilityId?: string,
    limit: number = 25,
  ): Promise<SupplierFDAExportPreviewResponse> {
    const { data } = await this.adminClient.get<SupplierFDAExportPreviewResponse>('/v1/supplier/export/fda-records/preview', {
      params: {
        ...(facilityId ? { facility_id: facilityId } : {}),
        limit,
      },
    });
    return data;
  }

  async downloadSupplierFDARecords(
    format: 'csv' | 'xlsx',
    facilityId?: string,
  ): Promise<{ blob: Blob; filename: string; recordCount: number }> {
    const response = await this.adminClient.get('/v1/supplier/export/fda-records', {
      params: {
        format,
        ...(facilityId ? { facility_id: facilityId } : {}),
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

  async resetSupplierDemoData(): Promise<SupplierDemoResetResponse> {
    const { data } = await this.adminClient.post<SupplierDemoResetResponse>('/v1/supplier/demo/reset', {});
    return data;
  }

  async trackSupplierFunnelEvent(request: SupplierFunnelEventRequest): Promise<SupplierFunnelEventResponse> {
    const { data } = await this.adminClient.post<SupplierFunnelEventResponse>('/v1/supplier/funnel-events', request);
    return data;
  }

  async getSupplierSocialProof(): Promise<SupplierSocialProofResponse> {
    const { data } = await this.adminClient.get<SupplierSocialProofResponse>('/v1/supplier/social-proof');
    return data;
  }

  async getSupplierFunnelSummary(): Promise<SupplierFunnelSummaryResponse> {
    const { data } = await this.adminClient.get<SupplierFunnelSummaryResponse>('/v1/supplier/funnel-summary');
    return data;
  }

  async parseSupplierBulkUpload(file: File): Promise<SupplierBulkUploadParseResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await this.adminClient.post<SupplierBulkUploadParseResponse>(
      '/v1/supplier/bulk-upload/parse',
      formData,
      {
        timeout: 180000,
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
        timeout: 120000,
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
        timeout: 180000,
      },
    );
    return data;
  }

  async getSupplierBulkUploadStatus(sessionId: string): Promise<SupplierBulkUploadStatusResponse> {
    const { data } = await this.adminClient.get<SupplierBulkUploadStatusResponse>(
      `/v1/supplier/bulk-upload/status/${sessionId}`,
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
}

export const apiClient = new APIClient();
