import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Error Codes | RegEngine',
  description: 'HTTP status codes and the error body the RegEngine API returns, with fixes and retry guidance.',
  openGraph: {
    title: 'Error Codes',
    description: 'HTTP status codes and the error body the RegEngine API returns, with fixes and retry guidance.',
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

/** Inline identifier — SPEC §2.3. */
const CODE =
    'rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary';

const errorCodes = [
    // 4xx Client Errors
    { code: 400, name: 'Bad Request', description: 'The request is malformed, or ingest is missing its Idempotency-Key header.', fix: 'Send an Idempotency-Key (255 characters at most) on every ingest POST and check the request against the API reference.', category: 'client' },
    { code: 401, name: 'Unauthorized', description: 'The API key is missing or not recognized, or an ingest request has a missing or wrong X-Webhook-Signature.', fix: 'Send the key in X-RegEngine-API-Key (an Authorization header is not accepted). Sign the exact body bytes you send.', category: 'client' },
    { code: 402, name: 'Payment Required', description: 'The workspace has no active subscription. Ingest and the FDA endpoints check this; record reads do not.', fix: 'Contact RegEngine. A retry will not help until the workspace subscription is active.', category: 'client' },
    { code: 403, name: 'Forbidden', description: 'The key lacks the scope this endpoint needs, or an X-Tenant-ID or tenant_id value names a different workspace than the key.', fix: 'Check the key scopes on the Authentication page and stop sending X-Tenant-ID.', category: 'client' },
    { code: 404, name: 'Not Found', description: 'The resource does not exist for your workspace, or the path is not part of the public API.', fix: 'Check the path against the API reference and the resource ID.', category: 'client' },
    { code: 405, name: 'Method Not Allowed', description: 'The path exists but not for this HTTP method, for example GET on /webhooks/ingest.', fix: 'Use the method shown in the API reference.', category: 'client' },
    { code: 409, name: 'Conflict', description: 'An Idempotency-Key was reused with different request bytes, or its first request is still in progress.', fix: 'Use a new Idempotency-Key for a changed payload. For an in-progress key, see Retry Strategy.', category: 'client' },
    { code: 422, name: 'Unprocessable Entity', description: 'The body is well-formed JSON but failed validation, for example an event timestamp more than 24 hours ahead. The whole request is refused and nothing is stored. The details array lists each failing field.', fix: 'Fix the fields named in error.details and send the request again.', category: 'client' },
    { code: 429, name: 'Too Many Requests', description: 'A rate limit was exceeded.', fix: 'Stop sending for 60 seconds, then retry. See Rate Limits.', category: 'client' },

    // 5xx Server Errors
    { code: 500, name: 'Internal Server Error', description: 'Unexpected server error. The message is deliberately generic.', fix: 'Retry with exponential backoff. If it persists, contact support with the time of the request.', category: 'server' },
    { code: 502, name: 'Bad Gateway', description: 'The gateway could not reach the API.', fix: 'Retry with exponential backoff.', category: 'server' },
    { code: 503, name: 'Service Unavailable', description: 'A dependency the request needs, such as the database or the subscription check, is unavailable.', fix: 'Retry with exponential backoff.', category: 'server' },
    { code: 504, name: 'Gateway Timeout', description: 'The request took too long to process.', fix: 'Send fewer events per request and retry.', category: 'server' },
];

const bodyShapes = [
    { when: 'Most errors (400, 401, 402, 403, 404, 405, 429, 500, 503)', body: 'error.type is "http_" plus the status, for example http_402. error.message says what happened.', },
    { when: '400 from a bad value', body: 'error.type is bad_request and error.message is "Invalid request".' },
    { when: '422 validation failure', body: 'error.type is validation_error. error.details lists each failing field.' },
    { when: '401 on ingest signature', body: 'error.type is http_401 and an extra error.error field is missing_webhook_signature or invalid_webhook_signature. The invalid case has a generic message on purpose.' },
    { when: 'Unhandled 500', body: 'error.type is internal_error. error.correlation_id and error.request_id are included; quote them to support.' },
    { when: 'Idempotency responses (409, 413, 503, 504)', body: 'Not an object: {"error": "idempotency_key_conflict"}. The other values are idempotency_request_in_progress, payload_too_large, idempotency_backend_unavailable and request_timeout.' },
    { when: 'Some 429 responses', body: 'Not an object: {"error": "rate_limit_exceeded", "detail": "..."}. Other 429s use the usual error object.' },
];

const ERROR_RESPONSE = `{
  "error": {
    "type": "http_402",
    "message": "No active subscription found for this tenant. If you just signed up, wait a few seconds and retry. Otherwise visit https://regengine.co/billing."
  }
}`;

const RETRY_SNIPPET = `import random
import time

import requests


def post_with_retry(url, headers, body, max_retries=5):
    """Retry one ingest request. headers carries a single Idempotency-Key and body is the
    exact signed bytes, so every retry repeats the same request."""
    for attempt in range(max_retries):
        response = requests.post(url, headers=headers, data=body)

        if response.status_code == 429:
            time.sleep(60)  # stop for 60 seconds; do not rely on rate-limit headers
            continue

        if response.status_code in (500, 502, 503, 504):
            time.sleep(min(32, 2 ** attempt) + random.uniform(0, 1))
            continue

        return response

    raise RuntimeError("Max retries exceeded")`;

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
                description="HTTP status codes and the error body the API returns"
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

                {/* Error Body Section */}
                <section>
                    <h2 className="mb-3 text-heading text-re-text-primary">Error Body</h2>
                    <p className="mb-5 text-body text-re-text-secondary">
                        Errors return a JSON body with an <code className={CODE}>error</code> object that has a{' '}
                        <code className={CODE}>type</code> and a <code className={CODE}>message</code>. There is no separate
                        machine-readable code list: branch on the HTTP status.
                    </p>

                    {/* Example Response */}
                    <Card variant="inset" className="mb-5 overflow-hidden">
                        <div className="border-b border-re-border-subtle px-4 py-2">
                            <Badge tone="danger" size="sm" mono>
                                402 Payment Required
                            </Badge>
                        </div>
                        <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
                            <code>{ERROR_RESPONSE}</code>
                        </pre>
                    </Card>

                    {/* Body shapes */}
                    <Card className="overflow-hidden">
                        <Table className="min-w-[36rem]">
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[16rem]">When</TableHead>
                                    <TableHead>What the body looks like</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {bodyShapes.map((shape) => (
                                    <TableRow key={shape.when}>
                                        <TableCell className="text-re-text-primary">{shape.when}</TableCell>
                                        <TableCell className="text-re-text-tertiary">{shape.body}</TableCell>
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
                            For 5xx errors, use exponential backoff with jitter: start at 1 second, double each retry, cap at 32 seconds.
                            For a 429, stop for 60 seconds. Retrying an ingest request is safe when you repeat the same{' '}
                            <code className={CODE}>Idempotency-Key</code> with the same bytes, because only successful responses are
                            stored and a stored one is replayed. If a retry returns <code className={CODE}>409</code>{' '}
                            <code className={CODE}>idempotency_request_in_progress</code>, the first attempt may still be running or its
                            outcome is unknown. Check <code className={CODE}>GET /api/v1/records?tlc=&lt;lot code&gt;</code> before you send
                            the batch again under a new key.
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
