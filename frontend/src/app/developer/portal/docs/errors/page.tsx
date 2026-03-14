'use client';

import { AlertCircle, Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { CodeBlock } from '@/components/developer/CodeBlock';

export default function ErrorCodesPage() {
  return (
    <div className="space-y-8 pb-12">
      <div>
        <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--re-text-primary)' }}>
          Error Codes
        </h1>
        <p className="text-lg" style={{ color: 'var(--re-text-muted)' }}>
          Reference guide for HTTP status codes and RegEngine-specific error codes
        </p>
      </div>

      {/* HTTP Status Codes Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <AlertCircle size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            HTTP Status Codes
          </h2>
        </div>
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '8px',
          padding: '16px',
          overflowX: 'auto'
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Code</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>200</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>OK</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Request succeeded</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>201</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Created</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Resource created successfully</td>
              </tr>              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>400</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Bad Request</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Invalid request parameters</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>401</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Unauthorized</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>API key missing or invalid</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>403</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Forbidden</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Permission denied for this resource</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>404</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Not Found</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Resource not found</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>409</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Conflict</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Resource already exists</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>422</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Unprocessable Entity</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Validation failed on input data</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontWeight: '600' }}>429</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Too Many Requests</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Rate limit exceeded</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', color: 'var(--re-text-primary)', fontWeight: '600' }}>500</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>Internal Server Error</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>Server encountered an error</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>      {/* Error Response Format Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <Info size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            Error Response Format
          </h2>
        </div>
        <p style={{ color: 'var(--re-text-muted)' }}>
          All error responses follow a consistent JSON structure with error code, message, and optional details.
        </p>
        <CodeBlock snippets={[{ language: 'json', label: 'JSON', code: `{
  "error": {
    "code": "invalid_api_key",
    "message": "The provided API key is invalid or expired",
    "details": [
      {
        "field": "headers.X-RegEngine-API-Key",
        "reason": "Key format mismatch"
      }
    ]
  }
}` }]} />
      </section>

      {/* Common Error Codes Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <AlertCircle size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            Common Error Codes
          </h2>
        </div>
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '8px',
          padding: '16px',
          overflowX: 'auto'
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Error Code</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>HTTP Status</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Description</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Resolution</th>
              </tr>
            </thead>            <tbody>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>invalid_api_key</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>401</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>API key is invalid, expired, or malformed</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Verify key format and expiration in portal</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>missing_tenant_id</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>400</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>X-Tenant-ID header is required but missing</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Add X-Tenant-ID header to request</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>invalid_cte_type</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>422</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>CTE type is invalid or unsupported</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Check API docs for valid CTE types</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>duplicate_event</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>409</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Event with this ID already exists</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Use unique event IDs or retrieve existing</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>lot_code_required</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>400</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Lot code is required but missing</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Include lot_code in request body</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>rate_limit_exceeded</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>429</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Rate limit for your plan exceeded</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Retry after delay or upgrade plan</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', color: 'var(--re-text-primary)', fontFamily: 'monospace' }}>chain_integrity_error</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>422</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>Supply chain integrity check failed</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>Verify event signatures and chain history</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}