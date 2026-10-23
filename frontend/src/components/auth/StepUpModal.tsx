'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Fingerprint, Loader2 } from 'lucide-react';

import { PasskeyRequiredNotice } from '@/components/auth/PasskeyRequiredNotice';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';
import { isValidEmail, performPasskeyLogin, seedPasswordlessClientUser } from '@/lib/passwordless-auth';
import {
  DEFAULT_STEP_UP_REASON,
  STEP_UP_REQUIRED_EVENT,
  type StepUpEventDetail,
} from '@/lib/step-up-events';

export function StepUpModal() {
  const { user } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(DEFAULT_STEP_UP_REASON);
  const [returnTo, setReturnTo] = useState<string | undefined>();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const onStepUpRequired = (event: Event) => {
      const detail = (event as CustomEvent<StepUpEventDetail | null>).detail;
      if (user?.email) {
        setEmail(user.email);
      }
      setReason(detail?.reason || DEFAULT_STEP_UP_REASON);
      setReturnTo(detail?.returnTo);
      setOpen(true);
      setError(null);
    };

    window.addEventListener(STEP_UP_REQUIRED_EVENT, onStepUpRequired);
    return () => window.removeEventListener(STEP_UP_REQUIRED_EVENT, onStepUpRequired);
  }, [user?.email]);

  const handleCancel = () => {
    setOpen(false);
    setError(null);
    if (returnTo) {
      router.push(returnTo);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!isValidEmail(normalizedEmail)) {
      setError('Enter your email to continue with a passkey.');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await performPasskeyLogin(normalizedEmail);
      seedPasswordlessClientUser(normalizedEmail);
      setOpen(false);
      window.location.reload();
    } catch (err: unknown) {
      const browserError = err instanceof Error || err instanceof DOMException;
      setError(browserError && err.name === 'SecurityError'
        ? 'Passkey verification is unavailable on this domain. Contact support to verify the passkey domain configuration. This action remains blocked.'
        : browserError ? err.message : 'Passkey authentication failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : handleCancel())}>
      <DialogContent className="border-re-border bg-re-surface-card sm:max-w-md">
        <DialogHeader>
          <Badge tone="neutral" mono className="mb-2 w-fit uppercase">
            <Fingerprint className="h-3.5 w-3.5" aria-hidden="true" />
            Passkey required
          </Badge>
          <DialogTitle>Confirm it&apos;s you</DialogTitle>
          <DialogDescription>{reason}</DialogDescription>
        </DialogHeader>

        {error && <PasskeyRequiredNotice>{error}</PasskeyRequiredNotice>}

        <form onSubmit={handleSubmit} className="space-y-3">
          <Field label="Email address" htmlFor="step-up-email">
            <Input
              id="step-up-email"
              type="email"
              size="lg"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="email webauthn"
              disabled={isSubmitting}
            />
          </Field>
          <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                Waiting for passkey...
              </>
            ) : (
              <>
                Authenticate with passkey
                <Fingerprint aria-hidden="true" />
              </>
            )}
          </Button>
        </form>

        <DialogFooter>
          <Button type="button" variant="ghost" className="w-full" onClick={handleCancel}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
