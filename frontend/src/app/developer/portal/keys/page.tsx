'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/layout/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/ui/status-badge';
import { Key, Plus, Copy, Trash2, Check, Loader2 } from 'lucide-react';

interface ApiKey {
    id: string;
    name: string;
    key_prefix: string;
    enabled: boolean;
    total_requests: number;
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
}

export default function ApiKeysPage() {
    const { user: authUser, isHydrated } = useAuth();
    const [keys, setKeys] = useState<ApiKey[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isCreating, setIsCreating] = useState(false);
    const [newKeyName, setNewKeyName] = useState('');
    const [showCreate, setShowCreate] = useState(false);
    const [revealedKey, setRevealedKey] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);
    const [developerId, setDeveloperId] = useState<string | null>(null);
    const [revokingKeyId, setRevokingKeyId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const loadKeys = useCallback(async () => {
        // The server verifies Supabase auth; hydration supplies the client profile.
        if (!isHydrated) return;
        if (!authUser) {
            setIsLoading(false);
            return;
        }

        try {
            const response = await fetch('/api/developer/portal/keys', { credentials: 'include' });
            if (!response.ok) {
                setError('Could not load your API keys. Refresh to try again.');
                return;
            }
            const data = await response.json();
            setDeveloperId(data.developerId);
            setKeys(data.keys || []);
        } catch {
            setError('Could not load your API keys. Refresh to try again.');
        } finally {
            setIsLoading(false);
        }
    }, [authUser, isHydrated]);

    useEffect(() => { loadKeys(); }, [loadKeys]);

    async function createKey() {
        if (!developerId || !newKeyName.trim() || isCreating) return;
        setIsCreating(true);
        setError(null);

        try {
            const response = await fetchWithCsrf('/api/developer/portal/keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ name: newKeyName.trim() }),
            });

            if (!response.ok) {
                setError('Key creation failed. Check your connection and try again.');
                return;
            }

            const data = await response.json();
            setRevealedKey(data.rawKey);
            setNewKeyName('');
            setShowCreate(false);
            setKeys(data.keys || []);
        } catch {
            setError('Key creation failed. Check your connection and try again.');
        } finally {
            setIsCreating(false);
        }
    }

    async function revokeKey(keyId: string) {
        if (revokingKeyId) return;
        setRevokingKeyId(keyId);
        setError(null);

        try {
            const response = await fetchWithCsrf(`/api/developer/portal/keys/${encodeURIComponent(keyId)}`, {
                method: 'DELETE',
                credentials: 'include',
            });
            if (!response.ok) {
                setError('Revoking that key failed. It is still active — try again.');
                return;
            }
            await loadKeys();
        } catch {
            setError('Revoking that key failed. It is still active — try again.');
        } finally {
            setRevokingKeyId(null);
        }
    }

    function copyKey() {
        if (revealedKey) {
            navigator.clipboard.writeText(revealedKey);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    }

    // The skeleton mirrors the header, notice and key rows so nothing shifts on load.
    if (isLoading) {
        return (
            <div className="space-y-6">
                <div className="space-y-2 border-b border-re-border-subtle pb-5">
                    <Skeleton className="h-8 w-56" />
                    <Skeleton className="h-4 w-80" />
                </div>
                <Skeleton className="h-16 w-full rounded-md" />
                <Skeleton className="h-32 w-full rounded-lg" />
            </div>
        );
    }

    // Hydrated with no session: prompt for sign-in instead of showing an
    // empty key manager that can't actually do anything.
    if (!authUser) {
        return (
            <Card className="px-6 py-14 text-center">
                <h1 className="text-title text-re-text-primary">Your session has expired</h1>
                <p className="mx-auto mt-2 max-w-[48ch] text-ui text-re-text-tertiary">
                    Sign in again to manage your sandbox API keys.
                </p>
                <Button asChild size="lg" className="mt-6">
                    <a href="/login?next=/developer/portal/keys" className="no-underline">
                        Sign in
                    </a>
                </Button>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            <PageHeader
                title="Sandbox API Keys"
                description="Generate and manage sandbox keys for exploring the portal. Keys are shown once — store them securely."
                primaryAction={
                    <Button onClick={() => setShowCreate(true)} leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}>
                        New Key
                    </Button>
                }
                className="mb-0"
            />

            {/* Sandbox-only notice */}
            <Callout tone="info">
                Keys created here are <code className="font-mono text-[0.8125rem]">rge_test_</code> sandbox credentials — they
                cannot authenticate requests to the live RegEngine API. Live{' '}
                <code className="font-mono text-[0.8125rem]">rge_live_</code> keys are provisioned by the RegEngine team during
                onboarding.
            </Callout>

            {error && (
                <Callout tone="danger" role="alert">
                    {error}
                </Callout>
            )}

            {/* Revealed key banner */}
            {revealedKey && (
                <Callout
                    tone="success"
                    title="Your new sandbox key (copy it now — it won't be shown again):"
                    action={
                        <Button variant="ghost" size="sm" onClick={() => setRevealedKey(null)}>
                            Dismiss
                        </Button>
                    }
                >
                    <div className="flex items-center gap-2">
                        <code className="min-w-0 flex-1 overflow-x-auto rounded-md bg-re-surface-inset px-3 py-2 font-mono text-[0.8125rem] text-re-text-primary">
                            {revealedKey}
                        </code>
                        <Button
                            variant="secondary"
                            size="icon"
                            onClick={copyKey}
                            aria-label={copied ? 'Copied' : 'Copy'}
                        >
                            {copied
                                ? <Check className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                : <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
                        </Button>
                    </div>
                </Callout>
            )}

            {/* Create key form */}
            {showCreate && (
                <Card>
                    <CardContent>
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                            <Field label="Key Name" htmlFor="new-key-name" className="flex-1">
                                <Input
                                    placeholder="e.g. Local testing, CI experiments"
                                    value={newKeyName}
                                    onChange={(e) => setNewKeyName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && createKey()}
                                />
                            </Field>
                            <div className="flex items-center gap-2">
                                <Button
                                    onClick={createKey}
                                    loading={isCreating}
                                    disabled={!newKeyName.trim() || isCreating || !developerId}
                                >
                                    Generate
                                </Button>
                                <Button variant="ghost" onClick={() => { setShowCreate(false); setNewKeyName(''); }}>
                                    Cancel
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Keys list */}
            {keys.length === 0 ? (
                <EmptyState icon={Key} title="No API keys yet. Create one to get started." />
            ) : (
                <Card>
                    <ul className="divide-y divide-re-border-subtle">
                        {keys.map((key) => (
                            <li key={key.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
                                <Key className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <p className="truncate text-ui font-medium text-re-text-primary">{key.name}</p>
                                        {key.enabled
                                            ? <StatusBadge state="compliant" label="Active" size="sm" />
                                            : <StatusBadge state="blocked" label="Revoked" size="sm" />}
                                    </div>
                                    <p className="truncate font-mono text-[0.8125rem] text-re-text-muted">
                                        {key.key_prefix}••••••••
                                    </p>
                                </div>
                                <div className="shrink-0 text-right">
                                    <p className="text-small tabular-nums text-re-text-secondary">{key.total_requests.toLocaleString()} requests</p>
                                    <p className="text-small text-re-text-tertiary">
                                        {key.last_used_at ? `Last used ${new Date(key.last_used_at).toLocaleDateString()}` : 'Never used'}
                                    </p>
                                </div>
                                {key.enabled && (
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => revokeKey(key.id)}
                                        disabled={revokingKeyId !== null}
                                        aria-label={`Revoke ${key.name}`}
                                        className="shrink-0 text-re-danger hover:text-re-danger"
                                    >
                                        {revokingKeyId === key.id
                                            ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
                                            : <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
                                    </Button>
                                )}
                            </li>
                        ))}
                    </ul>
                </Card>
            )}
        </div>
    );
}
