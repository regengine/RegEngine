'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth-context';
import { useUpdateOnboarding } from '@/hooks/use-onboarding';
import { apiClient } from '@/lib/api-client';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { US_STATES, SUPPLY_CHAIN_ROLES } from '@/lib/constants';

// #539 — US ZIP: 5 digits or 5+4 (e.g. 93901 or 93901-1234)
const ZIP_RE = /^\d{5}(-\d{4})?$/;

// #540 — UUID v4 format expected from the API
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function FacilityPage() {
  const router = useRouter();
  const { tenantId } = useAuth();
  const updateOnboarding = useUpdateOnboarding(tenantId);

  const [name, setName] = useState('');
  const [street, setStreet] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [zip, setZip] = useState('');
  const [fdaReg, setFdaReg] = useState('');
  const [roles, setRoles] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggleRole = (role: string) => {
    setRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    );
  };

  // #539 — ZIP is required and must match the US ZIP pattern
  const zipValid = ZIP_RE.test(zip);
  const zipInvalid = zip.length > 0 && !zipValid;

  const isValid =
    name.trim().length >= 2 &&
    street.trim().length >= 2 &&
    city.trim().length >= 2 &&
    !!state &&
    zipValid;

  const handleSubmit = async () => {
    if (!isValid || !tenantId) return;
    setSaving(true);
    setError('');

    try {
      const facility = await apiClient.createSupplierFacility({
        name,
        street,           // #539 — real value, no '--' placeholder
        city,
        state,
        postal_code: zip, // #539 — required, validated above
        fda_registration_number: fdaReg.trim() || undefined,
        roles,
      });

      // #540 — Validate the returned facility ID before navigating.
      // An empty or malformed ID would produce an unusable URL and a broken
      // next step. Surface the problem here rather than silently navigating.
      const facilityId = facility?.id;
      if (!facilityId || !UUID_RE.test(String(facilityId))) {
        setError(
          'Facility was saved but returned an invalid ID. ' +
          'Please refresh the page and try the next step again.',
        );
        return;
      }

      await updateOnboarding.mutateAsync({
        onboarding: { facility_created: true },
      });

      router.push(`/onboarding/setup/ftl-check?facilityId=${facilityId}`);
    } catch (err: unknown) {
      const apiError = err as {
        response?: { status?: number; data?: { detail?: string } };
      };
      const status = apiError.response?.status;
      if (!apiError.response) {
        const offline = typeof navigator !== 'undefined' && !navigator.onLine;
        setError(
          offline
            ? 'You appear to be offline. Check your connection and try again.'
            : 'Could not reach the server. Check your connection and try again.',
        );
      } else if (status === 400 || status === 422) {
        setError(
          apiError.response.data?.detail ||
            'Validation failed. Check your facility details and try again.',
        );
      } else if (status === 409) {
        setError(
          'A facility with this name already exists in your account. Use a different name.',
        );
      } else if (status === 429) {
        setError('Too many requests. Please wait a moment and try again.');
      } else if (status !== undefined && status >= 500) {
        setError(
          'Could not save facility (server error). Try again or email support@regengine.co.',
        );
      } else {
        setError(
          'Could not save facility. Please try again or email support@regengine.co.',
        );
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card padding="spacious">
      <StepIndicator step={2} />
      <h1 className="mt-4 text-heading text-re-text-primary">
        Register Your First Facility
      </h1>
      <p className="mt-1 text-ui text-re-text-secondary">
        You can add more facilities later under Suppliers.
      </p>

      <div className="mt-6 space-y-5">
        {error && (
          <Callout tone="danger" role="alert">
            {error}
          </Callout>
        )}

        {/* Facility name */}
        <Field label="Facility name" htmlFor="facility-name" required>
          <Input
            id="facility-name"
            size="lg"
            placeholder="e.g. Salinas Valley Packhouse"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>

        {/* Street address — #539: real field replaces hardcoded '--' */}
        <Field label="Street address" htmlFor="facility-street" required>
          <Input
            id="facility-street"
            size="lg"
            placeholder="e.g. 1234 Harvest Rd"
            value={street}
            onChange={(e) => setStreet(e.target.value)}
          />
        </Field>

        {/* City / State */}
        <div className="grid grid-cols-2 gap-3">
          <Field label="City" htmlFor="facility-city" required>
            <Input
              id="facility-city"
              size="lg"
              placeholder="e.g. Salinas"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </Field>
          <Field label="State" htmlFor="facility-state" required>
            <Select value={state} onValueChange={setState}>
              <SelectTrigger id="facility-state" className="h-11">
                <SelectValue placeholder="State" />
              </SelectTrigger>
              <SelectContent>
                {US_STATES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>

        {/* ZIP / FDA reg — #539: ZIP required with format validation */}
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="ZIP code"
            htmlFor="facility-zip"
            required
            error={zipInvalid ? 'Enter a valid 5-digit ZIP (or ZIP+4 e.g. 93901-1234).' : undefined}
          >
            <Input
              id="facility-zip"
              size="lg"
              placeholder="e.g. 93901"
              value={zip}
              onChange={(e) => setZip(e.target.value)}
              aria-invalid={zipInvalid}
            />
          </Field>
          <Field label="FDA registration #" htmlFor="facility-fda-reg">
            <Input
              id="facility-fda-reg"
              size="lg"
              placeholder="Optional"
              value={fdaReg}
              onChange={(e) => setFdaReg(e.target.value)}
            />
          </Field>
        </div>

        {/* Supply chain roles */}
        <fieldset>
          <legend className="text-ui font-medium text-re-text-primary">
            Supply chain role(s)
          </legend>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {SUPPLY_CHAIN_ROLES.map((role) => {
              const selected = roles.includes(role);
              return (
                <button
                  key={role}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => toggleRole(role)}
                  className={cn(
                    'rounded-full border px-3 py-1.5 text-small font-medium transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none',
                    selected
                      ? 'border-re-text-primary bg-re-surface-inset text-re-text-primary'
                      : 'border-re-border text-re-text-secondary hover:border-re-border-strong',
                  )}
                >
                  {role}
                </button>
              );
            })}
          </div>
        </fieldset>
      </div>

      <div className="mt-8 flex flex-col-reverse gap-3 border-t border-re-border-subtle pt-5 sm:flex-row sm:items-center sm:justify-between">
        <Button
          variant="ghost"
          size="lg"
          onClick={() => router.push('/dashboard')}
        >
          Skip for now. I&apos;ll set up later
        </Button>
        <Button
          size="lg"
          disabled={!isValid || saving}
          onClick={handleSubmit}
        >
          {saving ? (
            <>
              <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Saving...
            </>
          ) : (
            <>
              Continue
              <ArrowRight aria-hidden="true" />
            </>
          )}
        </Button>
      </div>
    </Card>
  );
}
