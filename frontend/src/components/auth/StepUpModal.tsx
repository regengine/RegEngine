'use client';

import { FormEvent, useEffect, useState } from 'react';
import { Fingerprint, Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
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
      <DialogContent className="border-re-border bg-re-surface-card sm:max-w-md">
        <DialogHeader>
          <Badge tone="neutral" mono className="mb-2 w-fit uppercase">
            <Fingerprint className="h-3.5 w-3.5" aria-hidden="true" />
            Step-up required
          </Badge>
          <DialogTitle>Authenticate with your passkey</DialogTitle>
          <DialogDescription>
            This action requires a high-assurance session before it can continue.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Callout tone="danger" role="alert">
            {error}
          </Callout>
        )}

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
      </DialogContent>
    </Dialog>
  );
}
