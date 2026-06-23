'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowRight,
  Fingerprint,
  KeyRound,
  Loader2,
  Mail,
  ShieldCheck,
} from 'lucide-react';

import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';
import {
  isValidEmail,
  performPasskeyLogin,
  saveOtpChallengeState,
  seedPasswordlessClientUser,
  startEmailChallenge,
} from '@/lib/passwordless-auth';

const GENERIC_OTP_MESSAGE = 'If this address is eligible, a sign-in code is on its way.';

function resolveSafeNextPath(nextPath: string | null): string {
  if (!nextPath) return '/dashboard';
  const trimmed = nextPath.trim();
  if (!trimmed.startsWith('/') || trimmed.startsWith('//') || trimmed.startsWith('/login')) {
    return '/dashboard';
  }
  return trimmed;
}

function resolveSsoRedirect(organizationId?: string | null): string {
  const params = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : '';
  return `/auth/sso/mock${params}`;
}

export default function PasswordlessEntryClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isHydrated } = useAuth();
  const [email, setEmail] = useState('');
  const [passkeyEmail, setPasskeyEmail] = useState('');
  const [showPasskeyPrompt, setShowPasskeyPrompt] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isEmailSubmitting, setIsEmailSubmitting] = useState(false);
  const [isPasskeySubmitting, setIsPasskeySubmitting] = useState(false);
  const submitInFlightRef = useRef(false);

  const nextPath = resolveSafeNextPath(searchParams.get('next'));
  const queryError = searchParams.get('error');

  useEffect(() => {
    if (!isHydrated || !user) return;
    router.push(nextPath);
  }, [isHydrated, nextPath, router, user]);

  const handleEmailSubmit = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitInFlightRef.current) return;

    const normalizedEmail = email.trim().toLowerCase();
    if (!isValidEmail(normalizedEmail)) {
      setError('Enter a valid work email address.');
      return;
    }

    submitInFlightRef.current = true;
    setIsEmailSubmitting(true);
    setError(null);
    setStatusMessage(null);

    try {
      const response = await startEmailChallenge(normalizedEmail);
      if (response.sso_redirect) {
        window.location.assign(resolveSsoRedirect(response.organization_id));
        return;
      }

      saveOtpChallengeState({
        email: normalizedEmail,
        challengeId: response.challenge_id ?? null,
        createdAt: Date.now(),
      });
      setStatusMessage(response.detail || response.message || GENERIC_OTP_MESSAGE);
      router.push('/auth/verify');
    } catch (err: unknown) {
      const apiError = err as { response?: { status?: number }; message?: string };
      if (apiError.response?.status === 429) {
        setError('Too many code requests. Please wait before trying again.');
      } else if (apiError.response?.status === 422 || apiError.response?.status === 400) {
        setError('Enter a valid work email address.');
      } else {
        setError(apiError.message || 'Unable to start sign-in. Please try again.');
      }
    } finally {
      submitInFlightRef.current = false;
      setIsEmailSubmitting(false);
    }
  }, [email, router]);

  const handlePasskeySubmit = useCallback(async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const normalizedEmail = (passkeyEmail || email).trim().toLowerCase();
    if (!isValidEmail(normalizedEmail)) {
      setError('Enter your email before using a passkey.');
      setShowPasskeyPrompt(true);
      return;
    }

    setIsPasskeySubmitting(true);
    setError(null);
    setStatusMessage(null);

    try {
      await performPasskeyLogin(normalizedEmail);
      seedPasswordlessClientUser(normalizedEmail);
      window.location.assign(nextPath);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Passkey sign-in failed.';
      setError(message);
      setShowPasskeyPrompt(true);
    } finally {
      setIsPasskeySubmitting(false);
    }
  }, [email, nextPath, passkeyEmail]);

  const busy = isEmailSubmitting || isPasskeySubmitting;

  return (
    <div className="re-compliance-os min-h-screen overflow-x-hidden bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      <section className="mx-auto grid min-h-screen w-full max-w-6xl items-center gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(390px,0.75fr)] lg:px-8">
        <aside className="hidden lg:grid lg:gap-5" aria-label="Secure access context">
          <Link href="/" className="inline-flex w-fit items-center text-[var(--re-text-primary)] no-underline">
            <RegEngineWordmark size="md" />
          </Link>

          <div className="border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-6 shadow-sm">
            <div className="inline-flex items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              Passwordless access
            </div>
            <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-tight text-[var(--re-text-primary)]">
              Open the traceability control room.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--re-text-muted)]">
              Use an email code for standard access, or a passkey when your workspace requires high-assurance authentication.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {[
                ['OTP', 'Email code'],
                ['SSO', 'Policy routing'],
                ['Passkey', 'Step-up ready'],
              ].map(([value, label]) => (
                <div key={label} className="border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-4">
                  <p className="font-mono text-2xl font-semibold leading-none text-[var(--re-text-primary)]">{value}</p>
                  <p className="mt-2 text-xs leading-5 text-[var(--re-text-muted)]">{label}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="border border-[var(--re-evidence-border)] bg-[var(--re-evidence-bg)] p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--re-evidence)]" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--re-text-primary)]">Enterprise policy is enforced before codes are sent.</p>
                <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">
                  Verified SSO-only domains route to the identity provider instead of issuing email OTPs.
                </p>
              </div>
            </div>
          </div>
        </aside>

        <Card className="border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-lg">
          <CardHeader className="px-5 pb-3 pt-6 text-left sm:px-9 sm:pt-9">
            <Link href="/" className="mb-8 inline-flex w-fit items-center text-[var(--re-text-primary)] no-underline lg:hidden">
              <RegEngineWordmark size="md" />
            </Link>
            <div className="inline-flex w-fit items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
              <Mail className="h-3.5 w-3.5" aria-hidden="true" />
              Secure sign-in
            </div>
            <h2 className="mt-5 text-3xl font-semibold leading-tight text-[var(--re-text-primary)]">Continue to RegEngine</h2>
            <CardDescription className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">
              Enter your email to receive a one-time code, or use a registered passkey.
            </CardDescription>
          </CardHeader>

          <CardContent className="px-5 pb-6 sm:px-9 sm:pb-9">
            {queryError === 'session_expired' && (
              <div className="mb-4 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] p-3 text-sm text-[var(--re-text-secondary)]" role="status">
                Your session expired. Sign in again to continue.
              </div>
            )}

            {statusMessage && (
              <div className="mb-4 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] p-3 text-sm text-[var(--re-text-secondary)]" role="status">
                {statusMessage}
              </div>
            )}

            {error && (
              <div
                id="login-error"
                role="alert"
                aria-live="polite"
                className="mb-4 border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/10 dark:text-red-400"
              >
                {error}
              </div>
            )}

            <form onSubmit={handleEmailSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium leading-none text-[var(--re-text-secondary)]" htmlFor="email">
                  Email address
                </label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--re-text-muted)]" />
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    placeholder="name@company.com"
                    value={email}
                    onChange={(event) => {
                      setEmail(event.target.value);
                      if (!passkeyEmail) setPasskeyEmail(event.target.value);
                    }}
                    disabled={busy}
                    required
                    autoComplete="email"
                    aria-invalid={!!error}
                    aria-describedby={error ? 'login-error' : undefined}
                    className="h-12 pl-10"
                  />
                </div>
              </div>

              <Button className="h-12 w-full gap-2" type="submit" disabled={busy}>
                {isEmailSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Sending code...
                  </>
                ) : (
                  <>
                    Continue
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </>
                )}
              </Button>
            </form>

            <div className="my-5 flex items-center gap-3 text-xs uppercase tracking-[0.14em] text-[var(--re-text-muted)]">
              <div className="h-px flex-1 bg-[var(--re-border-subtle)]" />
              or
              <div className="h-px flex-1 bg-[var(--re-border-subtle)]" />
            </div>

            <Button
              className="h-12 w-full gap-2"
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setPasskeyEmail(email);
                setShowPasskeyPrompt(true);
              }}
            >
              <Fingerprint className="h-4 w-4" aria-hidden="true" />
              Sign in with Passkey
            </Button>

            {showPasskeyPrompt && (
              <form onSubmit={handlePasskeySubmit} className="mt-4 space-y-3 border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-3">
                <label className="text-sm font-medium leading-none text-[var(--re-text-secondary)]" htmlFor="passkey-email">
                  Passkey email
                </label>
                <Input
                  id="passkey-email"
                  type="email"
                  value={passkeyEmail}
                  onChange={(event) => setPasskeyEmail(event.target.value)}
                  placeholder="name@company.com"
                  autoComplete="email webauthn"
                  disabled={busy}
                />
                <Button type="submit" className="h-11 w-full gap-2" disabled={busy}>
                  {isPasskeySubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Waiting for passkey...
                    </>
                  ) : (
                    <>
                      Use Passkey
                      <Fingerprint className="h-4 w-4" aria-hidden="true" />
                    </>
                  )}
                </Button>
              </form>
            )}

            <div className="mt-5 border-t border-[var(--re-border-subtle)] pt-5 text-center text-sm text-[var(--re-text-muted)]">
              <Link href="/" className="font-medium text-[var(--re-text-secondary)] transition-colors hover:text-[var(--re-text-primary)]">
                Return to RegEngine.co
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
