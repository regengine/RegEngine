'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { HelpTooltip } from '@/components/ui/tooltip';
import { useAuth } from '@/lib/auth-context';
import { useAPIKeys, useCreateAPIKey, useGenerateAPIKey, useRevokeAPIKey } from '@/hooks/use-api';
import { Key, Plus, Trash2, CheckCircle, Copy, Shield, Terminal, AlertCircle, ArrowRight } from 'lucide-react';
import { formatDate } from '@/lib/utils';

export default function AdminPage() {
  const { adminKey: storedAdminKey, setAdminKey: storeAdminKey, setApiKey: storeApiKey, tenantId } = useAuth();
  const [adminKey, setAdminKey] = useState('');
  const [newKeyDescription, setNewKeyDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [authError, setAuthError] = useState(false);

  const { data: apiKeys, isLoading, refetch, error } = useAPIKeys(adminKey, !!adminKey);
  const createKeyMutation = useCreateAPIKey();
  const generateKeyMutation = useGenerateAPIKey();
  const revokeKeyMutation = useRevokeAPIKey();

  // Initialize from stored admin key
  useEffect(() => {
    if (storedAdminKey && !adminKey) {
      setAdminKey(storedAdminKey);
    }
  }, [storedAdminKey, adminKey]);

  // Handle auth errors
  useEffect(() => {
    if (error) {
      setAuthError(true);
    } else if (apiKeys) {
      setAuthError(false);
      // Store the admin key if authentication was successful
      if (adminKey && adminKey !== storedAdminKey) {
        storeAdminKey(adminKey);
      }
    }
  }, [error, apiKeys, adminKey, storedAdminKey, storeAdminKey]);

  const handleCreateKey = async () => {
    if (!adminKey) return;

    try {
      const result = await createKeyMutation.mutateAsync({
        adminKey,
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
    if (!adminKey) return;

    try {
      const result = await generateKeyMutation.mutateAsync({ adminKey, tenantId: tenantId || undefined });
      if (result.api_key) {
        setGeneratedKey(result.api_key);
      }
    } catch (error) {
      console.error('Failed to generate API key:', error);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!adminKey || !confirm('Are you sure you want to revoke this API key?')) return;

    try {
      await revokeKeyMutation.mutateAsync({ adminKey, keyId });
      refetch();
    } catch (error) {
      console.error('Failed to revoke API key:', error);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setTimeout(() => setCopiedKey(null), 2000);
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
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-orange-100 dark:bg-orange-900">
              <Key className="h-8 w-8 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">API Management</h1>
              <p className="text-muted-foreground mt-1">
                Manage API keys and access controls
              </p>
            </div>
          </div>

          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Admin Shortcuts</CardTitle>
              <CardDescription>
                Jump directly to operational consoles.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              <Link href="/admin/alerts">
                <Button variant="outline">
                  Alert Center
                </Button>
              </Link>
              <Link href="/admin/api-console">
                <Button variant="outline">
                  API Console
                </Button>
              </Link>
            </CardContent>
          </Card>

          {/* Admin Key Input */}
          {!adminKey && (
            <Card className="mb-8">
              <CardHeader>
                <CardTitle>Authentication Required</CardTitle>
                <CardDescription>
                  Enter your admin master key to manage API keys
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    refetch();
                  }}
                  className="flex gap-4"
                >
                  <Input
                    type="password"
                    placeholder="Enter admin master key"
                    value={adminKey}
                    onChange={(e) => {
                      setAdminKey(e.target.value);
                      setAuthError(false);
                    }}
                  />
                  <Button type="submit">
                    <Shield className="h-4 w-4 mr-2" />
                    Authenticate
                  </Button>
                </form>

                {authError && (
                  <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5" />
                      <p className="text-sm text-red-700 dark:text-red-300">
                        Invalid admin key. Please check your key and try again.
                      </p>
                    </div>
                  </div>
                )}

                {/* Help Section */}
                <div className="p-4 rounded-lg bg-muted/50 border">
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <Terminal className="h-4 w-4" />
                    Where to find your Admin Master Key
                  </h4>
                  <p className="text-sm text-muted-foreground mb-3">
                    The Admin Master Key is set in your environment configuration. You can find it in your <code className="bg-muted px-1 rounded">.env</code> file:
                  </p>
                  <pre className="bg-gray-900 text-gray-100 p-3 rounded text-sm overflow-x-auto">
                    <code>ADMIN_MASTER_KEY=your_key_here</code>
                  </pre>
                  <p className="text-sm text-muted-foreground mt-3">
                    If you haven&apos;t set one up yet, generate a secure key:
                  </p>
                  <pre className="bg-gray-900 text-gray-100 p-3 rounded text-sm overflow-x-auto mt-2">
                    <code>openssl rand -hex 32</code>
                  </pre>
                </div>

                {/* Alternative: Onboarding Wizard */}
                <div className="p-4 rounded-lg border border-primary/30 bg-primary/5">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded-full bg-primary/10">
                      <Key className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-medium">First time here?</h4>
                      <p className="text-sm text-muted-foreground mt-1">
                        Use our setup wizard for a guided experience to get your first API key.
                      </p>
                      <Link href="/onboarding">
                        <Button size="sm" variant="outline" className="mt-2">
                          Go to Setup Wizard
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Authenticated View */}
          {adminKey && (
            <>
              {/* Quick Generate API Key */}
              <Card className="mb-8">
                <CardHeader className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
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
                  <p className="text-sm text-amber-700 dark:text-amber-300 flex items-center gap-2">
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
                            onClick={() => {
                              storeApiKey(generatedKey);
                              setGeneratedKey(null);
                            }}
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
                  <div className="flex items-center justify-between">
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
                        className="mt-4 p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800"
                      >
                        <div className="flex items-start gap-3">
                          <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400 mt-0.5" />
                          <div className="flex-1">
                            <h4 className="font-semibold text-green-900 dark:text-green-100 mb-2">
                              API Key Created Successfully
                            </h4>
                            <p className="text-sm text-green-700 dark:text-green-300 mb-2">
                              Save this key now - it won&apos;t be shown again!
                            </p>
                            <div className="flex items-center gap-2">
                              <code className="flex-1 text-sm bg-white dark:bg-gray-800 p-2 rounded font-mono break-all">
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
                              onClick={() => {
                                storeApiKey(copiedKey);
                                setCopiedKey(null);
                              }}
                            >
                              <CheckCircle className="h-4 w-4 mr-2" />
                              Use as my API Key
                            </Button>
                            <p className="text-xs text-green-600 dark:text-green-400 mt-2">
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
                            onClick={() => key.key_id && handleRevokeKey(key.key_id)}
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
        </motion.div>
      </PageContainer>
    </div>
  );
}
