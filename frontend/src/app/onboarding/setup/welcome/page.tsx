'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/lib/auth-context';
import { useUpdateOnboarding } from '@/hooks/use-onboarding';
import { StepIndicator } from '@/components/onboarding/StepIndicator';

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
  const { tenantId } = useAuth();
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
    <Card padding="spacious">
      <StepIndicator step={1} />
      <h1 className="mt-4 text-heading text-re-text-primary">
        Welcome to RegEngine
      </h1>
      <p className="mt-1 text-ui text-re-text-secondary">
        Help us tailor your workspace. This takes about 10 seconds.
      </p>

      <div className="mt-6 space-y-5">
        <Field label="Your role" htmlFor="onboarding-role">
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger id="onboarding-role" className="h-11">
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
        </Field>

        <Field label="Company type" htmlFor="onboarding-company-type">
          <Select value={companyType} onValueChange={setCompanyType}>
            <SelectTrigger id="onboarding-company-type" className="h-11">
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
        </Field>

        <Field label="Compliance status" htmlFor="onboarding-compliance-status">
          <Select value={complianceStatus} onValueChange={setComplianceStatus}>
            <SelectTrigger id="onboarding-compliance-status" className="h-11">
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
        </Field>
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
          disabled={!isValid || updateOnboarding.isPending}
          onClick={handleContinue}
        >
          {updateOnboarding.isPending ? (
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
