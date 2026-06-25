"use client";

import Link from "next/link";
import { ArrowLeft, Activity, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";


export default function RateLimitsDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Documentation
                </Link>

                <div className="mb-12">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-3 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
                            <Activity className="h-8 w-8 text-purple-600 dark:text-purple-400" />
                        </div>
                        <h1 className="text-4xl font-bold">Rate Limits</h1>
                    </div>
                    <p className="text-xl text-muted-foreground">
                        Understanding API quotas, response headers, and 429 backoff.
                    </p>
                </div>

                <div className="space-y-8">
                    <Card>
                        <CardHeader>
                            <CardTitle>Default Limits</CardTitle>
                            <CardDescription>
                                Rate limits are applied per API key.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <p className="text-muted-foreground">
                                All API keys are rate limited on a per-key basis. If you need higher throughput,{' '}
                                <Link href="/alpha" className="text-primary underline">contact us</Link> to discuss your requirements.
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
                            <CardTitle>Response Headers</CardTitle>
                            <CardDescription>
                                Rate-limit metadata is returned on successful responses and <code>429 Too Many Requests</code> responses so clients can back off before exhausting a bucket.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b pb-4 font-semibold text-sm">
                                    <div>Header</div>
                                    <div className="md:col-span-2">Description</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b pb-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Limit</div>
                                    <div className="md:col-span-2">The maximum requests allowed in the current window for this scope.</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b pb-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Remaining</div>
                                    <div className="md:col-span-2">Requests remaining in the current window. This is <code>0</code> on a 429 response.</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b pb-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Reset</div>
                                    <div className="md:col-span-2">Unix timestamp for the next rate-limit window boundary.</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b pb-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Tenant</div>
                                    <div className="md:col-span-2">The tenant ID the limit was applied to.</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Scope</div>
                                    <div className="md:col-span-2">The bucket/scope that was exceeded (e.g. <code>ingest</code>, <code>webhook_read</code>).</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <AlertTriangle className="h-5 w-5 text-re-warning" />
                                Handling Rate Limits
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="mb-4 text-muted-foreground">
                                If you exceed the rate limit, the API will return a <code className="text-primary">429 Too Many Requests</code> response.
                                Your client should handle this by pausing requests until the time specified in the <code className="text-primary">Retry-After</code> header.
                            </p>
                            <div className="bg-slate-950 rounded-lg p-4 font-mono text-sm text-slate-50">
                                <div className="text-slate-400">{'// Example 429 Response'}</div>
                                HTTP/1.1 429 Too Many Requests<br />
                                Content-Type: application/json<br />
                                Retry-After: 30<br />
                                X-RateLimit-Limit: 75<br />
                                X-RateLimit-Remaining: 0<br />
                                X-RateLimit-Reset: 1778522430<br />
                                X-RateLimit-Scope: webhooks.ingest<br />
                                <br />
                                {"{"}<br />
                                &nbsp;&nbsp;"error": {"{"}<br />
                                &nbsp;&nbsp;&nbsp;&nbsp;"code": "rate_limit_exceeded",<br />
                                &nbsp;&nbsp;&nbsp;&nbsp;"message": "Rate limit exceeded. Try again in 30 seconds.",<br />
                                &nbsp;&nbsp;&nbsp;&nbsp;"request_id": "req_abc123"<br />
                                &nbsp;&nbsp;{"}"}<br />
                                {"}"}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>        </>
    );
}
