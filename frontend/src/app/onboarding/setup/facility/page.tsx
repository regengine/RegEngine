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

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
  'VA','WA','WV','WI','WY','DC','PR','GU','VI',
];

const SUPPLY_CHAIN_ROLES = [
  'Grower',
  'Packer',
  'Processor',
  'Distributor',
  'Importer',
];

export default function FacilityPage() {
  const router = useRouter();
  const { tenantId } = useAuth();
  const updateOnboarding = useUpdateOnboarding(tenantId);

  const [name, setName] = useState('');
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

  const isValid = name.length >= 2 && city.length >= 2 && state;

  const handleSubmit = async () => {
    if (!isValid || !tenantId) return;
    setSaving(true);
    setError('');

    try {
      const facility = await apiClient.createSupplierFacility({
        name,
        street: '--',
        city,
        state,
        postal_code: zip || '00000',
        fda_registration_number: fdaReg || undefined,
        roles,
      });

      await updateOnboarding.mutateAsync({
        onboarding: { facility_created: true },
      });

      router.push(`/onboarding/setup/ftl-check?facilityId=${facility.id}`);
    } catch {
      setError('Could not save facility. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
      <CardHeader className="space-y-2 pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10">
            <Factory className="h-5 w-5 text-emerald-500" />
          </div>
          <div>
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
          <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">
            {error}
          </div>
        )}

        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Facility name <span className="text-red-400">*</span>
          </label>
          <Input
            placeholder="e.g. Salinas Valley Packhouse"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              City <span className="text-red-400">*</span>
            </label>
            <Input
              placeholder="e.g. Salinas"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              State <span className="text-red-400">*</span>
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

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <label className="text-sm font-medium text-[var(--re-text-secondary)]">
              ZIP code
            </label>
            <Input
              placeholder="e.g. 93901"
              value={zip}
              onChange={(e) => setZip(e.target.value)}
            />
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
