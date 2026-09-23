import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Error Codes | RegEngine',
  description: 'HTTP status codes and API-specific error responses for the RegEngine API, with fixes and retry strategies.',
  openGraph: {
    title: 'Error Codes',
    description: 'HTTP status codes and API-specific error responses for the RegEngine API, with fixes and retry strategies.',
    url: 'https://regengine.co/docs/errors',
    type: 'website',
  },
};
import { ArrowLeft } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';

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
    { code: 'rate_limit_exceeded', message: 'Too many requests in time window', fix: 'Implement exponential backoff, see Rate Limits docs' },
];

const ERROR_RESPONSE = `{
  "error": {
    "code": "invalid_api_key",
    "message": "The API key provided is not valid",
    "request_id": "req_a1b2c3d4e5f6"
  }
}`;

const RETRY_SNIPPET = `import time
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
    
    raise Exception("Max retries exceeded")`;

function StatusTable({
    rows,
    tone,
}: {
    rows: typeof errorCodes;
    tone: 'warning' | 'danger';
}) {
    return (
        <Card className="overflow-hidden">
            <Table className="min-w-[36rem]">
                <TableHeader>
                    <TableRow>
                        <TableHead className="w-[5rem]">Code</TableHead>
                        <TableHead className="w-[9rem]">Name</TableHead>
                        <TableHead>Description</TableHead>
                        <TableHead>How to Fix</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {rows.map((error) => (
                        <TableRow key={error.code}>
                            <TableCell>
                                <Badge tone={tone} size="sm" mono>
                                    {error.code}
                                </Badge>
                            </TableCell>
                            <TableCell className="text-re-text-primary">{error.name}</TableCell>
                            <TableCell>{error.description}</TableCell>
                            <TableCell className="text-re-text-tertiary">{error.fix}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </Card>
    );
}

export default function ErrorCodesPage() {
    return (
        <>
            <PageHeader
                breadcrumbs={
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Back to Docs
                    </Link>
                }
                title="Error Codes"
                description="HTTP status codes and API-specific error responses"
            />

            <div className="space-y-10">
                {/* HTTP Status Codes Section */}
                <section>
                    <h2 className="mb-5 text-heading text-re-text-primary">HTTP Status Codes</h2>

                    <div className="space-y-6">
                        <div>
                            <h3 className="mb-3 font-mono text-label uppercase text-re-text-muted">
                                4xx Client Errors
                            </h3>
                            <StatusTable rows={errorCodes.filter((e) => e.category === 'client')} tone="warning" />
                        </div>

                        <div>
                            <h3 className="mb-3 font-mono text-label uppercase text-re-text-muted">
                                5xx Server Errors
                            </h3>
                            <StatusTable rows={errorCodes.filter((e) => e.category === 'server')} tone="danger" />
                        </div>
                    </div>
                </section>

                {/* API Error Codes Section */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">API Error Codes</h2>
                    <p className="mb-5 text-body text-re-text-secondary">
                        In addition to HTTP status codes, the response body includes a machine-readable error code:
                    </p>

                    {/* Example Response */}
                    <Card variant="inset" className="mb-5 overflow-hidden">
                        <div className="border-b border-re-border-subtle px-4 py-2">
                            <Badge tone="danger" size="sm" mono>
                                401 Unauthorized
                            </Badge>
                        </div>
                        <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
                            <code>{ERROR_RESPONSE}</code>
                        </pre>
                    </Card>

                    {/* Error Code Table */}
                    <Card className="overflow-hidden">
                        <Table className="min-w-[36rem]">
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[12rem]">Error Code</TableHead>
                                    <TableHead>Message</TableHead>
                                    <TableHead>How to Fix</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {apiErrors.map((error) => (
                                    <TableRow key={error.code}>
                                        <TableCell className="font-mono text-[0.8125rem]">{error.code}</TableCell>
                                        <TableCell>{error.message}</TableCell>
                                        <TableCell className="text-re-text-tertiary">{error.fix}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </Card>
                </section>

                {/* Retry Strategy */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Retry Strategy</h2>

                    <Callout tone="info" title="Best Practice" className="mb-5">
                        <p className="text-ui text-re-text-secondary">
                            Use exponential backoff with jitter for 429 and 5xx errors. Start at 1 second, double each retry, cap at 32 seconds.
                        </p>
                    </Callout>

                    <Card variant="inset" className="overflow-hidden">
                        <div className="border-b border-re-border-subtle px-4 py-2">
                            <span className="font-mono text-label uppercase text-re-text-muted">Python Example</span>
                        </div>
                        <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
                            <code>{RETRY_SNIPPET}</code>
                        </pre>
                    </Card>
                </section>

                {/* Navigation */}
                <nav className="flex items-center justify-between gap-4 border-t border-re-border-subtle pt-6">
                    <Link
                        href="/docs/rate-limits"
                        className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Rate Limits
                    </Link>
                    <Link
                        href="/docs/api"
                        className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        API Reference →
                    </Link>
                </nav>
            </div>
        </>
    );
}
