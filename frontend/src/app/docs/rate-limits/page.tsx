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
                        Understanding API quotas and handling 429 errors.
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
                            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                                <div className="p-6 bg-background border rounded-lg text-center">
                                    <div className="text-3xl font-bold text-primary mb-1">100</div>
                                    <div className="text-sm text-muted-foreground">Requests per Minute</div>
                                    <div className="mt-2 text-xs font-mono bg-muted py-1 px-2 rounded inline-block">Growth</div>
                                </div>
                                <div className="p-6 bg-background border rounded-lg text-center">
                                    <div className="text-3xl font-bold text-primary mb-1">500</div>
                                    <div className="text-sm text-muted-foreground">Requests per Minute</div>
                                    <div className="mt-2 text-xs font-mono bg-muted py-1 px-2 rounded inline-block">Growth</div>
                                </div>
                                <div className="p-6 bg-background border rounded-lg text-center">
                                    <div className="text-3xl font-bold text-primary mb-1">1,000</div>
                                    <div className="text-sm text-muted-foreground">Requests per Minute</div>
                                    <div className="mt-2 text-xs font-mono bg-muted py-1 px-2 rounded inline-block">Scale</div>
                                </div>
                                <div className="p-6 bg-background border rounded-lg text-center">
                                    <div className="text-3xl font-bold text-primary mb-1">Custom</div>
                                    <div className="text-sm text-muted-foreground">Requests per Minute</div>
                                    <div className="mt-2 text-xs font-mono bg-muted py-1 px-2 rounded inline-block">Enterprise</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Response Headers</CardTitle>
                            <CardDescription>
                                Every API response includes headers to tell you about your current rate limit status.
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
                                    <div className="md:col-span-2">The maximum number of requests allowed in the current time window.</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b pb-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Remaining</div>
                                    <div className="md:col-span-2">The number of requests remaining in the current time window.</div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                                    <div className="font-mono text-purple-600">X-RateLimit-Reset</div>
                                    <div className="md:col-span-2">The time (Unix timestamp) when the current window resets.</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <AlertTriangle className="h-5 w-5 text-amber-500" />
                                Handling Rate Limits
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="mb-4 text-muted-foreground">
                                If you exceed the rate limit, the API will return a <code className="text-primary">429 Too Many Requests</code> response.
                                Your client should handle this by pausing requests until the time specified in the <code className="text-primary">Retry-After</code> header.
                            </p>
                            <div className="bg-slate-950 rounded-lg p-4 font-mono text-sm text-slate-50">
                                <div className="text-slate-400">// Example 429 Response</div>
                                HTTP/1.1 429 Too Many Requests<br />
                                Content-Type: application/json<br />
                                Retry-After: 30<br />
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
