'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useRouter } from 'next/navigation';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
  Shield,
  Zap,
  BarChart3,
  Network,
  FileSearch,
} from 'lucide-react';

type OnboardingStep = 'welcome' | 'health' | 'credentials' | 'first-ingest' | 'complete';

const DEMO_DOCUMENT_URL = 'https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-21.xml?chapter=I&subchapter=A&part=1';

const QA_LOGIN_PRESETS = [
  {
    id: 'qa' as const,
    label: 'QA Tester',
    email: 'test@example.com',
    password: 'password123',
    access: 'Dashboard and core QA flows',
  },
  {
    id: 'admin' as const,
    label: 'QA Admin',
    email: 'admin@example.com',
    password: 'password',
    access: 'Sysadmin and admin tools',
  },
];

/* ───────────────────────────────────────────────────────────── */
/*  Framer Motion Variants                                      */
/* ───────────────────────────────────────────────────────────── */
const cardVariants = {
  enter: { opacity: 0, x: 30, scale: 0.98 },
  center: { opacity: 1, x: 0, scale: 1, transition: { duration: 0.35, ease: [0.4, 0, 0.2, 1] } },
  exit: { opacity: 0, x: -30, scale: 0.98, transition: { duration: 0.25 } },
};

const staggerChildren = {
  animate: { transition: { staggerChildren: 0.08 } },
};

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

/* ───────────────────────────────────────────────────────────── */
/*  Animated Background Orbs                                    */
/* ───────────────────────────────────────────────────────────── */
function BackgroundOrbs() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      <div
        className="absolute -top-40 -right-40 w-96 h-96 rounded-full opacity-[0.03]"
        style={{ background: 'radial-gradient(circle, var(--re-brand) 0%, transparent 70%)' }}
      />
      <div
        className="absolute -bottom-60 -left-40 w-[500px] h-[500px] rounded-full opacity-[0.02]"
        style={{ background: 'radial-gradient(circle, var(--re-info) 0%, transparent 70%)' }}
      />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────── */
/*  Activation Stats (completion page)                          */
/* ───────────────────────────────────────────────────────────── */
function ActivationStat({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string; color: string }) {
  return (
    <motion.div
      variants={fadeUp}
      className="flex items-center gap-3 p-3 rounded-lg border border-[var(--re-border-default)] bg-re-surface-card"
    >
      <div className="p-2 rounded-lg" style={{ background: `${color}15` }}>
        <Icon className="w-4 h-4" style={{ color }} />
      </div>
      <div>
        <p className="text-xs text-re-text-muted">{label}</p>
        <p className="font-semibold text-sm text-re-text-primary">{value}</p>
      </div>
    </motion.div>
  );
}

/* ───────────────────────────────────────────────────────────── */
/*  Main Onboarding Page                                        */
/* ───────────────────────────────────────────────────────────── */
export default function OnboardingPage() {
  const router = useRouter();
  const { apiKey, adminKey, tenantId, setApiKey, setAdminKey, setTenantId, completeOnboarding, isOnboarded, isAuthenticated } = useAuth();

  const [currentStep, setCurrentStep] = useState<OnboardingStep>('welcome');
  const [adminKeyInput, setAdminKeyInput] = useState('');
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [credentialMethod, setCredentialMethod] = useState<'admin' | 'existing' | 'cli' | null>(null);
  const [existingApiKey, setExistingApiKey] = useState('');
  const [tenantName, setTenantName] = useState('');

  // Cloud deployment detection — on Vercel, backend services don't exist
  const [isCloudMode, setIsCloudMode] = useState(false);
  const [showQaPresets, setShowQaPresets] = useState(false);
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const host = window.location.hostname;
      setIsCloudMode(host !== 'localhost' && host !== '127.0.0.1');

      const localHost = host === 'localhost' || host === '127.0.0.1';
      const previewHost = host.endsWith('.vercel.app') || host.includes('staging') || host.includes('preview');
      const explicitQaMode = process.env.NEXT_PUBLIC_SHOW_QA_CREDENTIALS === 'true';
      setShowQaPresets(explicitQaMode || localHost || previewHost);
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

  const goToPresetLogin = (preset: 'qa' | 'admin') => {
    router.push(`/login?preset=${preset}`);
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
    <div className="min-h-screen relative bg-re-surface-base">
      <BackgroundOrbs />

      <PageContainer>
        <div className="max-w-2xl mx-auto relative z-10">
          {/* ─── Progress Indicator ─── */}
          <div className="mb-8 pt-4">
            <div className="flex items-center justify-between mb-3">
              {steps.map((step, index) => (
                <div key={step.id} className="flex items-center">
                  <motion.div
                    animate={{
                      scale: index === currentStepIndex ? 1.1 : 1,
                      boxShadow: index === currentStepIndex
                        ? '0 0 20px rgba(16, 185, 129, 0.3)'
                        : '0 0 0px transparent',
                    }}
                    transition={{ duration: 0.3 }}
                    className={`
                      w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-colors duration-300
                      ${index < currentStepIndex
                        ? 'bg-re-brand text-[var(--re-surface-base)]'
                        : index === currentStepIndex
                          ? 'bg-re-brand text-[var(--re-surface-base)] ring-4 ring-re-brand/20'
                          : 'bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)]'
                      }
                    `}
                  >
                    {index < currentStepIndex ? <CheckCircle className="w-4 h-4" /> : step.number}
                  </motion.div>
                  {index < steps.length - 1 && (
                    <div className="w-10 sm:w-16 h-1 mx-1 rounded-full overflow-hidden bg-re-surface-elevated"
                    >
                      <motion.div
                        className="h-full rounded-full bg-re-brand"
                        initial={{ width: '0%' }}
                        animate={{ width: index < currentStepIndex ? '100%' : '0%' }}
                        transition={{ duration: 0.5, ease: 'easeOut' }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="text-center text-sm text-re-text-muted">
              Step {currentStepIndex + 1} of {steps.length}: <span className="text-re-text-secondary">{steps[currentStepIndex]?.title}</span>
            </p>
          </div>

          <AnimatePresence mode="wait">
            {/* ═══════════ Step 1: Welcome ═══════════ */}
            {currentStep === 'welcome' && (
              <motion.div key="welcome" variants={cardVariants} initial="enter" animate="center" exit="exit">
                <Card className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card">
                  {/* Gradient header accent */}
                  <div className="h-1" style={{ background: 'linear-gradient(90deg, var(--re-brand), var(--re-info), var(--re-brand-light))' }} />

                  <CardHeader className="text-center pb-2">
                    <motion.div
                      initial={{ scale: 0.5, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ delay: 0.15, type: 'spring', stiffness: 200 }}
                      className="mx-auto mb-4 p-4 rounded-2xl"
                      style={{ background: 'rgba(16, 185, 129, 0.1)', boxShadow: 'var(--re-shadow-glow)' }}
                    >
                      <Rocket className="w-12 h-12 text-re-brand" />
                    </motion.div>
                    <CardTitle className="text-3xl font-bold text-re-text-primary">
                      Welcome to RegEngine
                    </CardTitle>
                    <CardDescription className="text-lg text-re-text-tertiary">
                      Your compliance evidence platform — set up in under 3 minutes
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="space-y-6">
                    <motion.div className="grid gap-3" variants={staggerChildren} initial="initial" animate="animate">
                      {[
                        { icon: Shield, label: 'Verify services are running', desc: 'Quick health check on all backend services', color: 'var(--re-success)' },
                        { icon: Key, label: 'Set up your API key', desc: 'Create or enter credentials to access the platform', color: 'var(--re-info)' },
                        { icon: Upload, label: 'Ingest your first document', desc: 'See the platform transform a regulation into evidence', color: 'var(--re-brand)' },
                      ].map((item) => (
                        <motion.div
                          key={item.label}
                          variants={fadeUp}
                          className="flex items-start gap-3 p-4 rounded-xl border border-[var(--re-border-default)] bg-re-surface-elevated"
                        >
                          <div className="p-1.5 rounded-lg mt-0.5" style={{ background: `${item.color}15` }}>
                            <item.icon className="w-4 h-4" style={{ color: item.color }} />
                          </div>
                          <div>
                            <p className="font-medium text-re-text-primary">{item.label}</p>
                            <p className="text-sm text-re-text-muted">{item.desc}</p>
                          </div>
                        </motion.div>
                      ))}
                    </motion.div>

                    {showQaPresets && (
                      <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-re-surface-elevated space-y-3">
                        <div className="flex items-start gap-3">
                          <Shield className="w-4 h-4 mt-0.5 text-re-info" />
                          <div>
                            <p className="font-medium text-re-text-primary">QA Test Credentials</p>
                            <p className="text-sm text-re-text-muted">
                              Use these for QA sign-in and admin-access verification.
                            </p>
                          </div>
                        </div>

                        <div className="space-y-2">
                          {QA_LOGIN_PRESETS.map((preset) => (
                            <div
                              key={preset.id}
                              className="rounded-lg border border-[var(--re-border-default)] bg-re-surface-card p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                            >
                              <div>
                                <p className="text-sm font-medium text-re-text-primary">{preset.label}</p>
                                <p className="text-xs text-re-text-muted">{preset.access}</p>
                                <p className="text-xs font-mono text-re-text-secondary mt-1">
                                  {preset.email} / {preset.password}
                                </p>
                              </div>
                              <Button
                                type="button"
                                variant="outline"
                                className="border-[var(--re-border-default)]"
                                onClick={() => goToPresetLogin(preset.id)}
                              >
                                Open Login
                                <ExternalLink className="ml-2 w-4 h-4" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {isAuthenticated && (
                      <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-re-surface-elevated">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                          <div>
                            <p className="font-medium text-re-text-primary">Internal: Supplier Onboarding Wireframe</p>
                            <p className="text-sm text-re-text-muted">
                              Review the 8-step FSMA supplier onboarding flow in a clickable wireframe.
                            </p>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            className="border-[var(--re-border-default)]"
                            onClick={() => router.push('/onboarding/supplier-flow')}
                          >
                            Open Flow
                            <ExternalLink className="ml-2 w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    )}

                    <div className="flex gap-3">
                      <Button
                        className="flex-1 h-11 font-semibold bg-re-brand text-re-surface-base"
                        onClick={() => setCurrentStep('health')}
                      >
                        Get Started
                        <ArrowRight className="ml-2 w-4 h-4" />
                      </Button>
                      {apiKey && (
                        <Button variant="outline" onClick={handleComplete}
                          className="border-[var(--re-border-default)] text-re-text-secondary"
                        >
                          Skip (I have credentials)
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* ═══════════ Step 2: Health Check ═══════════ */}
            {currentStep === 'health' && (
              <motion.div key="health" variants={cardVariants} initial="enter" animate="center" exit="exit">
                <Card className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card">
                  <div className="h-1" style={{ background: 'linear-gradient(90deg, var(--re-brand), var(--re-info))' }} />

                  <CardHeader>
                    <CardTitle className="text-re-text-primary">System Health Check</CardTitle>
                    <CardDescription className="text-re-text-tertiary">
                      {isCloudMode
                        ? 'Cloud deployment detected — backend services connect separately'
                        : 'Verifying that all RegEngine services are running'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {isCloudMode ? (
                      <div className="p-4 rounded-xl border" style={{ background: 'var(--re-info-muted)', borderColor: 'var(--re-info)' }}>
                        <div className="flex items-start gap-3">
                          <Sparkles className="w-5 h-5 mt-0.5 text-re-info" />
                          <div>
                            <p className="font-medium text-re-text-primary">Cloud Mode</p>
                            <p className="text-sm mt-1 text-re-text-tertiary">
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
                          <div className="p-4 rounded-xl border" style={{ background: 'var(--re-warning-muted)', borderColor: 'var(--re-warning)' }}>
                            <div className="flex items-start gap-3">
                              <AlertCircle className="w-5 h-5 mt-0.5 text-re-warning" />
                              <div>
                                <p className="font-medium text-re-text-primary">Services not ready</p>
                                <p className="text-sm mt-1 text-re-text-tertiary">
                                  Make sure you&apos;ve started the backend services:
                                </p>
                                <code className="block mt-2 p-2 rounded text-sm font-mono"
                                  style={{ background: 'var(--re-surface-elevated)', color: 'var(--re-text-secondary)' }}
                                >
                                  make up
                                </code>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="mt-3 border-[var(--re-border-default)]"
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
                      <Button variant="outline" onClick={() => setCurrentStep('welcome')}
                        className="border-[var(--re-border-default)] text-re-text-secondary"
                      >
                        <ArrowLeft className="mr-2 w-4 h-4" />
                        Back
                      </Button>
                      <Button
                        className="flex-1 font-semibold"
                        onClick={() => setCurrentStep('credentials')}
                        disabled={!allServicesHealthy}
                        style={allServicesHealthy ? { background: 'var(--re-brand)', color: 'var(--re-surface-base)' } : undefined}
                      >
                        Continue
                        <ArrowRight className="ml-2 w-4 h-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* ═══════════ Step 3: Credentials ═══════════ */}
            {currentStep === 'credentials' && (
              <motion.div key="credentials" variants={cardVariants} initial="enter" animate="center" exit="exit">
                <Card className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card">
                  <div className="h-1" style={{ background: 'linear-gradient(90deg, var(--re-info), var(--re-brand))' }} />

                  <CardHeader>
                    <CardTitle className="text-re-text-primary">Set Up Your Credentials</CardTitle>
                    <CardDescription className="text-re-text-tertiary">
                      Choose how you want to authenticate with RegEngine
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {!credentialMethod && (
                      <motion.div className="grid gap-3" variants={staggerChildren} initial="initial" animate="animate">
                        {[
                          {
                            id: 'admin' as const,
                            icon: Key,
                            color: 'var(--re-brand)',
                            label: 'I have an Admin Master Key',
                            desc: 'Create a new API key using your admin credentials',
                          },
                          {
                            id: 'existing' as const,
                            icon: CheckCircle,
                            color: 'var(--re-success)',
                            label: 'I already have an API Key',
                            desc: 'Enter an existing key to link this session',
                          },
                          {
                            id: 'cli' as const,
                            icon: Terminal,
                            color: 'var(--re-warning)',
                            label: 'Create via CLI / Console',
                            desc: 'Generate a new tenant and key using the command line',
                          },
                        ].map((method) => (
                          <motion.button
                            key={method.id}
                            variants={fadeUp}
                            className="flex items-start gap-4 p-4 rounded-xl border text-left transition-all duration-200
                              hover:shadow-re-md"
                            style={{
                              borderColor: 'var(--re-border-default)',
                              background: 'var(--re-surface-elevated)',
                            }}
                            onClick={() => setCredentialMethod(method.id)}
                            whileHover={{ scale: 1.01, borderColor: 'var(--re-brand)' }}
                          >
                            <div className="p-2 rounded-lg" style={{ background: `${method.color}15` }}>
                              <method.icon className="w-5 h-5" style={{ color: method.color }} />
                            </div>
                            <div>
                              <p className="font-medium text-re-text-primary">{method.label}</p>
                              <p className="text-sm text-re-text-muted">{method.desc}</p>
                            </div>
                          </motion.button>
                        ))}
                      </motion.div>
                    )}

                    {/* Admin Key Method */}
                    {credentialMethod === 'admin' && (
                      <motion.div className="space-y-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Button variant="ghost" size="sm" onClick={() => setCredentialMethod(null)}
                          className="text-re-text-muted"
                        >
                          <ArrowLeft className="w-4 h-4 mr-2" />
                          Back to options
                        </Button>

                        <div>
                          <label className="text-sm font-medium mb-2 block text-re-text-secondary"
                            htmlFor="tenant-name"
                          >
                            Tenant or Organization Name
                          </label>
                          <Input
                            id="tenant-name"
                            placeholder="Acme Corp"
                            value={tenantName}
                            onChange={(e) => setTenantName(e.target.value)}
                            className="border-[var(--re-border-default)] bg-re-surface-elevated text-re-text-primary"
                          />
                        </div>

                        {createKeyMutation.isError || createTenantMutation.isError ? (
                          <div
                            id="onboarding-error"
                            role="alert"
                            className="p-3 rounded-lg text-sm"
                            style={{ background: 'var(--re-danger-muted)', color: 'var(--re-danger)' }}
                          >
                            Failed to create tenant or API key. Please check your admin key and try again.
                          </div>
                        ) : null}

                        <div>
                          <label className="text-sm font-medium mb-2 block text-re-text-secondary"
                            htmlFor="admin-key"
                          >
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
                            className="border-[var(--re-border-default)] bg-re-surface-elevated text-re-text-primary"
                          />
                        </div>

                        <Button
                          className="w-full font-semibold bg-re-brand text-re-surface-base"
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
                      </motion.div>
                    )}

                    {/* Existing API Key Method */}
                    {credentialMethod === 'existing' && (
                      <motion.div className="space-y-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Button variant="ghost" size="sm" onClick={() => setCredentialMethod(null)}
                          className="text-re-text-muted"
                        >
                          <ArrowLeft className="w-4 h-4 mr-2" />
                          Back to options
                        </Button>

                        <div>
                          <label className="text-sm font-medium mb-2 block text-re-text-secondary"
                            htmlFor="existing-api-key"
                          >
                            Your API Key
                          </label>
                          <p className="text-sm mb-2 text-re-text-muted">
                            Starts with <code className="px-1.5 py-0.5 rounded font-mono text-xs"
                              style={{ background: 'var(--re-surface-elevated)', color: 'var(--re-brand)' }}
                            >rge_</code>
                          </p>
                          <Input
                            id="existing-api-key"
                            type="password"
                            placeholder="rge_..."
                            value={existingApiKey}
                            onChange={(e) => setExistingApiKey(e.target.value)}
                            className="border-[var(--re-border-default)] bg-re-surface-elevated text-re-text-primary"
                          />
                        </div>

                        <Button
                          className="w-full font-semibold bg-re-brand text-re-surface-base"
                          onClick={handleUseExistingKey}
                          disabled={!existingApiKey}
                        >
                          Use This Key
                          <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                      </motion.div>
                    )}

                    {/* CLI Method */}
                    {credentialMethod === 'cli' && (
                      <motion.div className="space-y-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Button variant="ghost" size="sm" onClick={() => setCredentialMethod(null)}
                          className="text-re-text-muted"
                        >
                          <ArrowLeft className="w-4 h-4 mr-2" />
                          Back to options
                        </Button>

                        <div className="p-4 rounded-xl font-mono text-sm overflow-x-auto"
                          style={{ background: 'var(--re-surface-base)', border: '1px solid var(--re-border-default)' }}
                        >
                          <div className="flex items-center justify-between mb-2 text-re-text-muted">
                            <span className="text-xs">Terminal</span>
                            <div className="flex gap-1.5">
                              <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--re-danger)', opacity: 0.4 }} />
                              <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--re-warning)', opacity: 0.4 }} />
                              <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--re-success)', opacity: 0.4 }} />
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-re-success">$</span>
                            <span className="text-re-text-secondary">curl -X POST https://api.regengine.co/v1/tenants/init</span>
                          </div>
                          <div className="mt-3 flex justify-end">
                            <Button
                              variant="secondary"
                              size="sm"
                              className="h-7 text-xs"
                              onClick={() => copyToClipboard('curl -X POST https://api.regengine.co/v1/tenants/init')}
                            >
                              {copied ? <CheckCircle className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                            </Button>
                          </div>
                        </div>

                        <p className="text-sm text-re-text-muted">
                          This will create a new tenant with sample data and display your API key.
                        </p>

                        <div className="p-4 rounded-xl border border-re-border bg-re-surface-elevated">
                          <p className="font-medium mb-2 text-re-text-primary">After running the command:</p>
                          <div>
                            <label className="text-sm font-medium mb-2 block text-re-text-secondary"
                              htmlFor="cli-api-key"
                            >
                              Enter the API Key from the output
                            </label>
                            <Input
                              id="cli-api-key"
                              type="password"
                              placeholder="rge_..."
                              value={existingApiKey}
                              onChange={(e) => setExistingApiKey(e.target.value)}
                              className="border-[var(--re-border-default)]"
                              style={{ background: 'var(--re-surface-base)', color: 'var(--re-text-primary)' }}
                            />
                          </div>
                          <Button
                            className="w-full mt-3 font-semibold bg-re-brand text-re-surface-base"
                            onClick={handleUseExistingKey}
                            disabled={!existingApiKey}
                          >
                            Continue
                            <ArrowRight className="ml-2 w-4 h-4" />
                          </Button>
                        </div>
                      </motion.div>
                    )}

                    {/* Navigation Footer */}
                    {!credentialMethod && (
                      <div className="flex gap-3">
                        <Button variant="outline" onClick={() => setCurrentStep('health')}
                          className="border-[var(--re-border-default)] text-re-text-secondary"
                        >
                          <ArrowLeft className="mr-2 w-4 h-4" />
                          Back
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* ═══════════ Step 4: First Ingest ═══════════ */}
            {currentStep === 'first-ingest' && (
              <motion.div key="first-ingest" variants={cardVariants} initial="enter" animate="center" exit="exit">
                <Card className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card">
                  <div className="h-1" style={{ background: 'linear-gradient(90deg, var(--re-brand-light), var(--re-brand))' }} />

                  <CardHeader>
                    <CardTitle className="text-re-text-primary">Ingest Your First Document</CardTitle>
                    <CardDescription className="text-re-text-tertiary">
                      See RegEngine transform a regulation into structured compliance evidence
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="p-4 rounded-xl border border-re-border bg-re-surface-elevated">
                      <div className="flex items-center gap-2 mb-2">
                        <FileSearch className="w-4 h-4 text-re-brand" />
                        <p className="font-medium text-re-text-primary">Sample Document</p>
                      </div>
                      <p className="text-sm mb-2 text-re-text-muted">
                        We&apos;ll ingest a section of FDA regulations (21 CFR Part 1)
                      </p>
                      <code className="text-xs break-all block p-2 rounded font-mono"
                        style={{ background: 'var(--re-surface-base)', color: 'var(--re-text-tertiary)' }}
                      >
                        {DEMO_DOCUMENT_URL}
                      </code>
                    </div>

                    {ingestMutation.isSuccess && (
                      <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="p-4 rounded-xl border"
                        style={{ background: 'var(--re-success-muted)', borderColor: 'var(--re-success)' }}
                      >
                        <div className="flex items-start gap-3">
                          <CheckCircle className="w-5 h-5 mt-0.5 text-re-success" />
                          <div>
                            <p className="font-semibold text-re-text-primary">
                              Document Submitted!
                            </p>
                            <p className="text-sm mt-1 text-re-text-tertiary">
                              Document ID: <code className="font-mono px-1 py-0.5 rounded text-xs"
                                style={{ background: 'var(--re-surface-elevated)', color: 'var(--re-brand)' }}
                              >{ingestMutation.data?.doc_id}</code>
                            </p>
                            <p className="text-sm text-re-text-tertiary">
                              The document is now being processed through the NLP pipeline.
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    )}

                    {ingestMutation.isError && (
                      <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="p-4 rounded-xl border"
                        style={{ background: 'var(--re-danger-muted)', borderColor: 'var(--re-danger)' }}
                      >
                        <div className="flex items-start gap-3">
                          <XCircle className="w-5 h-5 mt-0.5 text-re-danger" />
                          <div>
                            <p className="font-semibold text-re-text-primary">
                              Ingestion Failed
                            </p>
                            <p className="text-sm mt-1 text-re-text-tertiary">
                              {ingestMutation.error?.message || 'An error occurred. You can try again or skip this step.'}
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    )}

                    <div className="flex gap-3">
                      <Button variant="outline" onClick={() => setCurrentStep('credentials')}
                        className="border-[var(--re-border-default)] text-re-text-secondary"
                      >
                        <ArrowLeft className="mr-2 w-4 h-4" />
                        Back
                      </Button>

                      {!ingestMutation.isSuccess ? (
                        <Button
                          className="flex-1 font-semibold bg-re-brand text-re-surface-base"
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
                        <Button
                          className="flex-1 font-semibold bg-re-brand text-re-surface-base"
                          onClick={() => setCurrentStep('complete')}
                        >
                          Continue
                          <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                      )}

                      <Button variant="ghost" onClick={() => setCurrentStep('complete')}
                        className="text-re-text-muted"
                      >
                        Skip
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            {/* ═══════════ Step 5: Complete ═══════════ */}
            {currentStep === 'complete' && (
              <motion.div key="complete" variants={cardVariants} initial="enter" animate="center" exit="exit">
                <Card className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card">
                  <div className="h-1.5" style={{ background: 'linear-gradient(90deg, var(--re-success), var(--re-brand), var(--re-info))' }} />

                  <CardHeader className="text-center pb-2">
                    <motion.div
                      initial={{ scale: 0, rotate: -180 }}
                      animate={{ scale: 1, rotate: 0 }}
                      transition={{ type: 'spring', stiffness: 200, delay: 0.1 }}
                      className="mx-auto mb-4 p-4 rounded-2xl"
                      style={{ background: 'var(--re-success-muted)', boxShadow: '0 0 30px rgba(34, 197, 94, 0.2)' }}
                    >
                      <Sparkles className="w-12 h-12 text-re-success" />
                    </motion.div>
                    <CardTitle className="text-3xl font-bold text-re-text-primary">
                      You&apos;re All Set!
                    </CardTitle>
                    <CardDescription className="text-lg text-re-text-tertiary">
                      RegEngine is ready — here&apos;s what you can do now
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="space-y-6">
                    {/* Platform stats */}
                    <motion.div
                      className="grid grid-cols-2 gap-3"
                      variants={staggerChildren}
                      initial="initial"
                      animate="animate"
                    >
                      <ActivationStat icon={Shield} label="Security" value="Double-Lock Active" color="var(--re-success)" />
                      <ActivationStat icon={Zap} label="Verticals" value="12 Industries" color="var(--re-warning)" />
                      <ActivationStat icon={BarChart3} label="Evidence" value="Hash-Chained" color="var(--re-info)" />
                      <ActivationStat icon={Network} label="Graph" value="Neo4j Ready" color="var(--re-brand)" />
                    </motion.div>

                    {/* What's next */}
                    <motion.div className="grid gap-2" variants={staggerChildren} initial="initial" animate="animate">
                      <p className="font-semibold text-sm text-re-text-secondary">Explore the Platform</p>
                      {[
                        { href: '/ingest', icon: Upload, label: 'Ingest Documents', desc: 'Add your own regulatory documents', color: 'var(--re-info)' },
                        { href: '/compliance', icon: Shield, label: 'Compliance Checklists', desc: 'Explore pre-built frameworks', color: 'var(--re-success)' },
                        { href: '/review', icon: FileSearch, label: 'Review Extractions', desc: 'Validate ML-extracted regulatory data', color: 'var(--re-warning)' },
                        { href: '/ftl-checker', icon: Zap, label: 'FTL Checker', desc: 'Check FDA Food Traceability List coverage', color: 'var(--re-brand)' },
                      ].map((item) => (
                        <motion.a
                          key={item.href}
                          href={item.href}
                          variants={fadeUp}
                          className="flex items-center gap-3 p-3 rounded-xl border transition-all duration-200
                            hover:shadow-re-md border-re-border bg-re-surface-elevated"
                          whileHover={{ scale: 1.01, x: 4 }}
                        >
                          <div className="p-1.5 rounded-lg" style={{ background: `${item.color}15` }}>
                            <item.icon className="w-4 h-4" style={{ color: item.color }} />
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-sm text-re-text-primary">{item.label}</p>
                            <p className="text-xs text-re-text-muted">{item.desc}</p>
                          </div>
                          <ExternalLink className="w-3.5 h-3.5 text-re-text-disabled" />
                        </motion.a>
                      ))}
                    </motion.div>

                    <Button
                      className="w-full h-12 font-bold text-base"
                      size="lg"
                      onClick={handleComplete}
                      style={{ background: 'var(--re-brand)', color: 'var(--re-surface-base)', boxShadow: 'var(--re-shadow-glow)' }}
                    >
                      Go to Dashboard
                      <ArrowRight className="ml-2 w-5 h-5" />
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

/* ───────────────────────────────────────────────────────────── */
/*  Service Health Item                                         */
/* ───────────────────────────────────────────────────────────── */
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
    <div className="flex items-center justify-between p-3 rounded-xl border border-re-border bg-re-surface-elevated"
    >
      <div className="flex items-center gap-3">
        {isLoading ? (
          <Spinner size="sm" />
        ) : isHealthy ? (
          <CheckCircle className="w-5 h-5 text-re-success" />
        ) : (
          <XCircle className="w-5 h-5 text-re-danger" />
        )}
        <div>
          <p className="font-medium text-sm text-re-text-primary">{name}</p>
          <p className="text-xs text-re-text-muted">Port {port}</p>
        </div>
      </div>
      <div>
        {isLoading ? (
          <span className="text-xs text-re-text-muted">Checking...</span>
        ) : isHealthy ? (
          <span className="text-xs font-medium px-2 py-1 rounded-full"
            style={{ background: 'var(--re-success-muted)', color: 'var(--re-success)' }}
          >Healthy</span>
        ) : (
          <span className="text-xs font-medium px-2 py-1 rounded-full"
            style={{ background: 'var(--re-danger-muted)', color: 'var(--re-danger)' }}
          >Offline</span>
        )}
      </div>
    </div>
  );
}
