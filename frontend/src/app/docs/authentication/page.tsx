"use client";

import Link from "next/link";
import { ArrowLeft, Key, Shield, Code } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Callout } from "@/components/ui/callout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code-block";
import { API_BASE } from "@/lib/api-base";

/** Inline identifier - SPEC §2.3. */
const CODE =
    "rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary";

const SCOPES: { scope: string; allows: string }[] = [
    { scope: "records.read", allows: "GET /records and the record detail, history, ingestion-run and trace endpoints under it" },
    { scope: "webhooks.ingest", allows: "POST /webhooks/ingest" },
    { scope: "webhooks.read", allows: "GET /webhooks/recent and GET /webhooks/chain/verify" },
    { scope: "fda.read", allows: "GET /fda/trace/{tlc} and GET /fda/export/history" },
    { scope: "fda.export", allows: "GET /fda/export, /fda/export/all, /fda/export/v2 and /fda/export/recall" },
    { scope: "fda.verify", allows: "POST /fda/export/verify and the Merkle root and proof endpoints" },
];

const EXAMPLE_REQUEST = `curl -s "${API_BASE}/records?limit=1" \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY"`;

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
                                RegEngine uses API keys to authenticate requests. RegEngine issues keys, your workspace ID and the ingest
                                signing secret on request.{" "}
                                <Link
                                    href="/contact"
                                    className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                                >
                                    Request access
                                </Link>
                                . There is no self-serve key creation.
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
                                        RegEngine issues live keys on request. Each key belongs to one workspace and carries the scopes
                                        listed below.
                                    </dd>
                                </div>
                                <div className="flex flex-col gap-1 border-b border-re-border-subtle py-3 sm:flex-row sm:gap-4">
                                    <dt className="w-24 shrink-0 font-medium text-re-text-muted">Revoke</dt>
                                    <dd className="m-0 min-w-0 text-re-text-secondary">
                                        Ask RegEngine to revoke a key whenever you need to, for example if it leaks. A revoked key is
                                        rejected on subsequent requests.
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
                                are equivalent: <code className={CODE}>records.read</code> and{' '}
                                <code className={CODE}>records:read</code> name the same scope. A key only needs the scopes for the
                                endpoints you call:
                            </p>
                            <dl className="border-t border-re-border-subtle text-ui">
                                {SCOPES.map(({ scope, allows }) => (
                                    <div
                                        key={scope}
                                        className="flex flex-col gap-1 border-b border-re-border-subtle py-3 sm:flex-row sm:gap-4"
                                    >
                                        <dt className="w-44 shrink-0">
                                            <code className="rounded-sm border border-re-border-subtle bg-re-surface-inset px-2 py-1 font-mono text-[0.8125rem] text-re-text-primary">
                                                {scope}
                                            </code>
                                        </dt>
                                        <dd className="m-0 min-w-0 text-re-text-secondary">{allows}</dd>
                                    </div>
                                ))}
                            </dl>
                        </div>

                        <Callout tone="warning" title="Scopes do not make a key read-only">
                            <p className="text-ui text-re-text-secondary">
                                Scopes limit which of the endpoints above a key can call. They are not a read-only guarantee: some other
                                operations on the RegEngine backend, for example compliance snapshots, SLA request updates, onboarding steps
                                and the EPCIS intake endpoint (Preview), accept any valid tenant key without checking a named scope. Treat every key as
                                read-write for its workspace. Keep it on your server, never in client-side code, and ask RegEngine to
                                revoke it if it leaks.
                            </p>
                        </Callout>
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
                            Send the key in <code className={CODE}>X-RegEngine-API-Key</code>. An <code className={CODE}>Authorization</code>{' '}
                            header is not accepted. RegEngine takes the workspace from the key, so do not send{' '}
                            <code className={CODE}>X-Tenant-ID</code>: a value that differs from the key&apos;s workspace is refused with a
                            403, and it never authenticates a request. The FDA endpoints take your workspace ID as a{' '}
                            <code className={CODE}>tenant_id</code> query parameter, and it must match the key.
                        </p>
                        <p className="text-ui text-re-text-secondary">
                            Ingest requests also carry <code className={CODE}>X-Webhook-Signature</code>, an HMAC-SHA256 of the request body
                            made with the signing secret RegEngine issues. See the{' '}
                            <Link
                                href="/docs/quickstart"
                                className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                            >
                                Quickstart
                            </Link>
                            .
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
                                The API key is missing or invalid. Send it in the <code className={CODE}>X-RegEngine-API-Key</code> header.
                                On ingest, a missing or wrong <code className={CODE}>X-Webhook-Signature</code> also returns 401.
                            </p>
                        </Callout>
                        <Callout tone="warning">
                            <p className="flex flex-wrap items-baseline gap-2">
                                <span className="font-mono text-[0.8125rem] font-medium text-re-text-primary">403</span>
                                <span className="font-medium text-re-text-primary">Forbidden</span>
                            </p>
                            <p className="mt-1 text-ui text-re-text-secondary">
                                The key lacks the scope this endpoint requires, or an <code className={CODE}>X-Tenant-ID</code> or{' '}
                                <code className={CODE}>tenant_id</code> value names a different workspace than the key.
                            </p>
                        </Callout>
                    </CardContent>
                </Card>
            </div>
        </>
    );
}
