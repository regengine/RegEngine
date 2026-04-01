'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Building2, ArrowRight, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useOrganizations } from '@/hooks/use-organizations';
import { useUpdateOnboarding } from '@/hooks/use-onboarding';

const ROLES = [
  { value: 'compliance_manager', label: 'Compliance Manager' },
  { value: 'qa_director', label: 'QA Director' },
  { value: 'operations', label: 'Operations' },
  { value: 'it_engineering', label: 'IT & Engineering' },
  { value: 'owner_executive', label: 'Owner / Executive' },
];

const COMPANY_TYPES = [
  { value: 'manufacturer', label: 'Manufacturer' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'retailer', label: 'Retailer' },
  { value: 'restaurant', label: 'Restaurant & Foodservice' },
  { value: 'farm_grower', label: 'Farm & Grower' },
];

const COMPLIANCE_STATUSES = [
  { value: 'not_started', label: 'Not started yet' },
  { value: 'exploring', label: 'Exploring options' },
  { value: 'implementing', label: 'Actively implementing' },
  { value: 'compliant', label: 'Already compliant' },
];

export default function WelcomePage() {
  const router = useRouter();
  const { user } = useAuth();
  const { tenantId } = useTenant();
  const { organizations } = useOrganizations();
  const tenantName = organizations?.find((o) => o.id === tenantId)?.name;
  const updateOnboarding = useUpdateOnboarding(tenantId);

  const [role, setRole] = useState('');
  const [companyType, setCompanyType] = useState('');
  const [complianceStatus, setComplianceStatus] = useState('');

  const isValid = role && companyType && complianceStatus;

  const handleContinue = async () => {
    if (!isValid || !tenantId) return;

    await updateOnboarding.mutateAsync({
      workspace_profile: {
        user_role: role,
        company_type: companyType,
        compliance_status: complianceStatus,
        completed_at: new Date().toISOString(),
      },
      onboarding: {
        workspace_setup_completed: true,
      },
    });

    router.push('/onboarding/setup/facility');
  };

  return (
    <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
      <CardHeader className="space-y-2 pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--re-brand)]/10">
            <Building2 className="h-5 w-5 text-[var(--re-brand)]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--re-text-primary)]">
              Welcome to RegEngine{tenantName ? `, ${tenantName}` : ''}
            </h1>
            <p className="text-sm text-[var(--re-text-muted)]">
              Help us tailor your workspace — this takes about 10 seconds.
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Your role
          </label>
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger>
              <SelectValue placeholder="Select your role" />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r.value} value={r.value}>
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Company type
          </label>
          <Select value={companyType} onValueChange={setCompanyType}>
            <SelectTrigger>
              <SelectValue placeholder="Select company type" />
            </SelectTrigger>
            <SelectContent>
              {COMPANY_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-[var(--re-text-secondary)]">
            Compliance status
          </label>
          <Select value={complianceStatus} onValueChange={setComplianceStatus}>
            <SelectTrigger>
              <SelectValue placeholder="Where are you on your FSMA 204 journey?" />
            </SelectTrigger>
            <SelectContent>
              {COMPLIANCE_STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          className="h-11 w-full"
          disabled={!isValid || updateOnboarding.isPending}
          onClick={handleContinue}
        >
          {updateOnboarding.isPending ? (
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
