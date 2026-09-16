'use client';

import { useState, useEffect } from 'react';
import { Play, Loader2, Copy, Check, AlertTriangle, FlaskConical } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { fieldControlClasses } from '@/components/ui/field-control';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { PageHeader } from '@/components/layout/page-header';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

// ---------------------------------------------------------------------------
// Demo / sandbox mock responses
// ---------------------------------------------------------------------------
const DEMO_RESPONSES: Record<string, { status: number; statusText: string; body: unknown }> = {
  'webhook-ingest': {
    status: 200,
    statusText: 'OK',
    body: {
      success: true,
      event_id: 'evt_demo_a1b2c3d4e5f6',
      hash: 'sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      received_at: new Date().toISOString(),
      message: 'Event ingested successfully (demo)',
    },
  },
  'fda-export': {
    status: 200,
    statusText: 'OK',
    body: {
      events: [
        {
          event_id: 'evt_demo_001',
          cte_type: 'receiving',
          traceability_lot_code: 'LOT-2026-001',
          product_description: 'Romaine Lettuce',
          quantity: 500,
          unit_of_measure: 'cases',
          location: 'Distribution Center A',
          timestamp: '2026-03-27T14:30:00Z',
        },
        {
          event_id: 'evt_demo_002',
          cte_type: 'shipping',
          traceability_lot_code: 'LOT-2026-002',
          product_description: 'Baby Spinach',
          quantity: 250,
          unit_of_measure: 'cases',
          location: 'Farm B',
          timestamp: '2026-03-26T09:15:00Z',
        },
        {
          event_id: 'evt_demo_003',
          cte_type: 'transformation',
          traceability_lot_code: 'LOT-2026-003',
          product_description: 'Mixed Salad Kit',
          quantity: 1000,
          unit_of_measure: 'units',
          location: 'Processing Facility C',
          timestamp: '2026-03-25T16:45:00Z',
        },
      ],
      total: 3,
      tenant_id: 'demo-tenant',
    },
  },
  'fda-export-all': {
    status: 200,
    statusText: 'OK',
    body: {
      export_job_id: 'exp_demo_7g8h9i0j',
      status: 'completed',
      format: 'json',
      record_count: 3,
      tenant_id: 'demo-tenant',
      created_at: new Date().toISOString(),
    },
  },
  'compliance-score': {
    status: 200,
    statusText: 'OK',
    body: {
      tenant_id: 'demo-tenant',
      compliance_score: 87.5,
      gaps: ['traceability_coverage', 'data_quality'],
      breakdown: {
        data_completeness: 92,
        traceability_coverage: 85,
        timeliness: 88,
        data_quality: 84,
      },
      last_evaluated: new Date().toISOString(),
      recommendation: 'Improve traceability coverage for shipping CTEs — 2 readiness gaps remaining.',
    },
  },
  'chain-verify': {
    status: 200,
    statusText: 'OK',
    body: {
      verified: true,
      chain_length: 142,
      merkle_root: 'sha256:3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b',
      last_block_hash: 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      verified_at: new Date().toISOString(),
    },
  },
  'health': {
    status: 200,
    statusText: 'OK',
    body: { status: 'healthy', service: 'regengine-ingestion', version: '2.4.0', tenant_id: 'demo-tenant' },
  },
  'csv-template': {
    status: 200,
    statusText: 'OK',
    body: {
      template_url: '/templates/receiving.csv',
      cte_type: 'receiving',
      columns: ['traceability_lot_code', 'product_description', 'quantity', 'unit_of_measure', 'location', 'timestamp'],
    },
  },
  'portal-link': {
    status: 200,
    statusText: 'OK',
    body: {
      link_id: 'lnk_demo_x1y2z3',
      url: 'https://regengine.co/portal/lnk_demo_x1y2z3',
      supplier_name: 'Example Farms',
      cte_types: ['receiving', 'shipping'],
      expires_at: '2026-04-27T00:00:00Z',
    },
  },
  'merkle-root': {
    status: 200,
    statusText: 'OK',
    body: {
      merkle_root: 'sha256:3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b',
      record_count: 142,
      tenant_id: 'demo-tenant',
      computed_at: new Date().toISOString(),
    },
  },
};

interface Endpoint {
  id: string;
  path: string;
  method: 'GET' | 'POST';
  description: string;
  proxyPath: string;
  sampleBody?: Record<string, unknown>;
  pathParams?: string[];
  queryParams?: { key: string; placeholder: string }[];
}

const ENDPOINTS: Endpoint[] = [
  {
    id: 'webhook-ingest',
    path: '/api/v1/webhooks/ingest',
    method: 'POST',
    description: 'Ingest webhook event data (CTE events)',
    proxyPath: '/api/ingestion/api/v1/webhooks/ingest',
    sampleBody: {
      events: [{
        cte_type: 'receiving',
        traceability_lot_code: 'LOT-2026-001',
        product_description: 'Romaine Lettuce',
        quantity: 500,
        unit_of_measure: 'cases',
      }],
    },
  },
  {
    id: 'fda-export',
    path: '/api/v1/fda/export',
    method: 'GET',
    description: 'Export FDA data for a specific TLC',
    proxyPath: '/api/ingestion/api/v1/fda/export',
    queryParams: [
      { key: 'tlc', placeholder: 'LOT-2026-001' },
      { key: 'tenant_id', placeholder: 'your-tenant-uuid' },
    ],
  },
  {
    id: 'fda-export-all',
    path: '/api/v1/fda/export/all',
    method: 'GET',
    description: 'Full tenant FDA export',
    proxyPath: '/api/ingestion/api/v1/fda/export/all',
    queryParams: [
      { key: 'tenant_id', placeholder: 'your-tenant-uuid' },
    ],
  },
  {
    id: 'compliance-score',
    path: '/api/v1/compliance/score/{tenant_id}',
    method: 'GET',
    description: 'Get FSMA 204 compliance score',
    proxyPath: '/api/ingestion/api/v1/compliance/score',
    pathParams: ['tenant_id'],
  },
  {
    id: 'chain-verify',
    path: '/api/v1/chain/verify-all',
    method: 'POST',
    description: 'Verify hash-chain integrity',
    proxyPath: '/api/ingestion/api/v1/chain/verify-all',
    sampleBody: {},
  },
  {
    id: 'health',
    path: '/api/v1/monitoring/health/{tenant_id}',
    method: 'GET',
    description: 'Health check for tenant',
    proxyPath: '/api/ingestion/api/v1/monitoring/health',
    pathParams: ['tenant_id'],
  },
  {
    id: 'csv-template',
    path: '/api/v1/templates/{cte_type}',
    method: 'GET',
    description: 'Download CSV template for a CTE type',
    proxyPath: '/api/ingestion/api/v1/templates',
    pathParams: ['cte_type'],
  },
  {
    id: 'portal-link',
    path: '/api/v1/portal/links',
    method: 'POST',
    description: 'Create a supplier portal link',
    proxyPath: '/api/ingestion/api/v1/portal/links',
    sampleBody: {
      supplier_name: 'Example Farms',
      cte_types: ['receiving', 'shipping'],
      expires_in_days: 30,
    },
  },
  {
    id: 'merkle-root',
    path: '/api/v1/fda/export/merkle-root',
    method: 'GET',
    description: 'Get Merkle root hash for tenant data',
    proxyPath: '/api/ingestion/api/v1/fda/export/merkle-root',
    queryParams: [
      { key: 'tenant_id', placeholder: 'your-tenant-uuid' },
    ],
  },
];

interface ApiResponse {
  status: number;
  statusText: string;
  body: unknown;
}

export default function APIPlayground() {
  const { isAuthenticated } = useAuth();
  const isGuest = !isAuthenticated;

  const [demoMode, setDemoMode] = useState(false);
  const [selectedEndpoint, setSelectedEndpoint] = useState(ENDPOINTS[0]);
  const [apiKey, setApiKey] = useState('rge_live_');
  const [tenantId, setTenantId] = useState('');
  const [pathParamValues, setPathParamValues] = useState<Record<string, string>>({});
  const [queryParamValues, setQueryParamValues] = useState<Record<string, string>>({});
  const [requestBody, setRequestBody] = useState(
    JSON.stringify(ENDPOINTS[0].sampleBody || {}, null, 2)
  );
  const [response, setResponse] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [duration, setDuration] = useState(0);
  const [copiedResponse, setCopiedResponse] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-enable demo mode for unauthenticated users
  useEffect(() => {
    if (isGuest) {
      setDemoMode(true);
      setApiKey('demo-key-sandbox');
      setTenantId('demo-tenant');
    }
  }, [isGuest]);

  const handleDemoToggle = (enabled: boolean) => {
    setDemoMode(enabled);
    if (enabled) {
      setApiKey('demo-key-sandbox');
      setTenantId('demo-tenant');
    } else {
      setApiKey('rge_live_');
      setTenantId('');
    }
    setResponse(null);
    setError(null);
  };

  const handleEndpointChange = (endpoint: Endpoint) => {
    setSelectedEndpoint(endpoint);
    setRequestBody(
      JSON.stringify(endpoint.sampleBody || {}, null, 2)
    );
    setResponse(null);
    setDuration(0);
    setError(null);
    setPathParamValues({});
    setQueryParamValues({});
  };

  const buildRequestUrl = (): string => {
    let url = selectedEndpoint.proxyPath;

    // Append path params (e.g., /compliance/score/{tenant_id} -> /compliance/score/abc123)
    if (selectedEndpoint.pathParams) {
      for (const param of selectedEndpoint.pathParams) {
        const value = pathParamValues[param] || tenantId || '';
        if (value) {
          url = `${url}/${encodeURIComponent(value)}`;
        }
      }
    }

    // Append query params
    const qp = new URLSearchParams();
    if (selectedEndpoint.queryParams) {
      for (const param of selectedEndpoint.queryParams) {
        const value = queryParamValues[param.key] || (param.key === 'tenant_id' ? tenantId : '');
        if (value) {
          qp.set(param.key, value);
        }
      }
    }
    const qs = qp.toString();
    return qs ? `${url}?${qs}` : url;
  };

  const sendDemoRequest = async () => {
    setLoading(true);
    setError(null);
    setResponse(null);

    // Simulate network latency
    await new Promise((resolve) => setTimeout(resolve, 500));

    const mock = DEMO_RESPONSES[selectedEndpoint.id];
    setDuration(500);
    if (mock) {
      setResponse({ ...mock });
    } else {
      setResponse({
        status: 200,
        statusText: 'OK',
        body: { message: 'Demo response — no mock configured for this endpoint.' },
      });
    }
    setLoading(false);
  };

  const sendRequest = async () => {
    if (demoMode) {
      return sendDemoRequest();
    }

    setLoading(true);
    setError(null);
    setResponse(null);

    const startTime = performance.now();

    try {
      const url = buildRequestUrl();
      const headers: Record<string, string> = {
        'X-RegEngine-API-Key': apiKey,
      };

      const fetchOptions: RequestInit = {
        method: selectedEndpoint.method,
        headers,
      };

      if (selectedEndpoint.method === 'POST') {
        headers['Content-Type'] = 'application/json';
        try {
          // Validate JSON before sending
          JSON.parse(requestBody);
          fetchOptions.body = requestBody;
        } catch {
          setError('Invalid JSON in request body');
          setLoading(false);
          return;
        }
      }

      if (tenantId) {
        headers['X-Tenant-ID'] = tenantId;
      }

      // #2885 Must go through fetchWithCsrf, not raw fetch. Playground requests
      // hit the same-origin BFF proxy (/api/ingestion/...), so src/proxy.ts
      // applies the double-submit CSRF check to every POST. The exemption list
      // in src/lib/csrf.ts only covers the next.config.js rewrite path
      // '/api/v1/webhooks/', which does NOT prefix-match the proxied
      // '/api/ingestion/api/v1/webhooks/ingest', and the Bearer bypass never
      // applies here (we send X-RegEngine-API-Key, and a browser always
      // attaches Origin/Referer). Without X-CSRF-Token the middleware answers
      // 403 before the proxy ever runs. fetchWithCsrf adds the header from the
      // JS-readable re_csrf cookie for POST/PUT/PATCH/DELETE only.
      const res = await fetchWithCsrf(url, fetchOptions);
      const endTime = performance.now();
      setDuration(Math.round(endTime - startTime));

      let body: unknown;
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        body = await res.json();
      } else {
        const text = await res.text();
        // Try to parse as JSON anyway (some endpoints omit the header)
        try {
          body = JSON.parse(text);
        } catch {
          body = { raw_response: text, content_type: contentType };
        }
      }

      setResponse({
        status: res.status,
        statusText: res.statusText,
        body,
      });
    } catch (err) {
      const endTime = performance.now();
      setDuration(Math.round(endTime - startTime));
      const message = err instanceof Error ? err.message : 'Request failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const copyResponse = () => {
    const text = response
      ? JSON.stringify(response.body, null, 2)
      : '';
    navigator.clipboard.writeText(text);
    setCopiedResponse(true);
    setTimeout(() => setCopiedResponse(false), 2000);
  };

  // 2xx / 4xx / 5xx as the shared status vocabulary — icon plus label, never
  // colour alone (SPEC §1.6).
  const statusState = (status: number): ComplianceState => {
    if (status >= 200 && status < 300) return 'compliant';
    if (status >= 400 && status < 500) return 'at-risk';
    return 'non-compliant';
  };

  const fieldLabelClass = 'text-label text-re-text-muted';
  const monoControl = cn(fieldControlClasses, 'font-mono text-[0.8125rem]');

  return (
    <div className="space-y-4">
      <PageHeader
        title="API Playground"
        description={demoMode
          ? 'Explore API endpoints with simulated responses — no API key required.'
          : 'Test live endpoints with your API key — responses are real.'}
        className="mb-0"
      />

      {/* Demo Mode Toggle */}
      <Card padding="compact" className="flex flex-wrap items-center gap-3">
        <FlaskConical
          className={cn('h-4 w-4 shrink-0', demoMode ? 'text-re-text-primary' : 'text-re-text-muted')}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        <span className="text-ui font-medium text-re-text-primary">
          Demo Mode
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={demoMode}
          aria-label="Demo Mode"
          onClick={() => handleDemoToggle(!demoMode)}
          disabled={isGuest}
          title={isGuest ? 'Live mode requires an API key provisioned by the RegEngine team' : (demoMode ? 'Switch to live API' : 'Switch to demo sandbox')}
          className={cn(
            'relative h-6 w-11 shrink-0 rounded-full border transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none',
            demoMode
              ? 'border-transparent bg-re-text-primary'
              : 'border-re-border-strong bg-re-surface-inset',
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              'absolute top-0.5 h-5 w-5 rounded-full transition-[left] duration-120 motion-reduce:transition-none',
              demoMode ? 'left-[1.375rem] bg-re-surface-card' : 'left-0.5 bg-re-text-muted',
            )}
          />
        </button>
        {isGuest && (
          <span className="text-small italic text-re-text-tertiary">
            Live mode requires a provisioned API key
          </span>
        )}
      </Card>

      {/* Demo Mode Banner */}
      {demoMode && (
        <Callout tone="info" icon={FlaskConical}>
          <strong className="font-medium text-re-text-primary">Demo Mode</strong> — responses are simulated.{' '}
          {isGuest && (
            <>
              <a href="/signup" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">
                Create a developer account
              </a>
              {' '}— live API keys are provisioned during onboarding.
            </>
          )}
          {!isGuest && 'Toggle off to send live requests.'}
        </Callout>
      )}

      {/* Main Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left Panel: Request */}
        <div className="flex min-w-0 flex-col gap-4">
          {/* Endpoint Selector */}
          <div>
            <Field label="Select Endpoint" htmlFor="playground-endpoint" hint={selectedEndpoint.description}>
              <select
                value={selectedEndpoint.id}
                onChange={(e) => {
                  const ep = ENDPOINTS.find(x => x.id === e.target.value);
                  if (ep) handleEndpointChange(ep);
                }}
                className={cn(monoControl, 'appearance-none pr-8')}
              >
                {ENDPOINTS.map(ep => (
                  <option key={ep.id} value={ep.id}>{ep.method} {ep.path}</option>
                ))}
              </select>
            </Field>
          </div>

          {/* API Key Input */}
          <Field label="API Key" htmlFor="playground-api-key">
            <input
              type="text"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="rge_live_..."
              className={monoControl}
            />
          </Field>

          {/* Tenant ID */}
          <Field label="Tenant ID" htmlFor="playground-tenant-id">
            <input
              type="text"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="your-tenant-uuid"
              className={monoControl}
            />
          </Field>

          {/* Path Params */}
          {selectedEndpoint.pathParams && selectedEndpoint.pathParams.filter(p => p !== 'tenant_id').length > 0 && (
            <div className="space-y-2">
              <p className={fieldLabelClass}>
                Path Parameters
              </p>
              {selectedEndpoint.pathParams.filter(p => p !== 'tenant_id').map(param => (
                <Field key={param} label={'{' + param + '}'} htmlFor={`playground-path-${param}`}>
                  <input
                    type="text"
                    value={pathParamValues[param] || ''}
                    onChange={(e) => setPathParamValues(prev => ({ ...prev, [param]: e.target.value }))}
                    placeholder={param === 'cte_type' ? 'receiving' : param}
                    className={monoControl}
                  />
                </Field>
              ))}
            </div>
          )}

          {/* Query Params */}
          {selectedEndpoint.queryParams && selectedEndpoint.queryParams.filter(p => p.key !== 'tenant_id').length > 0 && (
            <div className="space-y-2">
              <p className={fieldLabelClass}>
                Query Parameters
              </p>
              {selectedEndpoint.queryParams.filter(p => p.key !== 'tenant_id').map(param => (
                <Field key={param.key} label={param.key} htmlFor={`playground-query-${param.key}`}>
                  <input
                    type="text"
                    value={queryParamValues[param.key] || ''}
                    onChange={(e) => setQueryParamValues(prev => ({ ...prev, [param.key]: e.target.value }))}
                    placeholder={param.placeholder}
                    className={monoControl}
                  />
                </Field>
              ))}
            </div>
          )}

          {/* Request Headers */}
          <div className="space-y-1.5">
            <p className={fieldLabelClass}>
              Request Headers
            </p>
            <div className="overflow-x-auto rounded-md border border-re-border bg-re-surface-inset p-3 font-mono text-[0.8125rem] text-re-text-secondary">
              <div className="break-all">X-RegEngine-API-Key: {apiKey}</div>
              {tenantId && <div className="break-all">X-Tenant-ID: {tenantId}</div>}
              {selectedEndpoint.method === 'POST' && <div>Content-Type: application/json</div>}
            </div>
          </div>

          {/* Request Body */}
          <Field label="Request Body" htmlFor="playground-request-body">
            <textarea
              value={requestBody}
              onChange={(e) => setRequestBody(e.target.value)}
              disabled={selectedEndpoint.method === 'GET'}
              className={cn(monoControl, 'h-auto min-h-[200px] resize-y py-3 leading-relaxed')}
            />
          </Field>

          {/* Send Button */}
          <Button
            onClick={sendRequest}
            disabled={loading || !apiKey}
            size="lg"
            className="w-full"
            leadingIcon={loading
              ? <Loader2 className="animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
              : <Play strokeWidth={1.75} aria-hidden="true" />}
          >
            {loading ? 'Sending...' : (demoMode ? 'Send Demo Request' : 'Send Request')}
          </Button>
        </div>

        {/* Right Panel: Response */}
        <div className="flex min-w-0 flex-col gap-4">
          <div className="space-y-2">
            <p className={fieldLabelClass}>
              Response
            </p>

            {demoMode && response && !loading && (
              <Badge tone="neutral" className="h-auto whitespace-normal py-1 text-left">
                <FlaskConical className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                Sandbox response — does not call your account
              </Badge>
            )}

            {!response && !loading && !error && (
              <EmptyState title="Send a request to see the response" size="sm" />
            )}

            {loading && (
              <Card className="flex min-h-[300px] items-center justify-center gap-2 p-6 text-center text-ui text-re-text-tertiary">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
                <span>Processing request...</span>
              </Card>
            )}

            {error && !loading && (
              <Callout
                tone="danger"
                role="alert"
                icon={AlertTriangle}
                title={
                  <span className="flex items-center gap-2">
                    Request Failed
                    {duration > 0 && (
                      <span className="ml-auto text-small font-normal tabular-nums text-re-text-tertiary">
                        {duration}ms
                      </span>
                    )}
                  </span>
                }
              >
                <p className="m-0 break-words font-mono text-[0.8125rem] text-re-text-secondary">
                  {error}
                </p>
              </Callout>
            )}

            {response && !loading && (
              <div className="overflow-hidden rounded-lg border border-re-border">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-re-border-subtle bg-re-surface-card px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      state={statusState(response.status)}
                      label={`${response.status} ${response.statusText}`}
                      size="sm"
                      mono
                    />
                    <span className="text-small tabular-nums text-re-text-tertiary">
                      {duration}ms
                    </span>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={copyResponse}
                    leadingIcon={copiedResponse
                      ? <Check strokeWidth={1.75} aria-hidden="true" />
                      : <Copy strokeWidth={1.75} aria-hidden="true" />}
                  >
                    {copiedResponse ? 'Copied' : 'Copy'}
                  </Button>
                </div>
                <div className="max-h-[500px] min-h-[300px] overflow-y-auto whitespace-pre-wrap break-words bg-re-surface-inset p-4 font-mono text-[0.8125rem] text-re-text-secondary">
                  {JSON.stringify(response.body, null, 2)}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
