import Link from 'next/link';
import { ArrowLeft, AlertCircle, XCircle, AlertTriangle, Info } from 'lucide-react';
import { T } from '@/lib/design-tokens';

const errorCodes = [
    // 4xx Client Errors
    { code: 400, name: 'Bad Request', description: 'The request body is malformed or missing required fields.', fix: 'Check your JSON syntax and required fields in the API reference.', category: 'client' },
    { code: 401, name: 'Unauthorized', description: 'Missing or invalid API key.', fix: 'Ensure the Authorization header is set with a valid Bearer token.', category: 'client' },
    { code: 403, name: 'Forbidden', description: 'API key lacks permission for this operation.', fix: 'Check key scope and tenant permissions.', category: 'client' },
    { code: 404, name: 'Not Found', description: 'The requested resource does not exist.', fix: 'Verify the resource ID and endpoint path.', category: 'client' },
    { code: 409, name: 'Conflict', description: 'Resource already exists or state conflict.', fix: 'Check for duplicate record IDs or race conditions.', category: 'client' },
    { code: 422, name: 'Unprocessable Entity', description: 'Request is well-formed but contains invalid data.', fix: 'Review field validation rules in the API reference.', category: 'client' },
    { code: 429, name: 'Too Many Requests', description: 'Rate limit exceeded.', fix: 'Implement exponential backoff. See Rate Limits docs.', category: 'client' },

    // 5xx Server Errors
    { code: 500, name: 'Internal Server Error', description: 'Unexpected server error.', fix: 'Retry with exponential backoff. Contact support if persistent.', category: 'server' },
    { code: 502, name: 'Bad Gateway', description: 'Upstream service unavailable.', fix: 'Check API status page. Retry in 30 seconds.', category: 'server' },
    { code: 503, name: 'Service Unavailable', description: 'Service temporarily overloaded or in maintenance.', fix: 'Check status page for scheduled maintenance.', category: 'server' },
    { code: 504, name: 'Gateway Timeout', description: 'Request took too long to process.', fix: 'Reduce payload size or paginate large requests.', category: 'server' },
];

const apiErrors = [
    { code: 'invalid_api_key', message: 'The API key provided is not valid', fix: 'Generate a new key from the dashboard' },
    { code: 'expired_api_key', message: 'This API key has expired', fix: 'Generate a new key or extend expiration in settings' },
    { code: 'tenant_not_found', message: 'No tenant associated with this API key', fix: 'Verify tenant setup in admin dashboard' },
    { code: 'record_immutable', message: 'Cannot modify immutable compliance record', fix: 'Create a new record version instead of updating' },
    { code: 'hash_mismatch', message: 'Content hash does not match expected value', fix: 'Data integrity issue - check for transmission errors' },
    { code: 'chain_position_conflict', message: 'Chain position already occupied', fix: 'Retry request - server will assign next position' },
    { code: 'invalid_framework', message: 'Specified compliance framework not recognized', fix: 'Check /industries endpoint for supported frameworks' },
    { code: 'document_too_large', message: 'Document exceeds maximum size limit', fix: 'Split document or compress before upload (max 50MB)' },
    { code: 'rate_limit_exceeded', message: 'Too many requests in time window', fix: 'Implement exponential backoff, see Rate Limits docs' },
];

export default function ErrorCodesPage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{ borderBottom: `1px solid ${T.border}`, padding: '24px' }}>
                <div style={{ maxWidth: '900px', margin: '0 auto' }}>
                    <Link
                        href="/docs"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: T.accent,
                            fontSize: '14px',
                            textDecoration: 'none',
                            marginBottom: '16px',
                        }}
                    >
                        <ArrowLeft style={{ width: 16, height: 16 }} />
                        Back to Docs
                    </Link>
                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Error Codes
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        HTTP status codes and API-specific error responses
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '900px', margin: '0 auto', padding: '48px 24px' }}>

                {/* HTTP Status Codes Section */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '24px' }}>
                        HTTP Status Codes
                    </h2>

                    {/* Client Errors */}
                    <div style={{ marginBottom: '32px' }}>
                        <h3 style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: T.textMuted,
                            textTransform: 'uppercase',
                            letterSpacing: '1px',
                            marginBottom: '16px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}>
                            <AlertTriangle style={{ width: 14, height: 14, color: 'var(--re-warning)' }} />
                            4xx Client Errors
                        </h3>

                        <div style={{
                            background: T.surface,
                            border: `1px solid ${T.border}`,
                            borderRadius: '8px',
                            overflow: 'hidden',
                        }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600, width: '100px' }}>Code</th>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600, width: '150px' }}>Name</th>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>Description</th>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>How to Fix</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {errorCodes.filter(e => e.category === 'client').map((error, i) => (
                                        <tr key={error.code} style={{ borderBottom: i < errorCodes.filter(e => e.category === 'client').length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                            <td style={{ padding: '12px 16px' }}>
                                                <code style={{
                                                    background: 'rgba(234,179,8,0.2)',
                                                    color: 'var(--re-warning)',
                                                    padding: '4px 8px',
                                                    borderRadius: '4px',
                                                    fontSize: '13px',
                                                    fontWeight: 600,
                                                }}>{error.code}</code>
                                            </td>
                                            <td style={{ padding: '12px 16px', color: 'var(--re-text-primary)', fontWeight: 500 }}>{error.name}</td>
                                            <td style={{ padding: '12px 16px', color: T.text, fontSize: '14px' }}>{error.description}</td>
                                            <td style={{ padding: '12px 16px', color: T.textMuted, fontSize: '14px' }}>{error.fix}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Server Errors */}
                    <div>
                        <h3 style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: T.textMuted,
                            textTransform: 'uppercase',
                            letterSpacing: '1px',
                            marginBottom: '16px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}>
                            <XCircle style={{ width: 14, height: 14, color: 'var(--re-danger)' }} />
                            5xx Server Errors
                        </h3>

                        <div style={{
                            background: T.surface,
                            border: `1px solid ${T.border}`,
                            borderRadius: '8px',
                            overflow: 'hidden',
                        }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600, width: '100px' }}>Code</th>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600, width: '150px' }}>Name</th>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>Description</th>
                                        <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>How to Fix</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {errorCodes.filter(e => e.category === 'server').map((error, i) => (
                                        <tr key={error.code} style={{ borderBottom: i < errorCodes.filter(e => e.category === 'server').length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                            <td style={{ padding: '12px 16px' }}>
                                                <code style={{
                                                    background: 'rgba(239,68,68,0.2)',
                                                    color: 'var(--re-danger)',
                                                    padding: '4px 8px',
                                                    borderRadius: '4px',
                                                    fontSize: '13px',
                                                    fontWeight: 600,
                                                }}>{error.code}</code>
                                            </td>
                                            <td style={{ padding: '12px 16px', color: 'var(--re-text-primary)', fontWeight: 500 }}>{error.name}</td>
                                            <td style={{ padding: '12px 16px', color: T.text, fontSize: '14px' }}>{error.description}</td>
                                            <td style={{ padding: '12px 16px', color: T.textMuted, fontSize: '14px' }}>{error.fix}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>

                {/* API Error Codes Section */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        API Error Codes
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '24px' }}>
                        In addition to HTTP status codes, the response body includes a machine-readable error code:
                    </p>

                    {/* Example Response */}
                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                        marginBottom: '24px',
                    }}>
                        <div style={{
                            background: 'rgba(239,68,68,0.1)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}>
                            <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--re-danger)' }} />
                            <span style={{ fontSize: '12px', color: 'var(--re-danger)' }}>401 Unauthorized</span>
                        </div>
                        <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: 'var(--re-text-tertiary)' }}>
                            <code>{`{
  "error": {
    "code": "invalid_api_key",
    "message": "The API key provided is not valid",
    "request_id": "req_a1b2c3d4e5f6"
  }
}`}</code>
                        </pre>
                    </div>

                    {/* Error Code Table */}
                    <div style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: '8px',
                        overflow: 'hidden',
                    }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                    <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>Error Code</th>
                                    <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>Message</th>
                                    <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>How to Fix</th>
                                </tr>
                            </thead>
                            <tbody>
                                {apiErrors.map((error, i) => (
                                    <tr key={error.code} style={{ borderBottom: i < apiErrors.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                        <td style={{ padding: '12px 16px' }}>
                                            <code style={{
                                                background: 'rgba(255,255,255,0.1)',
                                                color: 'var(--re-text-primary)',
                                                padding: '4px 8px',
                                                borderRadius: '4px',
                                                fontSize: '12px',
                                            }}>{error.code}</code>
                                        </td>
                                        <td style={{ padding: '12px 16px', color: T.text, fontSize: '14px' }}>{error.message}</td>
                                        <td style={{ padding: '12px 16px', color: T.textMuted, fontSize: '14px' }}>{error.fix}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>

                {/* Retry Strategy */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        Retry Strategy
                    </h2>

                    <div style={{
                        background: 'rgba(16,185,129,0.1)',
                        border: `1px solid rgba(16,185,129,0.3)`,
                        borderRadius: '8px',
                        padding: '20px',
                        marginBottom: '24px',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                            <Info style={{ width: 20, height: 20, color: T.accent, flexShrink: 0, marginTop: '2px' }} />
                            <div>
                                <p style={{ color: 'var(--re-text-primary)', fontWeight: 600, marginBottom: '4px' }}>Best Practice</p>
                                <p style={{ color: T.text, fontSize: '14px', margin: 0 }}>
                                    Use exponential backoff with jitter for 429 and 5xx errors. Start at 1 second, double each retry, cap at 32 seconds.
                                </p>
                            </div>
                        </div>
                    </div>

                    <div style={{
                        background: 'rgba(0,0,0,0.4)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                    }}>
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                        }}>
                            <span style={{ fontSize: '12px', color: T.textMuted }}>Python Example</span>
                        </div>
                        <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: 'var(--re-text-tertiary)', overflowX: 'auto' }}>
                            <code>{`import time
import random
import requests

def make_request_with_retry(url, headers, max_retries=5):
    for attempt in range(max_retries):
        response = requests.post(url, headers=headers)
        
        if response.status_code in [429, 500, 502, 503, 504]:
            delay = min(32, (2 ** attempt)) + random.uniform(0, 1)
            time.sleep(delay)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")`}</code>
                        </pre>
                    </div>
                </section>

                {/* Navigation */}
                <div style={{
                    background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderRadius: '8px',
                    padding: '24px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                }}>
                    <Link
                        href="/docs/rate-limits"
                        style={{ color: T.accent, fontSize: '14px', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        <ArrowLeft style={{ width: 16, height: 16 }} />
                        Rate Limits
                    </Link>
                    <Link
                        href="/docs/api"
                        style={{ color: T.accent, fontSize: '14px', textDecoration: 'none' }}
                    >
                        API Reference →
                    </Link>
                </div>
            </div>
        </div>
    );
}
