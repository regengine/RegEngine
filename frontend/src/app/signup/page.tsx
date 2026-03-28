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

const PLAN_LABELS: Record<string, string> = {
  base: 'Base',
  standard: 'Standard',
  premium: 'Premium',
  growth: 'Growth',
  scale: 'Scale',
};

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();

  const checkoutSuccess = searchParams.get('checkout') === 'success';
  const selectedPlan = searchParams.get('plan');
  const planLabel = selectedPlan ? PLAN_LABELS[selectedPlan] || selectedPlan : null;

  const [tenantName, setTenantName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const response = await apiClient.signup(email, password, tenantName);
      login(response.access_token, response.user, response.tenant_id);
      router.push('/onboarding/supplier-flow');
    } catch (err: unknown) {
      const apiError = err as {
        response?: { status?: number; data?: { detail?: string } };
        message?: string;
      };
      if (apiError.response?.status === 409) {
        setError('An account with this email already exists.');
      } else if (apiError.response?.status === 400) {
        setError(apiError.response.data?.detail || 'Please check your signup details.');
      } else {
        setError('Unable to create account right now. Please try again.');
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
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-400" />
            <div>
              <p className="text-sm font-semibold text-emerald-300">
                Payment confirmed
              </p>
              <p className="text-xs text-emerald-300/80">
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

        <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
          <CardHeader className="space-y-1">
            <h1 className="text-2xl font-semibold leading-none tracking-tight text-[var(--re-text-primary)]">Create Your Workspace</h1>
            <CardDescription className="text-[var(--re-text-muted)]">
              14-day free trial. No credit card required.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              {error && (
                <div
                  className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200"
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
