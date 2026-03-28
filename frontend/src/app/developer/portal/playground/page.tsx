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
    <div style={{ minHeight: '100vh', background: 'var(--re-bg-primary)', color: 'var(--re-text-primary)' }}>
      <div style={{ maxWidth: '1400px', margin: '0 auto', padding: 'clamp(1.5rem, 5vw, 40px) clamp(1rem, 4vw, 32px)' }}>
        {/* Header */}
        <div style={{ marginBottom: 'clamp(1rem, 4vw, 32px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <Terminal size={28} style={{ color: 'var(--re-brand)' }} />
            <h1 style={{ fontSize: '28px', fontWeight: '600', margin: 0 }}>API Playground</h1>
          </div>
          <p style={{ color: 'var(--re-text-muted)', margin: '0', fontSize: '14px' }}>
            Test live endpoints with your API key — responses are real.
          </p>
        </div>

        {/* Main Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left Panel: Request */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Endpoint Selector */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Select Endpoint
              </label>
              <select
                value={selectedEndpoint.id}
                onChange={(e) => {
                  const ep = ENDPOINTS.find(x => x.id === e.target.value);
                  if (ep) handleEndpointChange(ep);
                }}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  fontSize: '14px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  color: 'var(--re-text-primary)',
                  borderRadius: '6px',
                  fontFamily: 'monospace'
                }}
              >
                {ENDPOINTS.map(ep => (
                  <option key={ep.id} value={ep.id}>{ep.method} {ep.path}</option>
                ))}
              </select>
              <p style={{ fontSize: '12px', color: 'var(--re-text-muted)', marginTop: '6px', margin: '6px 0 0 0' }}>
                {selectedEndpoint.description}
              </p>
            </div>

            {/* API Key Input */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                API Key
              </label>
              <input
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="rge_dev_..."
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  fontSize: '14px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  color: 'var(--re-text-primary)',
                  borderRadius: '6px',
                  fontFamily: 'monospace'
                }}
              />
            </div>

            {/* Tenant ID */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Tenant ID
              </label>
              <input
                type="text"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="your-tenant-uuid"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  fontSize: '14px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  color: 'var(--re-text-primary)',
                  borderRadius: '6px',
                  fontFamily: 'monospace'
                }}
              />
            </div>

            {/* Path Params */}
            {selectedEndpoint.pathParams && selectedEndpoint.pathParams.filter(p => p !== 'tenant_id').length > 0 && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                  Path Parameters
                </label>
                {selectedEndpoint.pathParams.filter(p => p !== 'tenant_id').map(param => (
                  <div key={param} style={{ marginBottom: '8px' }}>
                    <label style={{ display: 'block', fontSize: '11px', color: 'var(--re-text-muted)', marginBottom: '4px', fontFamily: 'monospace' }}>
                      {'{' + param + '}'}
                    </label>
                    <input
                      type="text"
                      value={pathParamValues[param] || ''}
                      onChange={(e) => setPathParamValues(prev => ({ ...prev, [param]: e.target.value }))}
                      placeholder={param === 'cte_type' ? 'receiving' : param}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        fontSize: '13px',
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)',
                        color: 'var(--re-text-primary)',
                        borderRadius: '6px',
                        fontFamily: 'monospace'
                      }}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Query Params */}
            {selectedEndpoint.queryParams && selectedEndpoint.queryParams.filter(p => p.key !== 'tenant_id').length > 0 && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                  Query Parameters
                </label>
                {selectedEndpoint.queryParams.filter(p => p.key !== 'tenant_id').map(param => (
                  <div key={param.key} style={{ marginBottom: '8px' }}>
                    <label style={{ display: 'block', fontSize: '11px', color: 'var(--re-text-muted)', marginBottom: '4px', fontFamily: 'monospace' }}>
                      {param.key}
                    </label>
                    <input
                      type="text"
                      value={queryParamValues[param.key] || ''}
                      onChange={(e) => setQueryParamValues(prev => ({ ...prev, [param.key]: e.target.value }))}
                      placeholder={param.placeholder}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        fontSize: '13px',
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)',
                        color: 'var(--re-text-primary)',
                        borderRadius: '6px',
                        fontFamily: 'monospace'
                      }}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Request Headers */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Request Headers
              </label>
              <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '6px', padding: '12px', fontSize: '12px', fontFamily: 'monospace', color: 'var(--re-text-muted)' }}>
                <div>X-RegEngine-API-Key: {apiKey}</div>
                {tenantId && <div>X-Tenant-ID: {tenantId}</div>}
                {selectedEndpoint.method === 'POST' && <div>Content-Type: application/json</div>}
              </div>
            </div>

            {/* Request Body */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Request Body
              </label>
              <textarea
                value={requestBody}
                onChange={(e) => setRequestBody(e.target.value)}
                disabled={selectedEndpoint.method === 'GET'}
                style={{
                  width: '100%',
                  minHeight: '200px',
                  padding: '12px',
                  fontSize: '12px',
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  color: 'var(--re-text-primary)',
                  borderRadius: '6px',
                  fontFamily: 'monospace',
                  resize: 'vertical',
                  opacity: selectedEndpoint.method === 'GET' ? 0.5 : 1
                }}
              />
            </div>

            {/* Send Button */}
            <Button
              onClick={sendRequest}
              disabled={loading || !apiKey}
              style={{
                width: '100%',
                padding: '12px',
                background: 'var(--re-brand)',
                color: 'white',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                fontSize: '14px',
                fontWeight: '600',
                borderRadius: '6px',
                border: 'none',
                cursor: loading ? 'wait' : 'pointer',
                opacity: loading || !apiKey ? 0.6 : 1
              }}
            >
              {loading ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={16} />}
              {loading ? 'Sending...' : 'Send Request'}
            </Button>
          </div>

          {/* Right Panel: Response */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Response
              </label>

              {!response && !loading && !error && (
                <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '6px', padding: '24px', textAlign: 'center', color: 'var(--re-text-disabled)' }}>
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
                <div style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '6px', padding: '16px', color: '#ef4444' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <AlertTriangle size={16} />
                    <span style={{ fontWeight: '600', fontSize: '13px' }}>Request Failed</span>
                    {duration > 0 && (
                      <span style={{ fontSize: '12px', color: 'var(--re-text-muted)', marginLeft: 'auto' }}>
                        {duration}ms
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '12px', fontFamily: 'monospace', margin: 0, color: '#fca5a5' }}>
                    {error}
                  </p>
                </div>
              )}

              {response && !loading && (
                <>
                  <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '6px 6px 0 0', padding: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Badge style={{
                        background: statusColor(response.status).bg,
                        color: statusColor(response.status).text,
                        fontSize: '11px',
                        fontWeight: '600',
                        padding: '4px 8px',
                      }}>
                        {response.status} {response.statusText}
                      </Badge>
                      <span style={{ fontSize: '12px', color: 'var(--re-text-muted)' }}>
                        {duration}ms
                      </span>
                    </div>
                    <Button
                      onClick={copyResponse}
                      style={{
                        padding: '6px 12px',
                        background: 'rgba(255,255,255,0.06)',
                        border: '1px solid rgba(255,255,255,0.06)',
                        color: 'var(--re-text-primary)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '12px',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      {copiedResponse ? <Check size={14} /> : <Copy size={14} />}
                      {copiedResponse ? 'Copied' : 'Copy'}
                    </Button>
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '0 0 6px 6px', padding: '16px', minHeight: '300px', maxHeight: '500px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '12px', color: 'var(--re-text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
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
