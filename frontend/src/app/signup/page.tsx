'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Loader2, CheckCircle2 } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { PLAN_LABELS } from '@/lib/constants';

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();

  const checkoutSuccess = searchParams.get('checkout') === 'success';
  const selectedPlan = searchParams.get('plan');
  const planLabel = selectedPlan ? PLAN_LABELS[selectedPlan] || selectedPlan : null;
  const partnerTier = searchParams.get('partner'); // ?partner=founding

  const [tenantName, setTenantName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptedDetail, setAcceptedDetail] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setAcceptedDetail(null);
    setIsLoading(true);

    try {
      const response = await apiClient.signup(email, password, tenantName, partnerTier || undefined);

      if (!('access_token' in response)) {
        setAcceptedDetail(response.detail);
        return;
      }

      // Set RegEngine JWT session FIRST (sets re_access_token cookie + React state)
      await login(response.access_token, response.user, response.tenant_id);

      // #538 fix: Establish Supabase session alongside custom JWT.
      // Middleware cross-validates both sessions — without this the user
      // hits a redirect loop on the next protected route.
      const supabase = createSupabaseBrowserClient();
      const { error: sbError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (sbError) {
        console.error('[signup] Supabase session sync failed:', sbError.message);
      }

      router.push('/onboarding/setup/welcome');
    } catch (err: unknown) {
      const apiError = err as {
        response?: { status?: number; data?: { detail?: string } };
        message?: string;
      };
      const status = apiError.response?.status;
      if (!apiError.response) {
        // No response — network-level failure
        const offline = typeof navigator !== 'undefined' && !navigator.onLine;
        setError(
          offline
            ? 'You appear to be offline. Check your connection and try again.'
            : 'Could not reach the server. Check your connection or try again in a moment.',
        );
      } else if (status === 409) {
        setError(
          'An account with this email already exists. Try signing in instead.',
        );
      } else if (status === 400 || status === 422) {
        setError(
          apiError.response.data?.detail ||
            'Please check your details — company name must be at least 2 characters and password at least 12.',
        );
      } else if (status === 429) {
        setError(
          'Too many signup attempts. Please wait a minute then try again.',
        );
      } else if (status !== undefined && status >= 500) {
        setError(
          'Our servers ran into a problem. If this keeps happening, email support@regengine.co.',
        );
      } else {
        setError(
          'Unable to create account right now. Try again or email support@regengine.co.',
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
      <div className="mx-auto max-w-md">
        {/* Checkout success banner */}
        {checkoutSuccess && (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-re-brand/30 bg-re-brand-muted p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-re-brand" />
            <div>
              <p className="text-sm font-semibold text-re-brand-light">
                Payment confirmed
              </p>
              <p className="text-xs text-re-brand-light/80">
                {planLabel
                  ? `Create your account to get started on the ${planLabel} plan.`
                  : 'Create your account to get started.'}
              </p>
            </div>
          </div>
        )}

        {/* Plan context banner (when coming from pricing, no Stripe) */}
        {selectedPlan && !checkoutSuccess && (
          <div className="mb-6 rounded-xl border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 px-4 py-3 text-center">
            <p className="text-sm text-[var(--re-brand)]">
              Selected plan: <span className="font-semibold">{planLabel}</span>
              {' \u2014 '}you can start your subscription after creating your account.
            </p>
          </div>
        )}

        {/* Design partner welcome banner */}
        {partnerTier === 'founding' && !checkoutSuccess && (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-re-brand/30 bg-re-brand-muted p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-re-brand" />
            <div>
              <p className="text-sm font-semibold text-re-brand-light">
                Founding Design Partner
              </p>
              <p className="text-xs text-re-brand-light/80">
                Welcome to the founding cohort. You&apos;ll get 50% off for life, white-glove onboarding, and direct founder support.
              </p>
            </div>
          </div>
        )}

        <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-md">
          <CardHeader className="space-y-1">
            <h1 className="text-2xl font-semibold leading-none tracking-tight text-[var(--re-text-primary)]">
              {partnerTier === 'founding' ? 'Create Your Partner Workspace' : 'Create Your Workspace'}
            </h1>
            <CardDescription className="text-[var(--re-text-muted)]">
              {partnerTier === 'founding'
                ? 'Founding partner access. No credit card required.'
                : '14-day free trial. No credit card required.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {acceptedDetail ? (
              <div
                className="rounded-md border border-re-brand/30 bg-re-brand-muted px-3 py-3 text-sm text-re-brand-light"
                role="status"
              >
                {acceptedDetail}
              </div>
            ) : null}
            <form className="space-y-4" onSubmit={handleSubmit}>
              {error && (
                <div
                  className="rounded-md border border-re-danger/40 bg-re-danger-muted0/10 px-3 py-2 text-sm text-re-danger"
                  role="alert"
                >
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <label className="text-sm text-[var(--re-text-secondary)]" htmlFor="tenantName">
                  Company Name
                </label>
                <Input
                  id="tenantName"
                  type="text"
                  required
                  minLength={2}
                  placeholder="Valley Fresh Foods"
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm text-[var(--re-text-secondary)]" htmlFor="email">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm text-[var(--re-text-secondary)]" htmlFor="password">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  required
                  minLength={12}
                  autoComplete="new-password"
                  placeholder="At least 12 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <Button className="h-11 w-full" type="submit" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating account...
                  </>
                ) : (
                  'Create Account'
                )}
              </Button>
            </form>

            <p className="mt-4 text-center text-xs text-[var(--re-text-muted)]">
              Already have an account?{' '}
              <Link href="/login" className="text-[var(--re-brand)] hover:underline">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function SignupPage() {
  return (
    <Suspense>
      <SignupForm />
    </Suspense>
  );
}
