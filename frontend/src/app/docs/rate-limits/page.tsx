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
    { header: "X-RateLimit-Remaining", description: "Requests remaining in the current window." },
    { header: "X-RateLimit-Reset", description: "Unix timestamp for the next rate-limit window boundary." },
    { header: "X-RateLimit-Tenant", description: "The workspace ID the limit was applied to." },
    {
        header: "X-RateLimit-Scope",
        description: (
            <>
                The bucket the request was counted against (for example <code className={CODE}>webhooks.ingest</code>).
            </>
        ),
    },
];

const EXAMPLE_429 = `HTTP/1.1 429 Too Many Requests
Content-Type: application/json

{
  "error": {
    "type": "http_429",
    "message": "Rate limit exceeded"
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
                description="What to do when a request is rate limited, and which headers you can and cannot rely on."
            />

            <div className="space-y-6">
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Limits</CardTitle>
                            <CardDescription>
                                Requests are rate limited. RegEngine does not publish limit values.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-ui text-re-text-secondary">
                            API keys are rate limited, and so are requests per workspace and per endpoint scope. If you need to
                            plan around a higher volume of requests,{' '}
                            <Link
                                href="/contact"
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
                 * Verified 2026-10: services/ingestion/tests/test_ratelimit_headers_2307.py shows the
                 * headers on 2xx, but _http_exception_handler in services/shared/error_handling.py
                 * builds the 429 response without exc.headers, so Retry-After and X-RateLimit-* are
                 * dropped on a 429 from require_permission and the per-key limiter. This page
                 * therefore calls the headers optional on 2xx and promises nothing on a 429 until
                 * that handler passes headers through (developer-portal plan, Phase 5).
                 */}
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Response Headers</CardTitle>
                            <CardDescription>
                                Some successful responses carry rate-limit metadata. It is not guaranteed on every response, and it is not sent reliably on a <code>429 Too Many Requests</code>, so treat these headers as optional and never build retry logic on them.
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
                            If you exceed a rate limit, the API returns <code className={CODE}>429 Too Many Requests</code>. Stop sending
                            for 60 seconds, then retry. Do not wait for a <code className={CODE}>Retry-After</code> header: a 429 does
                            not reliably carry one. The body is the usual error object (see{' '}
                            <Link
                                href="/docs/errors"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                Error Codes
                            </Link>
                            ); some 429s instead return <code className={CODE}>{`{"error": "rate_limit_exceeded", "detail": "..."}`}</code>.
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
