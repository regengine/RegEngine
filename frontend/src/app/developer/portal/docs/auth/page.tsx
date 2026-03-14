'use client';

import { ShieldCheck, Key, AlertTriangle, Info } from 'lucide-react';
import CodeBlock from '@/components/developer/CodeBlock';

export default function AuthenticationPage() {
  return (
    <div className="space-y-8 pb-12">
      <div>
        <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--re-text-primary)' }}>
          Authentication
        </h1>
        <p className="text-lg" style={{ color: 'var(--re-text-muted)' }}>
          API key management and authentication headers for RegEngine API requests
        </p>
      </div>

      {/* API Key Header Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <ShieldCheck size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            API Key Header
          </h2>
        </div>
        <p style={{ color: 'var(--re-text-muted)' }}>
          All requests to the RegEngine API require the <code style={{ backgroundColor: 'rgba(255,255,255,0.06)', padding: '2px 6px', borderRadius: '4px' }}>X-RegEngine-API-Key</code> header.
          This header contains your API key for authentication.
        </p>
        <CodeBlock
          language="curl"
          code={`curl -X GET https://api.regengine.io/v1/events \\
  -H "X-RegEngine-API-Key: rge_prod_abcd1234..."`}
        />
        <CodeBlock
          language="python"
          code={`import requests

headers = {
    "X-RegEngine-API-Key": "rge_prod_abcd1234..."
}
response = requests.get(
    "https://api.regengine.io/v1/events",
    headers=headers
)`}
        />        <CodeBlock
          language="javascript"
          code={`const headers = {
  'X-RegEngine-API-Key': 'rge_prod_abcd1234...'
};

fetch('https://api.regengine.io/v1/events', {
  method: 'GET',
  headers: headers
})
  .then(response => response.json())
  .then(data => console.log(data));`}
        />
      </section>

      {/* Tenant ID Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <Key size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            Tenant ID
          </h2>
        </div>
        <p style={{ color: 'var(--re-text-muted)' }}>
          For multi-tenant API requests, include the <code style={{ backgroundColor: 'rgba(255,255,255,0.06)', padding: '2px 6px', borderRadius: '4px' }}>X-Tenant-ID</code> header
          with your tenant UUID to scope requests to a specific tenant.
        </p>
        <CodeBlock
          language="curl"
          code={`curl -X POST https://api.regengine.io/v1/ctes \\
  -H "X-RegEngine-API-Key: rge_prod_abcd1234..." \\
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \\
  -H "Content-Type: application/json" \\
  -d '{"data": {...}'`}
        />
      </section>

      {/* Key Prefixes Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            Key Prefixes
          </h2>
        </div>        <p style={{ color: 'var(--re-text-muted)' }}>
          API keys are prefixed to indicate their environment and context.
        </p>
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
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Prefix</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Environment</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Usage</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)' }}><code>rge_dev_</code></td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Development</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Testing and development only</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)' }}><code>rge_prod_</code></td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Production</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>Live production requests</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Best Practices Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <ShieldCheck size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            Key Security Best Practices
          </h2>
        </div>        <ul style={{ color: 'var(--re-text-muted)', paddingLeft: '24px', space: '8px' }}>
          <li style={{ marginBottom: '8px' }}>Never commit API keys to version control. Always use environment variables.</li>
          <li style={{ marginBottom: '8px' }}>Use separate API keys for development and production environments.</li>
          <li style={{ marginBottom: '8px' }}>Rotate API keys every 90 days or after exposure.</li>
          <li style={{ marginBottom: '8px' }}>Restrict API key access to necessary services and team members only.</li>
          <li style={{ marginBottom: '8px' }}>Use HTTPS for all API requests. Never use HTTP.</li>
          <li style={{ marginBottom: '8px' }}>Monitor API key usage for unusual activity in the developer portal.</li>
        </ul>
      </section>

      {/* Rate Limits Section */}
      <section className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <Info size={24} style={{ color: 'var(--re-brand)' }} />
          <h2 className="text-2xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
            Rate Limits by Plan
          </h2>
        </div>
        <p style={{ color: 'var(--re-text-muted)' }}>
          Rate limits are enforced per API key and reset every minute. CTEs (Cumulative Tag Events) are counted monthly.
        </p>
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
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Plan</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>Requests/Min</th>
                <th style={{ textAlign: 'left', padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}>CTEs/Month</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)' }}>Growth</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>100</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>10,000</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-primary)' }}>Scale</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>500</td>
                <td style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.06)', color: 'var(--re-text-muted)' }}>100,000</td>
              </tr>
              <tr>
                <td style={{ padding: '12px', color: 'var(--re-text-primary)' }}>Enterprise</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>Custom</td>
                <td style={{ padding: '12px', color: 'var(--re-text-muted)' }}>Custom</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}