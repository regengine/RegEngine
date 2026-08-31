'use client';

import { useState } from 'react';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { useAuth } from '@/lib/auth-context';
import { useAPIKeys, useCreateAPIKey, useGenerateAPIKey, useRevokeAPIKey } from '@/hooks/use-api';
import { Key, Plus, Trash2, CheckCircle, Copy, Shield, AlertCircle, ArrowRight } from 'lucide-react';
import { formatDate } from '@/lib/utils';

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
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-6xl mx-auto"
        >
          {/* Page Header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-orange-100 dark:bg-orange-900">
              <Key className="h-8 w-8 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <h1 className="text-3xl sm:text-4xl font-bold">API Management</h1>
              <p className="text-muted-foreground mt-1">
                Manage API keys and access controls
              </p>
            </div>
          </div>

          {apiKeySaveError && (
            <div role="alert" className="mb-6 p-3 rounded-lg bg-re-danger-muted dark:bg-re-danger/20 border border-re-danger">
              <p className="text-sm text-re-danger">{apiKeySaveError}</p>
            </div>
          )}

          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Admin Shortcuts</CardTitle>
              <CardDescription>
                Jump directly to operational consoles.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              {experimentalFeaturesEnabled() && (
                <Link href="/admin/alerts">
                  <Button variant="outline">
                    Alert Center
                  </Button>
                </Link>
              )}
              <Link href="/admin/api-console">
                <Button variant="outline">
                  API Console
                </Button>
              </Link>
            </CardContent>
          </Card>

          {!canManageKeys && (
            <Card className="mb-8">
              <CardHeader>
                <CardTitle>High-assurance sign-in required</CardTitle>
                <CardDescription>
                  Live credential management requires a WebAuthn or SSO sysadmin session.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 rounded-lg border border-primary/30 bg-primary/5">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-full bg-primary/10">
                      <Shield className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-medium">Use your staff identity</h4>
                      <p className="text-sm text-muted-foreground mt-1">
                        Email-code-only sessions cannot create or revoke live credentials. Sign in with an approved passkey or SSO account.
                      </p>
                      <Link href="/login?next=/admin">
                        <Button size="sm" variant="outline" className="mt-2">
                          Sign in securely
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {canManageKeys && (
            <>
              {error && (
                <div className="mb-6 p-3 rounded-lg bg-re-danger-muted dark:bg-re-danger/20 border border-re-danger">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 text-re-danger mt-0.5" />
                    <p className="text-sm text-re-danger">
                      This session is not authorized to manage live credentials.
                    </p>
                  </div>
                </div>
              )}
              {/* Quick Generate API Key */}
              <Card className="mb-8">
                <CardHeader className="flex flex-col gap-2">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                      <CardTitle>Developer Settings</CardTitle>
                      <CardDescription>
                        Generate and manage developer credentials without leaving the console.
                      </CardDescription>
                    </div>
                    <Button
                      onClick={handleGenerateKey}
                      disabled={generateKeyMutation.isPending}
                    >
                      {generateKeyMutation.isPending ? (
                        <>
                          <Spinner size="sm" className="mr-2" />
                          Generating...
                        </>
                      ) : (
                        'Generate New API Key'
                      )}
                    </Button>
                  </div>
                  <p className="text-sm text-re-warning dark:text-re-warning flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    This will not be shown again. Copy and store the key securely.
                  </p>
                </CardHeader>
                <CardContent>
                  {generatedKey ? (
                    <div className="p-4 rounded-lg border bg-muted/40 space-y-3">
                      <div className="flex items-start gap-3">
                        <Key className="h-5 w-5 text-primary mt-0.5" />
                        <div className="flex-1">
                          <p className="font-semibold">API Key generated</p>
                          <p className="text-sm text-muted-foreground">
                            Copy and store this key securely. It will not be displayed again.
                          </p>
                          <div className="flex items-center gap-2 mt-3">
                            <code className="flex-1 text-sm bg-background p-2 rounded font-mono break-all">
                              {generatedKey}
                            </code>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => navigator.clipboard.writeText(generatedKey)}
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                          </div>
                          <Button
                            size="sm"
                            className="mt-3"
                            onClick={() => void handleUseApiKey(generatedKey, () => setGeneratedKey(null))}
                          >
                            <CheckCircle className="h-4 w-4 mr-2" />
                            Use as my API Key
                          </Button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Click &quot;Generate API Key&quot; to create a new credential instantly.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* New Key Creation */}
              <Card className="mb-8">
                <CardHeader>
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                      <CardTitle>Create New API Key</CardTitle>
                      <CardDescription>
                        Generate a new API key for accessing RegEngine services
                      </CardDescription>
                    </div>
                    {!isCreating && (
                      <Button onClick={() => setIsCreating(true)}>
                        <Plus className="h-4 w-4 mr-2" />
                        New Key
                      </Button>
                    )}
                  </div>
                </CardHeader>
                {isCreating && (
                  <CardContent>
                    <div className="space-y-4">
                      <Input
                        placeholder="Description (optional)"
                        value={newKeyDescription}
                        onChange={(e) => setNewKeyDescription(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <Button
                          onClick={handleCreateKey}
                          disabled={createKeyMutation.isPending}
                        >
                          {createKeyMutation.isPending ? (
                            <>
                              <Spinner size="sm" className="mr-2" />
                              Creating...
                            </>
                          ) : (
                            'Create Key'
                          )}
                        </Button>
                        <Button variant="outline" onClick={() => setIsCreating(false)}>
                          Cancel
                        </Button>
                      </div>
                    </div>

                    {copiedKey && (
                      <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="mt-4 p-4 rounded-lg bg-re-success-muted dark:bg-re-success/20 border border-green-200 dark:border-green-800"
                      >
                        <div className="flex items-start gap-3">
                          <CheckCircle className="h-5 w-5 text-re-success dark:text-re-success mt-0.5" />
                          <div className="flex-1">
                            <h4 className="font-semibold text-re-success dark:text-green-100 mb-2">
                              API Key Created Successfully
                            </h4>
                            <p className="text-sm text-re-success dark:text-re-success mb-2">
                              Save this key now - it won&apos;t be shown again!
                            </p>
                            <div className="flex items-center gap-2">
                              <code className="flex-1 text-sm bg-white dark:bg-re-surface-card p-2 rounded font-mono break-all">
                                {copiedKey}
                              </code>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => copyToClipboard(copiedKey)}
                              >
                                <Copy className="h-4 w-4" />
                              </Button>
                            </div>
                            <Button
                              size="sm"
                              className="mt-3"
                              onClick={() => void handleUseApiKey(copiedKey, () => setCopiedKey(null))}
                            >
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Use as my API Key
                            </Button>
                            <p className="text-xs text-re-success dark:text-re-success mt-2">
                              This will save the key in your browser for easy access across pages.
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </CardContent>
                )}
              </Card>

              {/* API Keys List */}
              <Card>
                <CardHeader>
                  <CardTitle>API Keys</CardTitle>
                  <CardDescription>
                    Manage existing API keys
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="flex justify-center py-8">
                      <Spinner size="md" />
                    </div>
                  ) : apiKeys && apiKeys.length > 0 ? (
                    <div className="space-y-3">
                      {apiKeys.map((key) => (
                        <motion.div
                          key={key.key_id}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent smooth-transition"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-3 mb-1">
                              <Key className="h-4 w-4 text-muted-foreground" />
                              <code className="text-sm font-mono">{key.key_id}</code>
                              <Badge variant="secondary">Active</Badge>
                            </div>
                            {key.description && (
                              <p className="text-sm text-muted-foreground ml-7">
                                {key.description}
                              </p>
                            )}
                            <p className="text-xs text-muted-foreground ml-7 mt-1">
                              Created {formatDate(key.created_at)}
                            </p>
                          </div>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => key.key_id && setPendingRevokeKeyId(key.key_id)}
                            disabled={revokeKeyMutation.isPending}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </motion.div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <Key className="h-12 w-12 mx-auto mb-3 text-muted-foreground" />
                      <p className="text-muted-foreground">No API keys found</p>
                    </div>
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
        </motion.div>
      </PageContainer>
    </div>
  );
}
