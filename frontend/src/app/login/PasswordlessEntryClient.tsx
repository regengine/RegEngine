'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowRight, Fingerprint, Loader2, Mail } from 'lucide-react';

import { AuthShell } from '@/components/auth/AuthShell';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
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

export default function PasswordlessEntryClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, isHydrated } = useAuth();
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
    // Gate on isAuthenticated (user + cookie-backed access token), not user
    // alone: `user` hydrates from localStorage and can outlive the
    // re_access_token cookie. Forwarding on stale user state ping-pongs with
    // the server-side auth gates (e.g. /developer/portal layout), producing
    // an infinite login <-> next-path redirect loop.
    if (!isHydrated || !isAuthenticated) return;
    router.push(nextPath);
  }, [isHydrated, nextPath, router, isAuthenticated]);

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
    <AuthShell
      title="Continue to RegEngine"
      description="Enter your email to receive a one-time code, or use a registered passkey."
      notice={
        <Callout tone="neutral">
          Enterprise policy is enforced before codes are sent.
        </Callout>
      }
      footer={
        <Link
          href="/"
          className="font-medium text-re-text-secondary underline-offset-[3px] transition-colors duration-120 hover:text-re-text-primary hover:underline motion-reduce:transition-none"
        >
          Return to RegEngine.co
        </Link>
      }
    >
      {queryError === 'session_expired' && (
        <Callout tone="info" role="status" className="mb-4">
          Your session expired. Sign in again to continue.
        </Callout>
      )}

      {queryError === 'tenant_suspended' && (
        <Callout tone="info" role="status" className="mb-4">
          Your account is not active. Contact your administrator or RegEngine support to restore access.
        </Callout>
      )}

      {queryError === 'tenant_status_unavailable' && (
        <Callout tone="info" role="status" className="mb-4">
          We couldn&apos;t verify your account status just now. Please sign in again.
        </Callout>
      )}

      {statusMessage && (
        <Callout tone="info" role="status" className="mb-4">
          {statusMessage}
        </Callout>
      )}

      {error && (
        <Callout
          id="login-error"
          tone="danger"
          role="alert"
          aria-live="polite"
          className="mb-4"
        >
          {error}
        </Callout>
      )}

      <form onSubmit={handleEmailSubmit} className="space-y-4">
        <Field label="Email address" htmlFor="email">
          <Input
            id="email"
            name="email"
            type="email"
            size="lg"
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
            leadingIcon={<Mail aria-hidden="true" />}
          />
        </Field>

        <Button className="w-full" size="lg" type="submit" disabled={busy}>
          {isEmailSubmitting ? (
            <>
              <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Sending code...
            </>
          ) : (
            <>
              Continue
              <ArrowRight aria-hidden="true" />
            </>
          )}
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3 text-label uppercase text-re-text-muted">
        <div className="h-px flex-1 bg-re-border-subtle" />
        or
        <div className="h-px flex-1 bg-re-border-subtle" />
      </div>

      <Button
        className="w-full"
        size="lg"
        type="button"
        variant="secondary"
        disabled={busy}
        onClick={() => {
          setPasskeyEmail(email);
          setShowPasskeyPrompt(true);
        }}
      >
        <Fingerprint aria-hidden="true" />
        Sign in with passkey
      </Button>

      {showPasskeyPrompt && (
        <form
          onSubmit={handlePasskeySubmit}
          className="mt-4 space-y-3 rounded-md border border-re-border-subtle bg-re-surface-inset p-3"
        >
          <Field label="Passkey email" htmlFor="passkey-email">
            <Input
              id="passkey-email"
              type="email"
              size="lg"
              value={passkeyEmail}
              onChange={(event) => setPasskeyEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="email webauthn"
              disabled={busy}
            />
          </Field>
          <Button type="submit" className="w-full" size="lg" variant="secondary" disabled={busy}>
            {isPasskeySubmitting ? (
              <>
                <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                Waiting for passkey...
              </>
            ) : (
              <>
                Sign in with passkey
                <Fingerprint aria-hidden="true" />
              </>
            )}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
