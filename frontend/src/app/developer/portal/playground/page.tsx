'use client';

import { useState } from 'react';
import { Terminal, Play, Loader2, Copy, Check, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

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
    description: 'Verify blockchain chain integrity',
    proxyPath: '/api/ingestion/api/v1/chain/verify-all',
    sampleBody: {},
  },
  {
    id: 'sla-dashboard',
    path: '/api/v1/sla/dashboard/{tenant_id}',
    method: 'GET',
    description: 'SLA dashboard metrics',
    proxyPath: '/api/ingestion/api/v1/sla/dashboard',
    pathParams: ['tenant_id'],
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
      supplier_name: 'Acme Farms',
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
  const [selectedEndpoint, setSelectedEndpoint] = useState(ENDPOINTS[0]);
  const [apiKey, setApiKey] = useState('rge_dev_');
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

  const sendRequest = async () => {
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

      const res = await fetch(url, fetchOptions);
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

  const statusColor = (status: number) => {
    if (status >= 200 && status < 300) return { bg: 'rgba(16,185,129,0.2)', text: '#10b981' };
    if (status >= 400 && status < 500) return { bg: 'rgba(245,158,11,0.2)', text: '#f59e0b' };
    return { bg: 'rgba(239,68,68,0.2)', text: '#ef4444' };
  };

  return (
    <div className="min-h-screen bg-[var(--re-bg-primary)] text-[var(--re-text-primary)]">
      <div className="max-w-[1400px] mx-auto px-[clamp(1rem,4vw,32px)] py-[clamp(1.5rem,5vw,40px)]">
        {/* Header */}
        <div className="mb-[clamp(1rem,4vw,32px)]">
          <div className="flex items-center gap-3 mb-2">
            <Terminal size={28} className="text-[var(--re-brand)]" />
            <h1 className="text-[28px] font-semibold m-0">API Playground</h1>
          </div>
          <p className="text-[var(--re-text-muted)] m-0 text-sm">
            Test live endpoints with your API key — responses are real.
          </p>
        </div>

        {/* Main Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left Panel: Request */}
          <div className="flex flex-col gap-4">
            {/* Endpoint Selector */}
            <div>
              <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                Select Endpoint
              </label>
              <select
                value={selectedEndpoint.id}
                onChange={(e) => {
                  const ep = ENDPOINTS.find(x => x.id === e.target.value);
                  if (ep) handleEndpointChange(ep);
                }}
                className="w-full px-3 py-2.5 text-sm bg-white/[0.02] border border-white/[0.06] text-[var(--re-text-primary)] rounded-md font-mono"
              >
                {ENDPOINTS.map(ep => (
                  <option key={ep.id} value={ep.id}>{ep.method} {ep.path}</option>
                ))}
              </select>
              <p className="text-xs text-[var(--re-text-muted)] mt-1.5 mb-0">
                {selectedEndpoint.description}
              </p>
            </div>

            {/* API Key Input */}
            <div>
              <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                API Key
              </label>
              <input
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="rge_dev_..."
                className="w-full px-3 py-2.5 text-sm bg-white/[0.02] border border-white/[0.06] text-[var(--re-text-primary)] rounded-md font-mono"
              />
            </div>

            {/* Tenant ID */}
            <div>
              <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                Tenant ID
              </label>
              <input
                type="text"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="your-tenant-uuid"
                className="w-full px-3 py-2.5 text-sm bg-white/[0.02] border border-white/[0.06] text-[var(--re-text-primary)] rounded-md font-mono"
              />
            </div>

            {/* Path Params */}
            {selectedEndpoint.pathParams && selectedEndpoint.pathParams.filter(p => p !== 'tenant_id').length > 0 && (
              <div>
                <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                  Path Parameters
                </label>
                {selectedEndpoint.pathParams.filter(p => p !== 'tenant_id').map(param => (
                  <div key={param} className="mb-2">
                    <label className="block text-[11px] text-[var(--re-text-muted)] mb-1 font-mono">
                      {'{' + param + '}'}
                    </label>
                    <input
                      type="text"
                      value={pathParamValues[param] || ''}
                      onChange={(e) => setPathParamValues(prev => ({ ...prev, [param]: e.target.value }))}
                      placeholder={param === 'cte_type' ? 'receiving' : param}
                      className="w-full px-3 py-2 text-[13px] bg-white/[0.02] border border-white/[0.06] text-[var(--re-text-primary)] rounded-md font-mono"
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Query Params */}
            {selectedEndpoint.queryParams && selectedEndpoint.queryParams.filter(p => p.key !== 'tenant_id').length > 0 && (
              <div>
                <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                  Query Parameters
                </label>
                {selectedEndpoint.queryParams.filter(p => p.key !== 'tenant_id').map(param => (
                  <div key={param.key} className="mb-2">
                    <label className="block text-[11px] text-[var(--re-text-muted)] mb-1 font-mono">
                      {param.key}
                    </label>
                    <input
                      type="text"
                      value={queryParamValues[param.key] || ''}
                      onChange={(e) => setQueryParamValues(prev => ({ ...prev, [param.key]: e.target.value }))}
                      placeholder={param.placeholder}
                      className="w-full px-3 py-2 text-[13px] bg-white/[0.02] border border-white/[0.06] text-[var(--re-text-primary)] rounded-md font-mono"
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Request Headers */}
            <div>
              <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                Request Headers
              </label>
              <div className="bg-black/30 border border-white/[0.06] rounded-md p-3 text-xs font-mono text-[var(--re-text-muted)]">
                <div>X-RegEngine-API-Key: {apiKey}</div>
                {tenantId && <div>X-Tenant-ID: {tenantId}</div>}
                {selectedEndpoint.method === 'POST' && <div>Content-Type: application/json</div>}
              </div>
            </div>

            {/* Request Body */}
            <div>
              <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                Request Body
              </label>
              <textarea
                value={requestBody}
                onChange={(e) => setRequestBody(e.target.value)}
                disabled={selectedEndpoint.method === 'GET'}
                className="w-full min-h-[200px] p-3 text-xs bg-black/30 border border-white/[0.06] text-[var(--re-text-primary)] rounded-md font-mono resize-y"
                style={{ opacity: selectedEndpoint.method === 'GET' ? 0.5 : 1 }}
              />
            </div>

            {/* Send Button */}
            <Button
              onClick={sendRequest}
              disabled={loading || !apiKey}
              className="w-full p-3 bg-[var(--re-brand)] text-white flex items-center justify-center gap-2 text-sm font-semibold rounded-md border-none"
              style={{
                cursor: loading ? 'wait' : 'pointer',
                opacity: loading || !apiKey ? 0.6 : 1,
              }}
            >
              {loading ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={16} />}
              {loading ? 'Sending...' : 'Send Request'}
            </Button>
          </div>

          {/* Right Panel: Response */}
          <div className="flex flex-col gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase text-[var(--re-text-muted)] mb-2">
                Response
              </label>

              {!response && !loading && !error && (
                <div className="bg-white/[0.02] border border-white/[0.06] rounded-md p-6 text-center text-[var(--re-text-disabled)]">
                  <p>Send a request to see the response</p>
                </div>
              )}

              {loading && (
                <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '6px', padding: '24px', textAlign: 'center', color: 'var(--re-text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', minHeight: '300px' }}>
                  <Loader2 size={16} style={{ animation: 'spin 1s linear infinite', color: 'var(--re-brand)' }} />
                  <span>Processing request...</span>
                </div>
              )}

              {error && !loading && (
                <div className="bg-red-500/5 border border-red-500/20 rounded-md p-4 text-[#ef4444]">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle size={16} />
                    <span className="font-semibold text-[13px]">Request Failed</span>
                    {duration > 0 && (
                      <span className="text-xs text-[var(--re-text-muted)] ml-auto">
                        {duration}ms
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono m-0 text-[#fca5a5]">
                    {error}
                  </p>
                </div>
              )}

              {response && !loading && (
                <>
                  <div className="bg-white/[0.02] border border-white/[0.06] rounded-t-md p-3 flex items-center justify-between border-b border-b-white/[0.06]">
                    <div className="flex items-center gap-2">
                      <Badge className="text-[11px] font-semibold px-2 py-1" style={{
                        background: statusColor(response.status).bg,
                        color: statusColor(response.status).text,
                      }}>
                        {response.status} {response.statusText}
                      </Badge>
                      <span className="text-xs text-[var(--re-text-muted)]">
                        {duration}ms
                      </span>
                    </div>
                    <Button
                      onClick={copyResponse}
                      className="px-3 py-1.5 bg-white/[0.06] border border-white/[0.06] text-[var(--re-text-primary)] flex items-center gap-1.5 text-xs rounded cursor-pointer"
                    >
                      {copiedResponse ? <Check size={14} /> : <Copy size={14} />}
                      {copiedResponse ? 'Copied' : 'Copy'}
                    </Button>
                  </div>
                  <div className="bg-black/30 border border-white/[0.06] rounded-b-md p-4 min-h-[300px] max-h-[500px] overflow-y-auto font-mono text-xs text-[var(--re-text-muted)] whitespace-pre-wrap break-words">
                    {JSON.stringify(response.body, null, 2)}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @media (max-width: 768px) {
          [style*="grid"] {
            grid-template-columns: 1fr !important;
          }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
