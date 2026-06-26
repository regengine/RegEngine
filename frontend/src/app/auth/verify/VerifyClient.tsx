'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, KeyRound, Loader2, Mail, RotateCcw } from 'lucide-react';

import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  clearOtpChallengeState,
  loadOtpChallengeState,
  seedPasswordlessClientUser,
  type StoredOtpChallenge,
  verifyEmailChallenge,
} from '@/lib/passwordless-auth';

type VerifyClientProps = {
  initialEmail?: string;
  initialChallengeId?: string;
};

export default function VerifyClient({ initialEmail = '', initialChallengeId = '' }: VerifyClientProps) {
  const [state, setState] = useState<StoredOtpChallenge | null>(() => {
    if (initialEmail) {
      return {
        email: initialEmail,
        challengeId: initialChallengeId || null,
        createdAt: Date.now(),
      };
    }
    return null;
  });
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (state) return;
    setState(loadOtpChallengeState());
  }, [state]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedCode = code.trim();

    if (!/^\d{6}$/.test(normalizedCode)) {
      setError('Enter the 6-digit code from your email.');
      return;
    }

    if (!state?.challengeId) {
      setError('This sign-in attempt is missing its challenge. Request a new code to continue.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await verifyEmailChallenge(state.challengeId, normalizedCode);
      seedPasswordlessClientUser(state.email);
      clearOtpChallengeState();
      window.location.assign('/dashboard');
    } catch (err: unknown) {
      const apiError = err as { response?: { status?: number }; message?: string };
      if (apiError.response?.status === 401 || apiError.response?.status === 400) {
        setError('That code is incorrect or expired. Check the code and try again.');
      } else if (apiError.response?.status === 429) {
        setError('Too many attempts. Please wait before trying again.');
      } else {
        setError(apiError.message || 'Unable to verify this code. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="re-compliance-os min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      <section className="mx-auto flex min-h-screen w-full max-w-md items-center px-4 py-8 sm:px-6">
        <Card className="w-full border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-lg">
          <CardHeader className="px-5 pb-3 pt-6 sm:px-8 sm:pt-8">
            <Link href="/" className="mb-8 inline-flex w-fit items-center text-[var(--re-text-primary)] no-underline">
              <RegEngineWordmark size="md" />
            </Link>
            <div className="inline-flex w-fit items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              Email code
            </div>
            <h1 className="mt-5 text-3xl font-semibold leading-tight text-[var(--re-text-primary)]">
              Enter your 6-digit sign-in code.
            </h1>
            <CardDescription className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">
              {state?.email ? (
                <span className="inline-flex items-center gap-2">
                  <Mail className="h-4 w-4" aria-hidden="true" />
                  If this address is eligible, use the code sent to {state.email}
                </span>
              ) : (
                'Use the same browser where you requested the sign-in code.'
              )}
            </CardDescription>
          </CardHeader>

          <CardContent className="px-5 pb-6 sm:px-8 sm:pb-8">
            {!state?.challengeId && (
              <div className="mb-4 border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/10 dark:text-amber-300" role="status">
                We could not find a challenge ID for this code. Request a new code, then return here from the same browser.
              </div>
            )}

            {error && (
              <div
                id="otp-error"
                role="alert"
                aria-live="polite"
                className="mb-4 border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/10 dark:text-red-400"
              >
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium leading-none text-[var(--re-text-secondary)]" htmlFor="otp-code">
                  Verification code
                </label>
                <Input
                  id="otp-code"
                  name="code"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  autoComplete="one-time-code"
                  placeholder="123456"
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                  disabled={isSubmitting}
                  aria-invalid={!!error}
                  aria-describedby={error ? 'otp-error' : undefined}
                  className="h-12 font-mono text-lg tracking-[0.24em]"
                />
              </div>

              <Button className="h-12 w-full gap-2" type="submit" disabled={isSubmitting || !state?.challengeId}>
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  <>
                    Verify and continue
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </>
                )}
              </Button>
            </form>

            <div className="mt-5 border-t border-[var(--re-border-subtle)] pt-5 text-center">
              <Button asChild variant="ghost" className="gap-2">
                <Link href="/login">
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Request a new code
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
