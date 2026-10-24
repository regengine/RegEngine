'use client';

import { useState } from 'react';
import Link from 'next/link';

import { PasskeyRequiredNotice } from '@/components/auth/PasskeyRequiredNotice';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/ui/status-badge';
import { useAuth } from '@/lib/auth-context';
import { useAPIKeys, useCreateAPIKey, useGenerateAPIKey, useRevokeAPIKey } from '@/hooks/use-api';
import { Key, Plus, Trash2, CheckCircle, Copy, Shield, ArrowRight, Fingerprint } from 'lucide-react';
import { isRequiresStepUpPayload, requestStepUp } from '@/lib/step-up-events';
import { formatDate } from '@/lib/utils';

const API_KEYS_STEP_UP_REASON = "Confirm it's you to view and manage live API keys.";

export default function AdminPage() {
  const {
    isAuthenticated,
    isHighAssuranceSession,
    user,
    setApiKey: storeApiKey,
    tenantId,
  } = useAuth();
  const [newKeyDescription, setNewKeyDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [apiKeySaveError, setApiKeySaveError] = useState<string | null>(null);
  const [pendingRevokeKeyId, setPendingRevokeKeyId] = useState<string | null>(null);
  const canManageKeys = isAuthenticated && isHighAssuranceSession && user?.is_sysadmin === true;

  const { data: apiKeys, isLoading, refetch, error } = useAPIKeys(canManageKeys);
  const keysNeedStepUp = isRequiresStepUpPayload(
    (error as { response?: { data?: unknown } } | null)?.response?.data,
  );
  const createKeyMutation = useCreateAPIKey();
  const generateKeyMutation = useGenerateAPIKey();
  const revokeKeyMutation = useRevokeAPIKey();

  const handleCreateKey = async () => {
    if (!canManageKeys) return;

    try {
      const result = await createKeyMutation.mutateAsync({
        name: newKeyDescription || 'New API Key',
        description: newKeyDescription || undefined,
        tenantId: tenantId || undefined,
      });
      setNewKeyDescription('');
      setIsCreating(false);
      if (result.api_key) {
        setCopiedKey(result.api_key);
      }
      refetch();
    } catch (error) {
      console.error('Failed to create API key:', error);
    }
  };

  const handleGenerateKey = async () => {
    if (!canManageKeys) return;

    try {
      const result = await generateKeyMutation.mutateAsync({ tenantId: tenantId || undefined });
      if (result.api_key) {
        setGeneratedKey(result.api_key);
      }
    } catch (error) {
      console.error('Failed to generate API key:', error);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!canManageKeys) return;

    try {
      await revokeKeyMutation.mutateAsync({ keyId });
      refetch();
    } catch (error) {
      console.error('Failed to revoke API key:', error);
    } finally {
      setPendingRevokeKeyId(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleUseApiKey = async (key: string, clear: () => void) => {
    setApiKeySaveError(null);
    try {
      await storeApiKey(key);
      clear();
    } catch {
      setApiKeySaveError('The API key could not be saved. Copy it now and try again.');
    }
  };

  return (
    <PageContainer>
      <PageHeader
        title="API Management"
        description="Manage API keys and access controls"
      />

      <div className="space-y-6">
        {apiKeySaveError && (
          <Callout tone="danger" role="alert">
            {apiKeySaveError}
          </Callout>
        )}

        <Card>
          <CardHeader>
            <div className="min-w-0">
              <CardTitle>Admin Shortcuts</CardTitle>
              <CardDescription>
                Jump directly to operational consoles.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Link href="/admin/api-console">
              <Button variant="outline">
                API Console
              </Button>
            </Link>
          </CardContent>
        </Card>

        {!canManageKeys && (
          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle>High-assurance sign-in required</CardTitle>
                <CardDescription>
                  Live credential management requires a WebAuthn or SSO sysadmin session.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Callout
                tone="info"
                icon={Shield}
                title="Use your staff identity"
                action={
                  <Link href="/login?next=/admin">
                    <Button size="sm" variant="outline" trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}>
                      Sign in securely
                    </Button>
                  </Link>
                }
              >
                Email-code-only sessions cannot create or revoke live credentials. Sign in with an approved passkey or SSO account.
              </Callout>
            </CardContent>
          </Card>
        )}

        {canManageKeys && (
          <>
            {keysNeedStepUp ? (
              <div className="space-y-3">
                <PasskeyRequiredNotice>
                  Your session needs a fresh passkey confirmation before API keys can load.
                </PasskeyRequiredNotice>
                <Button
                  onClick={() => requestStepUp({ reason: API_KEYS_STEP_UP_REASON, onSuccess: () => void refetch() })}
                  leadingIcon={<Fingerprint strokeWidth={1.75} aria-hidden="true" />}
                >
                  Confirm with passkey
                </Button>
              </div>
            ) : error && (
              <Callout tone="danger" role="alert">
                This session is not authorized to manage live credentials.
              </Callout>
            )}
            {/* Quick Generate API Key */}
            <Card>
              <CardHeader>
                <div className="min-w-0">
                  <CardTitle>Developer Settings</CardTitle>
                  <CardDescription>
                    Generate and manage developer credentials without leaving the console.
                  </CardDescription>
                </div>
                <Button
                  className="shrink-0"
                  onClick={handleGenerateKey}
                  disabled={generateKeyMutation.isPending}
                  loading={generateKeyMutation.isPending}
                >
                  {generateKeyMutation.isPending ? 'Generating...' : 'Generate New API Key'}
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <Callout tone="warning">
                  This will not be shown again. Copy and store the key securely.
                </Callout>

                {generatedKey ? (
                  <Card variant="inset" padding="compact">
                    <div className="flex items-start gap-3">
                      <Key className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="text-ui font-medium text-re-text-primary">API Key generated</p>
                        <p className="text-small text-re-text-tertiary">
                          Copy and store this key securely. It will not be displayed again.
                        </p>
                        <div className="mt-3 flex items-center gap-2">
                          <code className="min-w-0 flex-1 break-all rounded-md border border-re-border-subtle bg-re-surface-card p-2 font-mono text-[0.8125rem] text-re-text-primary">
                            {generatedKey}
                          </code>
                          <Button
                            size="icon"
                            variant="outline"
                            aria-label="Copy API key"
                            className="shrink-0"
                            onClick={() => navigator.clipboard.writeText(generatedKey)}
                          >
                            <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                          </Button>
                        </div>
                        <Button
                          size="sm"
                          className="mt-3"
                          onClick={() => void handleUseApiKey(generatedKey, () => setGeneratedKey(null))}
                          leadingIcon={<CheckCircle strokeWidth={1.75} aria-hidden="true" />}
                        >
                          Use as my API Key
                        </Button>
                      </div>
                    </div>
                  </Card>
                ) : (
                  <p className="text-ui text-re-text-secondary">
                    Click &quot;Generate API Key&quot; to create a new credential instantly.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* New Key Creation */}
            <Card>
              <CardHeader>
                <div className="min-w-0">
                  <CardTitle>Create New API Key</CardTitle>
                  <CardDescription>
                    Generate a new API key for accessing RegEngine services
                  </CardDescription>
                </div>
                {!isCreating && (
                  <Button
                    className="shrink-0"
                    onClick={() => setIsCreating(true)}
                    leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                  >
                    New Key
                  </Button>
                )}
              </CardHeader>
              {isCreating && (
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <label htmlFor="admin-new-key-description" className="sr-only">Description (optional)</label>
                      <Input
                        id="admin-new-key-description"
                        placeholder="Description (optional)"
                        value={newKeyDescription}
                        onChange={(e) => setNewKeyDescription(e.target.value)}
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={handleCreateKey}
                        disabled={createKeyMutation.isPending}
                        loading={createKeyMutation.isPending}
                      >
                        {createKeyMutation.isPending ? 'Creating...' : 'Create Key'}
                      </Button>
                      <Button variant="outline" onClick={() => setIsCreating(false)}>
                        Cancel
                      </Button>
                    </div>
                  </div>

                  {copiedKey && (
                    <Callout
                      tone="success"
                      icon={CheckCircle}
                      title="API Key Created Successfully"
                      className="mt-4"
                    >
                      <p>Save this key now. It won&apos;t be shown again!</p>
                      <div className="mt-2 flex items-center gap-2">
                        <code className="min-w-0 flex-1 break-all rounded-md border border-re-border-subtle bg-re-surface-inset p-2 font-mono text-[0.8125rem] text-re-text-primary">
                          {copiedKey}
                        </code>
                        <Button
                          size="icon"
                          variant="outline"
                          aria-label="Copy API key"
                          className="shrink-0"
                          onClick={() => copyToClipboard(copiedKey)}
                        >
                          <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        </Button>
                      </div>
                      <Button
                        size="sm"
                        className="mt-3"
                        onClick={() => void handleUseApiKey(copiedKey, () => setCopiedKey(null))}
                        leadingIcon={<CheckCircle strokeWidth={1.75} aria-hidden="true" />}
                      >
                        Use as my API Key
                      </Button>
                      <p className="mt-2 text-small text-re-text-tertiary">
                        This will save the key in your browser for easy access across pages.
                      </p>
                    </Callout>
                  )}
                </CardContent>
              )}
            </Card>

            {/* API Keys List */}
            <Card>
              <CardHeader>
                <div className="min-w-0">
                  <CardTitle>API Keys</CardTitle>
                  <CardDescription>
                    Manage existing API keys
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {isLoading ? (
                  <div className="space-y-2 p-5" aria-busy="true">
                    {[0, 1, 2].map((row) => (
                      <Skeleton key={row} className="h-16 w-full" />
                    ))}
                  </div>
                ) : apiKeys && apiKeys.length > 0 ? (
                  <ul className="divide-y divide-re-border-subtle">
                    {apiKeys.map((key) => (
                      <li
                        key={key.key_id}
                        className="flex items-center justify-between gap-3 px-5 py-4 transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="mb-1 flex flex-wrap items-center gap-3">
                            <Key className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <code className="font-mono text-[0.8125rem] text-re-text-primary">{key.key_id}</code>
                            <StatusBadge state="compliant" label="Active" size="sm" />
                          </div>
                          {key.description && (
                            <p className="ml-7 text-ui text-re-text-secondary">
                              {key.description}
                            </p>
                          )}
                          <p className="ml-7 mt-1 font-mono text-small text-re-text-tertiary">
                            Created {formatDate(key.created_at)}
                          </p>
                        </div>
                        <Button
                          variant="destructive"
                          size="icon"
                          aria-label="Revoke API key"
                          className="shrink-0"
                          onClick={() => key.key_id && setPendingRevokeKeyId(key.key_id)}
                          disabled={revokeKeyMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState bare icon={Key} title="No API keys found" />
                )}
              </CardContent>
            </Card>
          </>
        )}

        <Dialog open={pendingRevokeKeyId !== null} onOpenChange={(open) => { if (!open) setPendingRevokeKeyId(null); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Revoke this API key?</DialogTitle>
              <DialogDescription>
                Anything using this key will immediately lose access. This cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPendingRevokeKeyId(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={() => pendingRevokeKeyId && handleRevokeKey(pendingRevokeKeyId)}
                disabled={revokeKeyMutation.isPending}
              >
                Revoke Key
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </PageContainer>
  );
}
