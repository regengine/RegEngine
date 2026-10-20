'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Loader2, RotateCcw } from 'lucide-react';

import { AuthShell } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
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
    <AuthShell
      title="Enter your 6-digit sign-in code."
      description={
        state?.email
          ? `A sign-in code is sent only if the email has an invited account. If you received a code for ${state.email}, enter it below.`
          : 'A sign-in code is sent only if the email has an invited account. Use the same browser where you requested the code.'
      }
      footer={
        <Link
          href="/login"
          className="inline-flex items-center gap-2 font-medium text-re-text-secondary underline-offset-[3px] transition-colors duration-120 hover:text-re-text-primary hover:underline motion-reduce:transition-none"
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          Request a new code
        </Link>
      }
    >
      {!state?.challengeId && (
        <Callout tone="warning" role="status" className="mb-4">
          We could not find a challenge ID for this code. Request a new code, then return here from the same browser.
        </Callout>
      )}

      {error && (
        <Callout
          id="otp-error"
          tone="danger"
          role="alert"
          aria-live="polite"
          className="mb-4"
        >
          {error}
        </Callout>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Verification code" htmlFor="otp-code">
          <Input
            id="otp-code"
            name="code"
            type="text"
            size="lg"
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
            className="font-mono text-lg tracking-[0.24em]"
          />
        </Field>

        <Button className="w-full" size="lg" type="submit" disabled={isSubmitting || !state?.challengeId}>
          {isSubmitting ? (
            <>
              <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Verifying...
            </>
          ) : (
            <>
              Verify and continue
              <ArrowRight aria-hidden="true" />
            </>
          )}
        </Button>
      </form>
    </AuthShell>
  );
}
