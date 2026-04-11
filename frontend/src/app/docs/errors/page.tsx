import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Error Codes | RegEngine',
  description: 'HTTP status codes and API-specific error responses for the RegEngine API, with fixes and retry strategies.',
};
import { ArrowLeft, AlertCircle, XCircle, AlertTriangle, Info } from 'lucide-react';
import { T } from '@/lib/design-tokens';

const errorCodes = [
    // 4xx Client Errors
    { code: 400, name: 'Bad Request', description: 'The request body is malformed or missing required fields.', fix: 'Check your JSON syntax and required fields in the API reference.', category: 'client' },
    { code: 401, name: 'Unauthorized', description: 'Missing or invalid API key.', fix: 'Ensure the X-RegEngine-API-Key header is set with a valid API key.', category: 'client' },
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
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <div className="p-6" style={{ borderBottom: `1px solid ${T.border}` }}>
                <div className="max-w-[900px] mx-auto">
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-sm no-underline mb-4"
                        style={{ color: T.accent }}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>
                    <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
                        Error Codes
                    </h1>
                    <p className="text-re-text-muted text-base">
                        HTTP status codes and API-specific error responses
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-[900px] mx-auto py-12 px-6">

                {/* HTTP Status Codes Section */}
                <section className="mb-14">
                    <h2 className="text-2xl font-semibold text-[var(--re-text-primary)] mb-6">
                        HTTP Status Codes
                    </h2>

                    {/* Client Errors */}
                    <div className="mb-8">
                        <h3 className="text-xs font-semibold uppercase tracking-wider mb-4 flex items-center gap-2" style={{ color: T.textMuted }}>
                            <AlertTriangle className="w-3.5 h-3.5 text-[var(--re-warning)]" />
                            4xx Client Errors
                        </h3>

                        <div className="rounded-lg overflow-x-auto" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th className="text-left px-4 py-3 text-xs font-semibold w-[100px]" style={{ color: T.textMuted }}>Code</th>
                                        <th className="text-left px-4 py-3 text-xs font-semibold w-[150px]" style={{ color: T.textMuted }}>Name</th>
                                        <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">Description</th>
                                        <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">How to Fix</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {errorCodes.filter(e => e.category === 'client').map((error, i) => (
                                        <tr key={error.code} style={{ borderBottom: i < errorCodes.filter(e => e.category === 'client').length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                            <td className="px-4 py-3">
                                                <code className="bg-[rgba(234,179,8,0.2)] text-[var(--re-warning)] px-2 py-1 rounded text-[13px] font-semibold">{error.code}</code>
                                            </td>
                                            <td className="px-4 py-3 text-re-text-primary font-medium">{error.name}</td>
                                            <td className="px-4 py-3 text-re-text-secondary text-sm">{error.description}</td>
                                            <td className="px-4 py-3 text-re-text-muted text-sm">{error.fix}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Server Errors */}
                    <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider mb-4 flex items-center gap-2" style={{ color: T.textMuted }}>
                            <XCircle className="w-3.5 h-3.5 text-[var(--re-danger)]" />
                            5xx Server Errors
                        </h3>

                        <div className="rounded-lg overflow-x-auto" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th className="text-left px-4 py-3 text-xs font-semibold w-[100px]" style={{ color: T.textMuted }}>Code</th>
                                        <th className="text-left px-4 py-3 text-xs font-semibold w-[150px]" style={{ color: T.textMuted }}>Name</th>
                                        <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">Description</th>
                                        <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">How to Fix</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {errorCodes.filter(e => e.category === 'server').map((error, i) => (
                                        <tr key={error.code} style={{ borderBottom: i < errorCodes.filter(e => e.category === 'server').length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                            <td className="px-4 py-3">
                                                <code className="bg-[rgba(239,68,68,0.2)] text-[var(--re-danger)] px-2 py-1 rounded text-[13px] font-semibold">{error.code}</code>
                                            </td>
                                            <td className="px-4 py-3 text-re-text-primary font-medium">{error.name}</td>
                                            <td className="px-4 py-3 text-re-text-secondary text-sm">{error.description}</td>
                                            <td className="px-4 py-3 text-re-text-muted text-sm">{error.fix}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>

                {/* API Error Codes Section */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        API Error Codes
                    </h2>
                    <p className="leading-relaxed mb-6" style={{ color: T.text }}>
                        In addition to HTTP status codes, the response body includes a machine-readable error code:
                    </p>

                    {/* Example Response */}
                    <div className="bg-black/60 rounded-lg overflow-hidden mb-6" style={{ border: `1px solid ${T.border}` }}>
                        <div className="bg-[rgba(239,68,68,0.1)] px-4 py-2 flex items-center gap-2" style={{ borderBottom: `1px solid ${T.border}` }}>
                            <div className="w-2 h-2 rounded-full bg-[var(--re-danger)]" />
                            <span className="text-xs text-[var(--re-danger)]">401 Unauthorized</span>
                        </div>
                        <pre className="p-4 sm:p-[16px_20px] m-0 text-[12px] sm:text-[13px] leading-[1.5] text-[var(--re-text-tertiary)]">
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
                    <div className="rounded-lg overflow-x-auto" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                        <table className="w-full border-collapse">
                            <thead>
                                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                    <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">Error Code</th>
                                    <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">Message</th>
                                    <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">How to Fix</th>
                                </tr>
                            </thead>
                            <tbody>
                                {apiErrors.map((error, i) => (
                                    <tr key={error.code} style={{ borderBottom: i < apiErrors.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                        <td className="px-4 py-3">
                                            <code className="bg-white/10 text-[var(--re-text-primary)] px-2 py-1 rounded text-xs">{error.code}</code>
                                        </td>
                                        <td className="px-4 py-3 text-re-text-secondary text-sm">{error.message}</td>
                                        <td className="px-4 py-3 text-re-text-muted text-sm">{error.fix}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>

                {/* Retry Strategy */}
                <section className="mb-12">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        Retry Strategy
                    </h2>

                    <div className="bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.3)] rounded-lg p-5 mb-6">
                        <div className="flex items-start gap-3">
                            <Info className="w-5 h-5 shrink-0 mt-0.5" style={{ color: T.accent }} />
                            <div>
                                <p className="text-[var(--re-text-primary)] font-semibold mb-1">Best Practice</p>
                                <p className="text-re-text-secondary text-sm m-0">
                                    Use exponential backoff with jitter for 429 and 5xx errors. Start at 1 second, double each retry, cap at 32 seconds.
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-black/40 rounded-lg overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
                        <div className="bg-white/5 px-4 py-2" style={{ borderBottom: `1px solid ${T.border}` }}>
                            <span className="text-xs text-re-text-muted">Python Example</span>
                        </div>
                        <pre className="px-5 py-4 m-0 text-[13px] leading-normal text-[var(--re-text-tertiary)] overflow-x-auto">
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
                <div className="rounded-lg p-6 flex justify-between items-center" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                    <Link
                        href="/docs/rate-limits"
                        className="text-sm no-underline flex items-center gap-2"
                        style={{ color: T.accent }}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Rate Limits
                    </Link>
                    <Link
                        href="/docs/api"
                        className="text-sm no-underline"
                        style={{ color: T.accent }}
                    >
                        API Reference →
                    </Link>
                </div>
            </div>
        </div>
    );
}
