"use client";

import Link from "next/link";
import { ArrowLeft, Key, Shield, Code } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Callout } from "@/components/ui/callout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code-block";

/** Inline identifier — SPEC §2.3. */
const CODE =
    "rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary";

const SCOPES = ["records.read", "webhooks.ingest", "fda.export"];

const EXAMPLE_REQUEST = `curl https://regengine.co/api/v1/fda/export?tlc=00012345678901-LOT-2026-001&tenant_id=YOUR_TENANT_UUID \\
  -H "X-RegEngine-API-Key: rge_live_12345" \\
  -H "Content-Type: application/json"`;

export default function AuthenticationDocsPage() {
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
                title="Authentication"
                description="Authenticate API requests with an API key in the X-RegEngine-API-Key header."
            />

            <div className="space-y-6">
                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Key aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                                API Keys
                            </CardTitle>
                            <CardDescription>
                                RegEngine uses API keys to authenticate requests. You can view and manage your API keys in the{" "}
                                <Link
                                    href="/api-keys"
                                    className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                                >
                                    API Keys Dashboard
                                </Link>
                                .
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <Callout tone="warning">
                            <p>
                                <strong className="font-medium text-re-text-primary">Security Warning:</strong> Your API keys carry many privileges, so be sure to keep them secure! Do not share your secret API keys in publicly accessible areas such as GitHub, client-side code, and so forth.
                            </p>
                        </Callout>

                        {/* Key Format */}
                        <div>
                            <h4 className="mb-3 text-subheading text-re-text-primary">Key Format</h4>
                            <div className="flex flex-wrap items-center gap-3 rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                <code className="shrink-0 rounded-sm border border-re-border bg-re-surface-card px-2 py-1 font-mono text-[0.8125rem] font-medium text-re-text-primary">
                                    rge_live_
                                </code>
                                <span className="min-w-0 flex-1 text-ui text-re-text-secondary">
                                    Every API key starts with this prefix and is scoped to your tenant. There is no separate test-key environment.
                                </span>
                            </div>
                        </div>

                        {/* Key Lifecycle */}
                        <div>
                            <h4 className="mb-3 text-subheading text-re-text-primary">Key Lifecycle</h4>
                            <dl className="border-t border-re-border-subtle text-ui">
                                <div className="flex flex-col gap-1 border-b border-re-border-subtle py-3 sm:flex-row sm:gap-4">
                                    <dt className="w-24 shrink-0 font-medium text-re-text-muted">Create</dt>
                                    <dd className="m-0 min-w-0 text-re-text-secondary">
                                        Live keys are provisioned by the RegEngine team during onboarding. Keys created in the developer portal sandbox cannot authenticate live API requests.
                                    </dd>
                                </div>
                                <div className="flex flex-col gap-1 border-b border-re-border-subtle py-3 sm:flex-row sm:gap-4">
                                    <dt className="w-24 shrink-0 font-medium text-re-text-muted">Revoke</dt>
                                    <dd className="m-0 min-w-0 text-re-text-secondary">
                                        Revoked keys are rejected on subsequent requests. Allow a short propagation window for in-flight cached lookups.
                                    </dd>
                                </div>
                            </dl>
                        </div>

                        {/* Scopes */}
                        <div>
                            <h4 className="mb-3 text-subheading text-re-text-primary">Scopes</h4>
                            <p className="mb-3 text-ui text-re-text-secondary">
                                Keys carry scopes in a <code className={CODE}>resource.action</code> vocabulary.
                                The <code className={CODE}>.</code> and <code className={CODE}>:</code> separators
                                are equivalent — <code className={CODE}>records.read</code> and{' '}
                                <code className={CODE}>records:read</code> name the same scope. Examples:
                            </p>
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                {SCOPES.map((scope) => (
                                    <code
                                        key={scope}
                                        className="rounded-sm border border-re-border-subtle bg-re-surface-inset px-2 py-1 font-mono text-[0.8125rem] text-re-text-primary"
                                    >
                                        {scope}
                                    </code>
                                ))}
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Shield aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                                API Key Header
                            </CardTitle>
                            <CardDescription>
                                Authenticate your HTTP requests by including your API Key in the X-RegEngine-API-Key header.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <Card variant="inset" className="overflow-hidden">
                            <div className="border-b border-re-border-subtle px-4 py-2">
                                <span className="font-mono text-label uppercase text-re-text-muted">HTTP Header</span>
                            </div>
                            <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
                                <code>X-RegEngine-API-Key: rge_live_...</code>
                            </pre>
                        </Card>

                        <div>
                            <h3 className="mb-2 text-subheading text-re-text-primary">Example Request</h3>
                            <CodeBlock code={EXAMPLE_REQUEST} language="bash" />
                        </div>

                        <p className="text-ui text-re-text-secondary">
                            <code className={CODE}>X-Tenant-ID</code> is optional.
                            When supplied, it is only an assertion and must match the tenant bound to the API key;
                            it never authenticates a request.
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle>Human administration</CardTitle>
                            <CardDescription>
                                Browser administration is separate from the public API.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-ui text-re-text-secondary">
                            Staff administration uses an opaque Secure, HttpOnly, SameSite=Lax session cookie and
                            requires a WebAuthn or SSO-authenticated sysadmin for high-assurance actions. Browser
                            sessions and internal workload routes are intentionally absent from public OpenAPI.
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Code aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                                Authentication Errors
                            </CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <Callout tone="danger">
                            <p className="flex flex-wrap items-baseline gap-2">
                                <span className="font-mono text-[0.8125rem] font-medium text-re-text-primary">401</span>
                                <span className="font-medium text-re-text-primary">Unauthorized</span>
                            </p>
                            <p className="mt-1 text-ui text-re-text-secondary">
                                The API key is missing or invalid. Check that you are sending the correct header.
                            </p>
                        </Callout>
                        <Callout tone="warning">
                            <p className="flex flex-wrap items-baseline gap-2">
                                <span className="font-mono text-[0.8125rem] font-medium text-re-text-primary">403</span>
                                <span className="font-medium text-re-text-primary">Forbidden</span>
                            </p>
                            <p className="mt-1 text-ui text-re-text-secondary">
                                The API key does not have permission to perform this request (e.g., mismatched scopes).
                            </p>
                        </Callout>
                    </CardContent>
                </Card>
            </div>
        </>
    );
}
