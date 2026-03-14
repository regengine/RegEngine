'use client';

import { useState } from 'react';
import { Terminal, Play, Loader2, Copy, Check } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface Endpoint {
  path: string;
  method: 'GET' | 'POST';
  description: string;
  mockResponse: Record<string, unknown>;
  requestBody?: Record<string, unknown>;
}

const ENDPOINTS: Endpoint[] = [
  {
    path: 'POST /api/v1/webhooks/ingest',
    method: 'POST',
    description: 'Ingest webhook data',
    requestBody: {
      event_type: 'lot_created',
      lot_code: 'LOT-2026-003847',
      product_name: 'Organic Spinach',
      harvest_date: '2026-03-10',
      location: { latitude: 40.7128, longitude: -74.006 }
    },
    mockResponse: {
      success: true,
      event_id: 'evt_1nK5zJ2eZvKYlo2C',
      processed_at: '2026-03-14T08:32:15Z',
      lot_code: 'LOT-2026-003847',
      status: 'ingested'
    }
  },
  {
    path: 'GET /api/v1/compliance/score/:tenant_id',
    method: 'GET',
    description: 'Get FSMA 204 compliance score',
    mockResponse: {
      tenant_id: 'tenant_example',
      compliance_score: 94.2,
      status: 'compliant',
      last_audit: '2026-03-01T14:22:00Z',
      findings: [],
      next_review: '2026-04-01'
    }
  },
  {
    path: 'POST /api/v1/recall-simulations/run',
    method: 'POST',
    description: 'Run a recall simulation',
    requestBody: {
      lot_code: 'LOT-2026-003847',
      simulation_type: 'forward_trace',
      depth_levels: 2
    },
    mockResponse: {
      simulation_id: 'sim_1nK5zJ2eZvKYlo2C',
      status: 'completed',
      lot_code: 'LOT-2026-003847',
      affected_products: 3,
      total_ctes: 47,
      execution_time_ms: 342,
      results: {
        direct_recipients: 12,
        secondary_recipients: 31,
        coverage_percentage: 98.5
      }
    }
  },
  {
    path: 'GET /api/v1/epcis/events/:id',
    method: 'GET',
    description: 'Retrieve EPCIS event details',
    mockResponse: {
      event_id: 'evt_1nK5zJ2eZvKYlo2C',
      event_type: 'ObjectEvent',
      timestamp: '2026-03-14T08:15:30Z',
      business_location: 'urn:epc:id:sgln:0614141.00001.0',
      epc_list: ['urn:epc:id:sgtin:0614141.107346.2017'],
      action: 'OBSERVE',
      disposition: 'in_transit',
      ilmd: {
        lot_number: 'LOT-2026-003847',
        expiration_date: '2026-09-14'
      }
    }
  },
  {
    path: 'POST /api/v1/qr/decode',
    method: 'POST',
    description: 'Decode QR code data',
    requestBody: {
      qr_data: '011234567890128210LOT-2026-003847'
    },
    mockResponse: {
      success: true,
      gtin: '012345678901',
      lot_code: 'LOT-2026-003847',
      product_name: 'Organic Spinach',
      gtin_url: 'https://gs1.org/gtin/012345678901'
    }
  }
];

export default function APIPlayground() {
  const [selectedEndpoint, setSelectedEndpoint] = useState(ENDPOINTS[0]);
  const [apiKey, setApiKey] = useState('rge_dev_');
  const [requestBody, setRequestBody] = useState(
    JSON.stringify(selectedEndpoint.requestBody || {}, null, 2)
  );
  const [response, setResponse] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [duration, setDuration] = useState(0);
  const [copiedResponse, setCopiedResponse] = useState(false);

  const handleEndpointChange = (endpoint: Endpoint) => {
    setSelectedEndpoint(endpoint);
    setRequestBody(
      JSON.stringify(endpoint.requestBody || {}, null, 2)
    );
    setResponse(null);
    setDuration(0);
  };

  const sendRequest = async () => {
    setLoading(true);
    const startTime = performance.now();

    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 1000));

    const endTime = performance.now();
    setDuration(Math.round(endTime - startTime));
    setResponse(selectedEndpoint.mockResponse);
    setLoading(false);
  };

  const copyResponse = () => {
    navigator.clipboard.writeText(JSON.stringify(response, null, 2));
    setCopiedResponse(true);
    setTimeout(() => setCopiedResponse(false), 2000);
  };

  const methodColor = selectedEndpoint.method === 'GET' ? '#60a5fa' : '#10b981';
  const methodBgColor = selectedEndpoint.method === 'GET' ? 'rgba(96,165,250,0.1)' : 'rgba(16,185,129,0.1)';

  return (
    <div style={{ minHeight: '100vh', background: 'var(--re-bg-primary)', color: 'var(--re-text-primary)' }}>
      <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '32px 24px' }}>
        {/* Header */}
        <div style={{ marginBottom: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <Terminal size={28} style={{ color: 'var(--re-brand)' }} />
            <h1 style={{ fontSize: '28px', fontWeight: '600', margin: 0 }}>API Playground</h1>
          </div>
          <p style={{ color: 'var(--re-text-muted)', margin: '0', fontSize: '14px' }}>
            Test endpoints with your API key — no setup required.
          </p>
        </div>

        {/* Main Layout */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', '@media (maxWidth: 768px)': { gridTemplateColumns: '1fr' } }}>
          {/* Left Panel: Request */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Endpoint Selector */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Select Endpoint
              </label>
              <select
                value={selectedEndpoint.path}
                onChange={(e) => {
                  const ep = ENDPOINTS.find(x => x.path === e.target.value);
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
                  <option key={ep.path} value={ep.path}>{ep.path}</option>
                ))}
              </select>
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

            {/* Request Headers */}
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--re-text-muted)', marginBottom: '8px' }}>
                Request Headers
              </label>
              <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '6px', padding: '12px', fontSize: '12px', fontFamily: 'monospace', color: 'var(--re-text-muted)' }}>
                <div>X-RegEngine-API-Key: {apiKey}</div>
                <div>Content-Type: application/json</div>
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

              {!response && !loading && (
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

              {response && !loading && (
                <>
                  <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '6px 6px 0 0', padding: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Badge style={{ background: 'rgba(16,185,129,0.2)', color: '#10b981', fontSize: '11px', fontWeight: '600', padding: '4px 8px' }}>
                        200 OK
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
                    {JSON.stringify(response, null, 2)}
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