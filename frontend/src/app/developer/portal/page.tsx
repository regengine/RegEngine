'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Key } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { useAPIKeys, useRevokeAPIKey } from '@/hooks/use-api';
import { publicOpenApiSpec } from '@/lib/public-openapi';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';

const ROW = 'grid gap-x-6 gap-y-3 text-ui sm:grid-cols-[8rem_minmax(0,1fr)]';
const MONO = 'min-w-0 break-all font-mono text-small text-re-text-primary';
const LINK = 'text-re-text-primary underline underline-offset-[3px]';

const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'] as const;

interface SpecEndpoint {
    method: string;
    path: string;
    summary: string;
}

function formatEndpointSummary(summary: string): string {
    return summary.replace(/\btenant(s?)\b/gi, (match, plural) => {
        const isPlural = Boolean(plural);
        const base = isPlural ? 'workspaces' : 'workspace';
        if (match === match.toUpperCase()) {
            return base.toUpperCase();
        }
        if (match[0] === match[0].toUpperCase()) {
            return isPlural ? 'Workspaces' : 'Workspace';
        }
        return base;
    });
}

const endpoints: SpecEndpoint[] = Object.entries(publicOpenApiSpec.paths).flatMap(
    ([path, pathItem]) => {
        return Object.entries(pathItem)
            .filter(([method]) =>
                HTTP_METHODS.includes(method.toLowerCase() as typeof HTTP_METHODS[number])
            )
            .map(([method, operation]) => {
                const op = operation as { summary?: string };
                return {
                    method: method.toUpperCase(),
                    path,
                    summary: op.summary || '',
                };
            });
    }
);

function formatDateSafe(dateString?: string | null): string {
    if (!dateString) return 'Not set';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return 'Not set';
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

export default function DeveloperPortalPage() {
    const { user, tenantId } = useAuth();
    const { data: apiKeys, isLoading: isLoadingKeys } = useAPIKeys();
    const revokeKeyMutation = useRevokeAPIKey();
    const [actionError, setActionError] = useState<string | null>(null);

    const handleRevoke = async (keyId: string) => {
        try {
            setActionError(null);
            await revokeKeyMutation.mutateAsync({ keyId });
        } catch {
            setActionError('Failed to revoke API key. Please try again.');
        }
    };

    return (
        <PageContainer className="space-y-6">
            <PageHeader
                title="The JSON events API is live."
                eyebrow="Developer portal"
                description="How to reach the RegEngine API from your workspace. EPCIS (Preview) support is available for preview workflows."
                className="mb-0"
            />

            <Card>
                <CardHeader><CardTitle>Your session</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                    <dl className={ROW}>
                        <dt className="text-re-text-tertiary">Email</dt>
                        <dd className="min-w-0 break-all text-re-text-primary">{user?.email ?? 'Not available'}</dd>
                        <dt className="text-re-text-tertiary">Role</dt>
                        <dd className="min-w-0 text-re-text-primary">{user?.role_name ?? 'Not reported'}</dd>
                        {tenantId && (
                            <>
                                <dt className="text-re-text-tertiary">Workspace</dt>
                                <dd className={MONO}>{tenantId}</dd>
                            </>
                        )}
                    </dl>
                    {!tenantId && (
                        <Callout tone="warning">
                            This account has no single workspace. <Link href="/contact" className={LINK}>Contact support</Link>.
                        </Callout>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader><CardTitle>API access</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                    <dl className={ROW}>
                        <dt className="text-re-text-tertiary">Base URL</dt>
                        <dd className={MONO}>https://regengine.co/api/v1</dd>
                        <dt className="text-re-text-tertiary">Key header</dt>
                        <dd className={MONO}>X-RegEngine-API-Key</dd>
                    </dl>
                    <p className="max-w-[70ch] text-small text-re-text-tertiary">
                        Live API keys are issued by RegEngine for your workspace. Signing in here does not create or reveal a key.
                    </p>
                    <Button asChild>
                        <Link href="/contact" className="no-underline">Request a live key</Link>
                    </Button>
                    <p className="text-small text-re-text-tertiary">
                        Read the <Link href="/docs/quickstart" className={LINK}>quickstart</Link>,{' '}
                        <Link href="/docs/authentication" className={LINK}>authentication</Link> and{' '}
                        <Link href="/docs/api" className={LINK}>API reference</Link>, or see{' '}
                        <Link href="/developer/portal/keys" className={LINK}>how keys are issued</Link>.
                    </p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <div className="min-w-0">
                        <CardTitle>API keys</CardTitle>
                        <CardDescription>
                            Active credentials for this workspace.
                        </CardDescription>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    {actionError && (
                        <div className="p-5 pb-0">
                            <Callout tone="danger">{actionError}</Callout>
                        </div>
                    )}
                    {isLoadingKeys ? (
                        <div className="p-5 text-small text-re-text-tertiary">Loading keys...</div>
                    ) : !apiKeys || apiKeys.length === 0 ? (
                        <EmptyState bare icon={Key} title="No keys yet" description="No API keys have been issued for this workspace yet." />
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-ui">
                                <thead>
                                    <tr className="border-b border-re-border-subtle text-small text-re-text-tertiary">
                                        <th className="px-5 py-3 font-medium">Name</th>
                                        <th className="px-5 py-3 font-medium">Key prefix</th>
                                        <th className="px-5 py-3 font-medium">Created</th>
                                        <th className="px-5 py-3 font-medium">Last used</th>
                                        <th className="px-5 py-3 font-medium text-right">Action</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-re-border-subtle">
                                    {apiKeys.map((key) => {
                                        const keyId = key.key_id || key.id || '';
                                        const prefix = key.key_prefix?.trim() ? key.key_prefix : 'Not set';
                                        const createdAt = key.created_at || (key as { created?: string }).created;
                                        const lastUsed = key.last_used_at || key.last_used;
                                        return (
                                            <tr key={keyId} className="transition-colors hover:bg-re-surface-inset">
                                                <td className="px-5 py-3 font-medium text-re-text-primary">
                                                    {key.name || 'API key'}
                                                </td>
                                                <td className="px-5 py-3 font-mono text-small text-re-text-secondary">
                                                    {prefix}
                                                </td>
                                                <td className="px-5 py-3 text-small text-re-text-tertiary">
                                                    {formatDateSafe(createdAt)}
                                                </td>
                                                <td className="px-5 py-3 text-small text-re-text-tertiary">
                                                    {formatDateSafe(lastUsed)}
                                                </td>
                                                <td className="px-5 py-3 text-right">
                                                    <Button
                                                        variant="destructive"
                                                        size="sm"
                                                        onClick={() => handleRevoke(keyId)}
                                                        disabled={revokeKeyMutation.isPending}
                                                    >
                                                        Revoke
                                                    </Button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <div className="min-w-0">
                        <CardTitle>Endpoints</CardTitle>
                        <CardDescription>
                            Live endpoints generated from the OpenAPI specification.
                        </CardDescription>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    <ul className="divide-y divide-re-border-subtle" data-testid="endpoint-list">
                        {endpoints.map((ep) => (
                            <li key={`${ep.method}-${ep.path}`} className="px-5 py-3 transition-colors hover:bg-re-surface-inset">
                                <Link
                                    href="/docs/api"
                                    className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between text-ui no-underline"
                                >
                                    <div className="flex items-center gap-3">
                                        <span className="font-mono text-xs font-semibold uppercase text-re-text-secondary">
                                            {ep.method}
                                        </span>
                                        <code className="font-mono text-small text-re-text-primary">
                                            {ep.path}
                                        </code>
                                    </div>
                                    <span className="text-small text-re-text-tertiary">
                                        {formatEndpointSummary(ep.summary)}
                                    </span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                </CardContent>
            </Card>
        </PageContainer>
    );
}
