'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useRouter } from 'next/navigation';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { useAuth } from '@/lib/auth-context';
import {
  useAdminHealth,
  useIngestionHealth,
  useCreateAPIKey,
  useIngestURL,
  useCreateTenant,
} from '@/hooks/use-api';
import {
  Rocket,
  CheckCircle,
  XCircle,
  Key,
  Upload,
  ArrowRight,
  ArrowLeft,
  Copy,
  Terminal,
  Sparkles,
  ExternalLink,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';

type OnboardingStep = 'welcome' | 'health' | 'credentials' | 'first-ingest' | 'complete';

const DEMO_DOCUMENT_URL = 'https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-21.xml?chapter=I&subchapter=A&part=1';

export default function OnboardingPage() {
  const router = useRouter();
  const { apiKey, adminKey, tenantId, setApiKey, setAdminKey, setTenantId, completeOnboarding, isOnboarded } = useAuth();

  const [currentStep, setCurrentStep] = useState<OnboardingStep>('welcome');
  const [adminKeyInput, setAdminKeyInput] = useState('');
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [credentialMethod, setCredentialMethod] = useState<'admin' | 'existing' | 'cli' | null>(null);
  const [existingApiKey, setExistingApiKey] = useState('');
  const [tenantName, setTenantName] = useState('');

  // Cloud deployment detection — on Vercel, backend services don't exist
  const [isCloudMode, setIsCloudMode] = useState(false);
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const host = window.location.hostname;
      setIsCloudMode(host !== 'localhost' && host !== '127.0.0.1');
    }
  }, []);

  // Health checks
  const adminHealth = useAdminHealth();
  const ingestionHealth = useIngestionHealth();

  // Mutations
  const createKeyMutation = useCreateAPIKey();
  const createTenantMutation = useCreateTenant();
  const ingestMutation = useIngestURL();

  // System status derived state — cloud mode bypasses the gate
  const allServicesHealthy =
    isCloudMode ||
    (adminHealth.data?.status === 'healthy' &&
      ingestionHealth.data?.status === 'healthy');

  useEffect(() => {
    // If user is already onboarded, redirect to dashboard
    if (isOnboarded) {
      router.push('/dashboard');
    }
  }, [isOnboarded, router]);

  const handleCreateTenant = async () => {
    if (!adminKeyInput || !tenantName) return;

    try {
      const tenantResponse = await createTenantMutation.mutateAsync({
        adminKey: adminKeyInput,
        name: tenantName || 'New Tenant',
      });
      const result = await createKeyMutation.mutateAsync({
        adminKey: adminKeyInput,
        name: 'Onboarding API Key',
        description: 'Created via onboarding wizard',
        tenantId: tenantResponse.tenant_id,
      });

      if (result.api_key) {
        setNewApiKey(result.api_key);
        setApiKey(result.api_key);
        setAdminKey(adminKeyInput);
        setTenantId(tenantResponse.tenant_id || null);
        completeOnboarding();
        router.push('/dashboard');
      }
    } catch (error) {
      console.error('Failed to create API key:', error);
    }
  };

  const handleUseExistingKey = () => {
    if (existingApiKey) {
      setApiKey(existingApiKey);
      setCurrentStep('first-ingest');
    }
  };

  const handleDemoIngest = async () => {
    if (!apiKey) return;

    try {
      await ingestMutation.mutateAsync({
        apiKey,
        url: DEMO_DOCUMENT_URL,
      });
    } catch (error) {
      console.error('Demo ingest failed:', error);
    }
  };

  const handleComplete = () => {
    completeOnboarding();
    router.push('/');
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const steps: { id: OnboardingStep; title: string; number: number }[] = [
    { id: 'welcome', title: 'Welcome', number: 1 },
    { id: 'health', title: 'System Check', number: 2 },
    { id: 'credentials', title: 'Credentials', number: 3 },
    { id: 'first-ingest', title: 'First Document', number: 4 },
    { id: 'complete', title: 'Complete', number: 5 },
  ];

  const currentStepIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <div className="min-h-screen" style={{ background: '#06090f' }}>
      <PageContainer>
        <div className="max-w-2xl mx-auto">
          {/* Progress indicator */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-2">
              {steps.map((step, index) => (
                <div key={step.id} className="flex items-center">
                  <div
                    className={`
                      w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                      ${index < currentStepIndex ? 'bg-primary text-primary-foreground' : ''}
                      ${index === currentStepIndex ? 'bg-primary text-primary-foreground ring-4 ring-primary/20' : ''}
                      ${index > currentStepIndex ? 'bg-muted text-muted-foreground' : ''}
                    `}
                  >
                    {index < currentStepIndex ? <CheckCircle className="w-4 h-4" /> : step.number}
                  </div>
                  {index < steps.length - 1 && (
                    <div
                      className={`w-12 sm:w-20 h-1 mx-1 ${index < currentStepIndex ? 'bg-primary' : 'bg-muted'
                        }`}
                    />
                  )}
                </div>
              ))}
            </div>
            <p className="text-center text-sm text-muted-foreground">
              Step {currentStepIndex + 1} of {steps.length}: {steps[currentStepIndex]?.title}
            </p>
          </div>

          <AnimatePresence mode="wait">
            {/* Step 1: Welcome */}
            {currentStep === 'welcome' && (
              <motion.div
                key="welcome"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <Card>
                  <CardHeader className="text-center">
                    <div className="mx-auto mb-4 p-4 rounded-full bg-primary/10">
                      <Rocket className="w-12 h-12 text-primary" />
                    </div>
                    <CardTitle className="text-3xl">Welcome to RegEngine</CardTitle>
                    <CardDescription className="text-lg">
                      Let&apos;s get you set up in just a few minutes
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="grid gap-4">
                      <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
                        <CheckCircle className="w-5 h-5 text-green-500 mt-0.5" />
                        <div>
                          <p className="font-medium">Verify services are running</p>
                          <p className="text-sm text-muted-foreground">We&apos;ll check that all backend services are healthy</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
                        <Key className="w-5 h-5 text-blue-500 mt-0.5" />
                        <div>
                          <p className="font-medium">Set up your API key</p>
                          <p className="text-sm text-muted-foreground">Create or enter credentials to access the platform</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/50">
                        <Upload className="w-5 h-5 text-purple-500 mt-0.5" />
                        <div>
                          <p className="font-medium">Ingest your first document</p>
                          <p className="text-sm text-muted-foreground">See the platform in action with a sample regulatory document</p>
                        </div>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <Button className="flex-1" onClick={() => setCurrentStep('health')}>
                        Get Started
                        <ArrowRight className="ml-2 w-4 h-4" />
                      </Button>
                      {apiKey && (
                        <Button variant="outline" onClick={handleComplete}>
                          Skip (I have credentials)
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* Step 2: Health Check */}
            {currentStep === 'health' && (
              <motion.div
                key="health"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle>System Health Check</CardTitle>
                    <CardDescription>
                      {isCloudMode
                        ? 'Cloud deployment detected — backend services connect separately'
                        : 'Verifying that all RegEngine services are running'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {isCloudMode ? (
                      <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                        <div className="flex items-start gap-3">
                          <Sparkles className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5" />
                          <div>
                            <p className="font-medium text-blue-900 dark:text-blue-100">
                              Cloud Mode
                            </p>
                            <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                              You&apos;re on the hosted version of RegEngine. Backend services
                              (Admin API, Ingestion) are configured separately. You can continue
                              to set up your credentials.
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="space-y-3">
                          <ServiceHealthItem
                            name="Admin Service"
                            port={8400}
                            isLoading={adminHealth.isLoading}
                            isHealthy={adminHealth.data?.status === 'healthy'}
                            error={adminHealth.error}
                          />
                          <ServiceHealthItem
                            name="Ingestion Service"
                            port={8000}
                            isLoading={ingestionHealth.isLoading}
                            isHealthy={ingestionHealth.data?.status === 'healthy'}
                            error={ingestionHealth.error}
                          />
                        </div>

                        {!allServicesHealthy && !adminHealth.isLoading && !ingestionHealth.isLoading && (
                          <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                            <div className="flex items-start gap-3">
                              <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5" />
                              <div>
                                <p className="font-medium text-amber-900 dark:text-amber-100">
                                  Services not ready
                                </p>
                                <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                                  Make sure you&apos;ve started the backend services:
                                </p>
                                <code className="block mt-2 p-2 bg-amber-100 dark:bg-amber-900/40 rounded text-sm font-mono">
                                  make up
                                </code>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="mt-3"
                                  onClick={() => {
                                    adminHealth.refetch();
                                    ingestionHealth.refetch();
                                  }}
                                >
                                  <RefreshCw className="w-4 h-4 mr-2" />
                                  Retry Check
                                </Button>
                              </div>
                            </div>
                          </div>
                        )}
                      </>
                    )}

                    <div className="flex gap-3">
                      <Button variant="outline" onClick={() => setCurrentStep('welcome')}>
                        <ArrowLeft className="mr-2 w-4 h-4" />
                        Back
                      </Button>
                      <Button
                        className="flex-1"
                        onClick={() => setCurrentStep('credentials')}
                        disabled={!allServicesHealthy}
                      >
                        Continue
                        <ArrowRight className="ml-2 w-4 h-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* Step 3: Credentials */}
            {currentStep === 'credentials' && (
              <motion.div
                key="credentials"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle>Set Up Your Credentials</CardTitle>
                    <CardDescription>
                      Choose how you want to authenticate with RegEngine
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {!credentialMethod && (
                      <div className="grid gap-3">
                        <button
                          className="flex items-start gap-4 p-4 rounded-lg border hover:border-primary hover:bg-accent transition-colors text-left"
                          onClick={() => setCredentialMethod('admin')}
                        >
                          <Key className="w-6 h-6 text-primary mt-0.5" />
                          <div>
                            <p className="font-medium">I have an Admin Master Key</p>
                            <p className="text-sm text-muted-foreground">
                              Create a new API key using your admin credentials
                            </p>
                          </div>
                        </button>

                        <button
                          className="flex items-start gap-4 p-4 rounded-lg border hover:border-primary hover:bg-accent transition-colors text-left"
                          onClick={() => setCredentialMethod('existing')}
                        >
                          <CheckCircle className="w-6 h-6 text-green-500 mt-0.5" />
                          <div>
                            <p className="font-medium">I already have an API Key</p>
                            <p className="text-sm text-muted-foreground">
                              Enter an existing key to link this session
                            </p>
                          </div>
                        </button>

                        <button
                          className="flex items-start gap-4 p-4 rounded-lg border hover:border-primary hover:bg-accent transition-colors text-left"
                          onClick={() => setCredentialMethod('cli')}
                        >
                          <Terminal className="w-6 h-6 text-orange-500 mt-0.5" />
                          <div>
                            <p className="font-medium">Create via CLI / Console</p>
                            <p className="text-sm text-muted-foreground">
                              Generate a new tenant and key using the command line
                            </p>
                          </div>
                        </button>
                      </div>
                    )}

                    {/* Admin Key Method */}
                    {credentialMethod === 'admin' && (
                      <div className="space-y-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setCredentialMethod(null)}
                        >
                          <ArrowLeft className="w-4 h-4 mr-2" />
                          Back to options
                        </Button>

                        <div>
                          <label className="text-sm font-medium mb-2 block" htmlFor="tenant-name">
                            Tenant or Organization Name
                          </label>
                          <Input
                            id="tenant-name"
                            placeholder="Acme Corp"
                            value={tenantName}
                            onChange={(e) => setTenantName(e.target.value)}
                          />
                        </div>

                        {createKeyMutation.isError || createTenantMutation.isError ? (
                          <div
                            id="onboarding-error"
                            role="alert"
                            className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm"
                          >
                            Failed to create tenant or API key. Please check your admin key and try again.
                          </div>
                        ) : null}

                        <div>
                          <label className="text-sm font-medium mb-2 block" htmlFor="admin-key">
                            Admin Master Key
                          </label>
                          <Input
                            id="admin-key"
                            type="password"
                            placeholder="Enter your admin master key"
                            value={adminKeyInput}
                            onChange={(e) => setAdminKeyInput(e.target.value)}
                            aria-invalid={createKeyMutation.isError || createTenantMutation.isError}
                            aria-describedby="onboarding-error"
                          />
                        </div>

                        <Button
                          className="w-full"
                          onClick={handleCreateTenant}
                          disabled={!adminKeyInput || !tenantName || createKeyMutation.isPending || createTenantMutation.isPending}
                        >
                          {createKeyMutation.isPending || createTenantMutation.isPending ? (
                            <>
                              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                              Creating Tenant...
                            </>
                          ) : (
                            <>
                              Create Tenant & Key
                              <ArrowRight className="ml-2 w-4 h-4" />
                            </>
                          )}
                        </Button>
                      </div>
                    )}

                    {/* Existing API Key Method */}
                    {credentialMethod === 'existing' && (
                      <div className="space-y-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setCredentialMethod(null)}
                        >
                          <ArrowLeft className="w-4 h-4 mr-2" />
                          Back to options
                        </Button>

                        <div>
                          <label className="text-sm font-medium mb-2 block" htmlFor="existing-api-key">
                            Your API Key
                          </label>
                          <p className="text-sm text-muted-foreground mb-2">
                            Starts with <code className="bg-muted px-1 rounded">rge_</code>
                          </p>
                          <Input
                            id="existing-api-key"
                            type="password"
                            placeholder="rge_..."
                            value={existingApiKey}
                            onChange={(e) => setExistingApiKey(e.target.value)}
                          />
                        </div>

                        <Button
                          className="w-full"
                          onClick={handleUseExistingKey}
                          disabled={!existingApiKey}
                        >
                          Use This Key
                          <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                      </div>
                    )}

                    {/* CLI Method */}
                    {credentialMethod === 'cli' && (
                      <div className="space-y-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setCredentialMethod(null)}
                        >
                          <ArrowLeft className="w-4 h-4 mr-2" />
                          Back to options
                        </Button>

                        <div className="p-4 rounded-lg bg-slate-950 text-slate-50 font-mono text-sm overflow-x-auto">
                          <div className="flex items-center justify-between mb-2 text-slate-400">
                            <span>Terminal</span>
                            <div className="flex gap-1.5">
                              <div className="w-3 h-3 rounded-full bg-red-500/20" />
                              <div className="w-3 h-3 rounded-full bg-yellow-500/20" />
                              <div className="w-3 h-3 rounded-full bg-green-500/20" />
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-green-400">$</span>
                            <span>curl -X POST https://api.regengine.co/v1/tenants/init</span>
                          </div>
                          <div className="mt-4 flex justify-end">
                            <Button
                              variant="secondary"
                              size="sm"
                              className="h-8 text-xs"
                              onClick={() => copyToClipboard('curl -X POST https://api.regengine.co/v1/tenants/init')}
                            >
                              {copied ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                            </Button>
                          </div>
                        </div>
                        <p className="text-sm text-muted-foreground mt-3">
                          This will create a new tenant with sample data and display your API key.
                        </p>

                        <div className="p-4 rounded-lg border">
                          <p className="font-medium mb-2">After running the command:</p>
                          <div>
                            <label className="text-sm font-medium mb-2 block" htmlFor="cli-api-key">
                              Enter the API Key from the output
                            </label>
                            <Input
                              id="cli-api-key"
                              type="password"
                              placeholder="rge_..."
                              value={existingApiKey}
                              onChange={(e) => setExistingApiKey(e.target.value)}
                            />
                          </div>
                          <Button
                            className="w-full mt-3"
                            onClick={handleUseExistingKey}
                            disabled={!existingApiKey}
                          >
                            Continue
                            <ArrowRight className="ml-2 w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Navigation Footer */}
                    {!credentialMethod && (
                      <div className="flex gap-3">
                        <Button variant="outline" onClick={() => setCurrentStep('health')}>
                          <ArrowLeft className="mr-2 w-4 h-4" />
                          Back
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* Step 4: First Ingest */}
            {currentStep === 'first-ingest' && (
              <motion.div
                key="first-ingest"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle>Ingest Your First Document</CardTitle>
                    <CardDescription>
                      Let&apos;s see RegEngine in action with a sample regulatory document
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="font-medium mb-2">Sample Document</p>
                      <p className="text-sm text-muted-foreground mb-2">
                        We&apos;ll ingest a section of FDA regulations (21 CFR Part 1)
                      </p>
                      <code className="text-xs break-all block p-2 bg-background rounded">
                        {DEMO_DOCUMENT_URL}
                      </code>
                    </div>

                    {ingestMutation.isSuccess && (
                      <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
                        <div className="flex items-start gap-3">
                          <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 mt-0.5" />
                          <div>
                            <p className="font-semibold text-green-900 dark:text-green-100">
                              Document Submitted!
                            </p>
                            <p className="text-sm text-green-700 dark:text-green-300 mt-1">
                              Document ID: <code className="font-mono">{ingestMutation.data?.doc_id}</code>
                            </p>
                            <p className="text-sm text-green-700 dark:text-green-300">
                              The document is now being processed through the NLP pipeline.
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    {ingestMutation.isError && (
                      <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                        <div className="flex items-start gap-3">
                          <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" />
                          <div>
                            <p className="font-semibold text-red-900 dark:text-red-100">
                              Ingestion Failed
                            </p>
                            <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                              {ingestMutation.error?.message || 'An error occurred. You can try again or skip this step.'}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="flex gap-3">
                      <Button variant="outline" onClick={() => setCurrentStep('credentials')}>
                        <ArrowLeft className="mr-2 w-4 h-4" />
                        Back
                      </Button>

                      {!ingestMutation.isSuccess ? (
                        <Button
                          className="flex-1"
                          onClick={handleDemoIngest}
                          disabled={ingestMutation.isPending}
                        >
                          {ingestMutation.isPending ? (
                            <>
                              <Spinner size="sm" className="mr-2" />
                              Ingesting...
                            </>
                          ) : (
                            <>
                              <Upload className="w-4 h-4 mr-2" />
                              Ingest Sample Document
                            </>
                          )}
                        </Button>
                      ) : (
                        <Button className="flex-1" onClick={() => setCurrentStep('complete')}>
                          Continue
                          <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                      )}

                      <Button variant="ghost" onClick={() => setCurrentStep('complete')}>
                        Skip
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* Step 5: Complete */}
            {currentStep === 'complete' && (
              <motion.div
                key="complete"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
              >
                <Card>
                  <CardHeader className="text-center">
                    <div className="mx-auto mb-4 p-4 rounded-full bg-green-100 dark:bg-green-900/30">
                      <CheckCircle className="w-12 h-12 text-green-600 dark:text-green-400" />
                    </div>
                    <CardTitle className="text-3xl">You&apos;re All Set!</CardTitle>
                    <CardDescription className="text-lg">
                      RegEngine is ready to use
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="p-4 rounded-lg bg-muted/50">
                      <p className="font-medium mb-2">Your API Key is saved</p>
                      <p className="text-sm text-muted-foreground">
                        Your credentials are stored in this browser. You won&apos;t need to enter them again.
                      </p>
                    </div>

                    <div className="grid gap-3">
                      <p className="font-medium">What&apos;s next?</p>
                      <a
                        href="/ingest"
                        className="flex items-center gap-3 p-3 rounded-lg border hover:bg-accent transition-colors"
                      >
                        <Upload className="w-5 h-5 text-blue-500" />
                        <div className="flex-1">
                          <p className="font-medium">Ingest More Documents</p>
                          <p className="text-sm text-muted-foreground">Add your own regulatory documents</p>
                        </div>
                        <ExternalLink className="w-4 h-4 text-muted-foreground" />
                      </a>
                      <a
                        href="/compliance"
                        className="flex items-center gap-3 p-3 rounded-lg border hover:bg-accent transition-colors"
                      >
                        <CheckCircle className="w-5 h-5 text-green-500" />
                        <div className="flex-1">
                          <p className="font-medium">Browse Compliance Checklists</p>
                          <p className="text-sm text-muted-foreground">Explore pre-built compliance frameworks</p>
                        </div>
                        <ExternalLink className="w-4 h-4 text-muted-foreground" />
                      </a>
                      <a
                        href="/review"
                        className="flex items-center gap-3 p-3 rounded-lg border hover:bg-accent transition-colors"
                      >
                        <CheckCircle className="w-5 h-5 text-amber-500" />
                        <div className="flex-1">
                          <p className="font-medium">Review Extractions</p>
                          <p className="text-sm text-muted-foreground">Validate ML-extracted regulatory data</p>
                        </div>
                        <ExternalLink className="w-4 h-4 text-muted-foreground" />
                      </a>
                    </div>

                    <Button className="w-full" size="lg" onClick={handleComplete}>
                      Go to Dashboard
                      <ArrowRight className="ml-2 w-4 h-4" />
                    </Button>
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </PageContainer>
    </div>
  );
}

function ServiceHealthItem({
  name,
  port,
  isLoading,
  isHealthy,
  error,
}: {
  name: string;
  port: number;
  isLoading: boolean;
  isHealthy: boolean;
  error: unknown;
}) {
  return (
    <div className="flex items-center justify-between p-3 rounded-lg border">
      <div className="flex items-center gap-3">
        {isLoading ? (
          <Spinner size="sm" />
        ) : isHealthy ? (
          <CheckCircle className="w-5 h-5 text-green-500" />
        ) : (
          <XCircle className="w-5 h-5 text-red-500" />
        )}
        <div>
          <p className="font-medium">{name}</p>
          <p className="text-sm text-muted-foreground">Port {port}</p>
        </div>
      </div>
      <Badge
        variant={isHealthy ? 'outline' : isLoading ? 'secondary' : 'destructive'}
        className={isHealthy ? 'text-green-600 border-green-600 bg-green-50' : ''}
      >
        {isLoading ? 'Checking...' : isHealthy ? 'Healthy' : 'Offline'}
      </Badge>
    </div>
  );
}
