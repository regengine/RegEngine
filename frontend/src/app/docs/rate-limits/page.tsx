"use client";

import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

/** Inline identifier — SPEC §2.3. */
const CODE =
    "rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary";

const RESPONSE_HEADERS: { header: string; description: React.ReactNode }[] = [
    { header: "X-RateLimit-Limit", description: "The maximum requests allowed in the current window for this scope." },
    {
        header: "X-RateLimit-Remaining",
        description: (
            <>
                Requests remaining in the current window. This is <code className={CODE}>0</code> on a 429 response.
            </>
        ),
    },
    { header: "X-RateLimit-Reset", description: "Unix timestamp for the next rate-limit window boundary." },
    { header: "X-RateLimit-Tenant", description: "The tenant ID the limit was applied to." },
    {
        header: "X-RateLimit-Scope",
        description: (
            <>
                The bucket/scope that was exceeded (e.g. <code className={CODE}>ingest</code>, <code className={CODE}>webhook_read</code>).
            </>
        ),
    },
];

const EXAMPLE_429 = `// Example 429 Response
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30
X-RateLimit-Limit: 75
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1778522430
X-RateLimit-Scope: webhooks.ingest

{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Try again in 30 seconds.",
    "request_id": "req_abc123"
  }
}`;

export default function RateLimitsDocsPage() {
    return (
        <>
            <PageHeader
                breadcrumbs={
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Back to Documentation
                    </Link>
                }
                title="Rate Limits"
                description="Understanding API quotas, response headers, and 429 backoff."
            />

            <div className="space-y-6">
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Default Limits</CardTitle>
                            <CardDescription>
                                Rate limits are applied per API key.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-ui text-re-text-secondary">
                            All API keys are rate limited on a per-key basis. If you need higher throughput,{' '}
                            <Link
                                href="/alpha"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                contact us
                            </Link>{' '}
                            to discuss your requirements.
                        </p>
                    </CardContent>
                </Card>

                {/*
                 * Rate-limit header docs — propagation tracker: regengine/RegEngine#2317.
                 * Coordinate edits here with:
                 *   - #2307 (emit X-RateLimit-* on 200 responses across all routes)
                 *   - #2308 (publish public OpenAPI spec describing these headers)
                 * Keep the wording compatible with both pre- and post-#2307 behavior:
                 * headers are documented on 429s and present-when-emitted on 2xx.
                 * Do NOT re-litigate the wording without checking #2317 first.
                 */}
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Response Headers</CardTitle>
                            <CardDescription>
                                Rate-limit metadata is returned on successful responses and <code>429 Too Many Requests</code> responses so clients can back off before exhausting a bucket.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[15rem]">Header</TableHead>
                                    <TableHead>Description</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {RESPONSE_HEADERS.map((row) => (
                                    <TableRow key={row.header}>
                                        <TableCell className="font-mono text-[0.8125rem]">{row.header}</TableCell>
                                        <TableCell>{row.description}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <AlertTriangle aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                                Handling Rate Limits
                            </CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <p className="text-ui text-re-text-secondary">
                            If you exceed the rate limit, the API will return a <code className={CODE}>429 Too Many Requests</code> response.
                            Your client should handle this by pausing requests until the time specified in the <code className={CODE}>Retry-After</code> header.
                        </p>
                        <Card variant="inset">
                            <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
                                <code>{EXAMPLE_429}</code>
                            </pre>
                        </Card>
                    </CardContent>
                </Card>
            </div>
        </>
    );
}
