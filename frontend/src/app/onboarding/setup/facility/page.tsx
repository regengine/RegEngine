'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Factory, ArrowRight, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
            'Validation failed — check your facility details and try again.',
        );
      } else if (status === 409) {
        setError(
          'A facility with this name already exists in your account. Use a different name.',
        );
      } else if (status === 429) {
        setError('Too many requests. Please wait a moment and try again.');
      } else if (status !== undefined && status >= 500) {
        setError(
          'Could not save facility — server error. Try again or email support@regengine.co.',
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
    <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
      <CardHeader className="space-y-2 pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-re-brand-muted">
            <Factory className="h-5 w-5 text-re-brand" />
          </div>
          <div>
            <div className="mb-1">
              <StepIndicator step={2} />
            </div>
            <h1 className="text-xl font-semibold text-[var(--re-text-primary)]">
              Register Your First Facility
            </h1>
            <p className="text-sm text-[var(--re-text-muted)]">
              You can add more facilities later in Settings.
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {error && (
          <div className="rounded-md border border-re-danger/40 bg-re-danger-muted0/10 px-3 py-2 text-sm text-red-200" role="alert">
            {error}
          </div>
        )}

        {/* Facility name */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Facility name <span className="text-re-danger">*</span>
          </label>
          <Input
            placeholder="e.g. Salinas Valley Packhouse"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        {/* Street address — #539: real field replaces hardcoded '--' */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Street address <span className="text-re-danger">*</span>
          </label>
          <Input
            placeholder="e.g. 1234 Harvest Rd"
            value={street}
            onChange={(e) => setStreet(e.target.value)}
          />
        </div>

        {/* City / State */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              City <span className="text-re-danger">*</span>
            </label>
            <Input
              placeholder="e.g. Salinas"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              State <span className="text-re-danger">*</span>
            </label>
            <Select value={state} onValueChange={setState}>
              <SelectTrigger>
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
          </div>
        </div>

        {/* ZIP / FDA reg — #539: ZIP required with format validation */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              ZIP code <span className="text-re-danger">*</span>
            </label>
            <Input
              placeholder="e.g. 93901"
              value={zip}
              onChange={(e) => setZip(e.target.value)}
              aria-invalid={zipInvalid}
            />
            {zipInvalid && (
              <p className="text-xs text-re-danger">
                Enter a valid 5-digit ZIP (or ZIP+4 e.g. 93901-1234).
              </p>
            )}
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              FDA registration #
            </label>
            <Input
              placeholder="Optional"
              value={fdaReg}
              onChange={(e) => setFdaReg(e.target.value)}
            />
          </div>
        </div>

        {/* Supply chain roles */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Supply chain role(s)
          </label>
          <div className="flex flex-wrap gap-2">
            {SUPPLY_CHAIN_ROLES.map((role) => (
              <button
                key={role}
                type="button"
                onClick={() => toggleRole(role)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  roles.includes(role)
                    ? 'border-[var(--re-brand)] bg-[var(--re-brand)]/10 text-[var(--re-brand)]'
                    : 'border-[var(--re-surface-border)] text-[var(--re-text-muted)] hover:border-[var(--re-text-muted)]'
                }`}
              >
                {role}
              </button>
            ))}
          </div>
        </div>

        <Button
          className="h-11 w-full"
          disabled={!isValid || saving}
          onClick={handleSubmit}
        >
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              Continue
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
