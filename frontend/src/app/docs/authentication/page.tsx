"use client";

import Link from "next/link";
import { Lock, ArrowLeft, Key, Shield, Code } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";


export default function AuthenticationDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Documentation
                </Link>

                <div className="mb-12">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-3 bg-re-info-muted dark:bg-re-info/30 rounded-lg">
                            <Lock className="h-8 w-8 text-re-info dark:text-re-info" />
                        </div>
                        <h1 className="text-4xl font-bold">Authentication</h1>
                    </div>
                    <p className="text-xl text-muted-foreground">
                        Secure your API requests with Bearer Token authentication.
                    </p>
                </div>

                <div className="space-y-8">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Key className="h-5 w-5 text-primary" />
                                API Keys
                            </CardTitle>
                            <CardDescription>
                                RegEngine uses API keys to authenticate requests. You can view and manage your API keys in the <Link href="/api-keys" className="text-primary hover:underline">API Keys Dashboard</Link>.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="bg-re-warning-muted dark:bg-re-warning/10 border-l-4 border-amber-500 p-4">
                                <p className="text-sm text-re-warning dark:text-re-warning">
                                    <strong>Security Warning:</strong> Your API keys carry many privileges, so be sure to keep them secure! Do not share your secret API keys in publicly accessible areas such as GitHub, client-side code, and so forth.
                                </p>
                            </div>

                            {/* Key Types */}
                            <div className="mt-6">
                                <h4 className="font-semibold mb-3">Key Types</h4>
                                <div className="grid gap-3">
                                    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                                        <code className="bg-primary/10 text-primary px-2 py-1 rounded text-xs font-bold">rge_live_</code>
                                        <span className="text-sm">Production key — access to your production tenant data</span>
                                    </div>
                                    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                                        <code className="bg-orange-500/10 text-orange-600 px-2 py-1 rounded text-xs font-bold">rge_test_</code>
                                        <span className="text-sm">Test key — non-production testing environment, no production tenant data</span>
                                    </div>
                                </div>
                            </div>

                            {/* Key Lifecycle */}
                            <div className="mt-6">
                                <h4 className="font-semibold mb-3">Key Lifecycle</h4>
                                <div className="space-y-3 text-sm">
                                    <div className="flex gap-3">
                                        <div className="w-24 font-medium text-muted-foreground">Create</div>
                                        <div>Generate keys from the dashboard. You can create up to 5 keys per environment.</div>
                                    </div>
                                    <div className="flex gap-3">
                                        <div className="w-24 font-medium text-muted-foreground">Rotate</div>
                                        <div>Rotate keys every 90 days. The old key remains valid for 24 hours after rotation.</div>
                                    </div>
                                    <div className="flex gap-3">
                                        <div className="w-24 font-medium text-muted-foreground">Revoke</div>
                                        <div>Revoke a key immediately if compromised. This takes effect within 60 seconds.</div>
                                    </div>
                                </div>
                            </div>

                            {/* Scopes */}
                            <div className="mt-6">
                                <h4 className="font-semibold mb-3">Scopes</h4>
                                <div className="grid grid-cols-2 gap-2 text-sm">
                                    <code className="bg-muted px-2 py-1 rounded">records:read</code>
                                    <code className="bg-muted px-2 py-1 rounded">records:write</code>
                                    <code className="bg-muted px-2 py-1 rounded">trace:read</code>
                                    <code className="bg-muted px-2 py-1 rounded">exports:write</code>
                                    <code className="bg-muted px-2 py-1 rounded">recall:read</code>
                                    <code className="bg-muted px-2 py-1 rounded">recall:write</code>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Shield className="h-5 w-5 text-primary" />
                                API Key Header
                            </CardTitle>
                            <CardDescription>
                                Authenticate your HTTP requests by including your API Key in the X-RegEngine-API-Key header.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="bg-slate-950 rounded-lg p-6 font-mono text-sm text-slate-50 overflow-x-auto">
                                <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-4">
                                    <span className="text-slate-400">HTTP Header</span>
                                </div>
                                X-RegEngine-API-Key: <span className="text-re-info">rge_live_...</span>
                            </div>

                            <div>
                                <h3 className="font-semibold mb-2">Example Request</h3>
                                <div className="bg-slate-950 rounded-lg p-6 font-mono text-sm text-slate-50 overflow-x-auto">
                                    <span className="text-purple-400">curl</span> https://regengine.co/api/v1/fda/export?tlc=00012345678901-LOT-2026-001&amp;tenant_id=YOUR_TENANT_UUID \<br />
                                    &nbsp;&nbsp;<span className="text-slate-400">-H</span> <span className="text-re-success">"X-RegEngine-API-Key: rge_live_12345"</span> \<br />
                                    &nbsp;&nbsp;<span className="text-slate-400">-H</span> <span className="text-re-success">"Content-Type: application/json"</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Code className="h-5 w-5 text-primary" />
                                Authentication Errors
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid gap-4">
                                <div className="flex items-start gap-4 p-4 rounded-lg bg-re-danger-muted dark:bg-re-danger/10">
                                    <div className="font-mono font-bold text-re-danger">401</div>
                                    <div>
                                        <div className="font-semibold text-re-danger dark:text-red-100">Unauthorized</div>
                                        <div className="text-sm text-re-danger dark:text-red-200">The API key is missing or invalid. Check that you are sending the correct header.</div>
                                    </div>
                                </div>
                                <div className="flex items-start gap-4 p-4 rounded-lg bg-orange-50 dark:bg-orange-900/10">
                                    <div className="font-mono font-bold text-orange-600">403</div>
                                    <div>
                                        <div className="font-semibold text-orange-900 dark:text-orange-100">Forbidden</div>
                                        <div className="text-sm text-orange-800 dark:text-orange-200">The API key does not have permission to perform this request (e.g., mismatched scopes).</div>
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>        </>
    );
}
