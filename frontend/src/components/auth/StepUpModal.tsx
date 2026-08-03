'use client';

import { FormEvent, useEffect, useState } from 'react';
import { Fingerprint, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';
import { isValidEmail, performPasskeyLogin, seedPasswordlessClientUser } from '@/lib/passwordless-auth';
import { STEP_UP_REQUIRED_EVENT } from '@/lib/step-up-events';

export function StepUpModal() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const onStepUpRequired = () => {
      if (user?.email) {
        setEmail(user.email);
      }
      setOpen(true);
      setError(null);
    };

    window.addEventListener(STEP_UP_REQUIRED_EVENT, onStepUpRequired);
    return () => window.removeEventListener(STEP_UP_REQUIRED_EVENT, onStepUpRequired);
  }, [user?.email]);

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
      setError(err instanceof Error ? err.message : 'Passkey authentication failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] sm:max-w-md">
        <DialogHeader>
          <div className="mb-2 inline-flex w-fit items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
            <Fingerprint className="h-3.5 w-3.5" aria-hidden="true" />
            Step-up required
          </div>
          <DialogTitle>Authenticate with your passkey</DialogTitle>
          <DialogDescription>
            This action requires a high-assurance session before it can continue.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div role="alert" className="border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/10 dark:text-red-400">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]" htmlFor="step-up-email">
              Email address
            </label>
            <Input
              id="step-up-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="email webauthn"
              disabled={isSubmitting}
            />
          </div>
          <Button type="submit" className="h-11 w-full gap-2" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Waiting for passkey...
              </>
            ) : (
              <>
                Authenticate with passkey
                <Fingerprint className="h-4 w-4" aria-hidden="true" />
              </>
            )}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
