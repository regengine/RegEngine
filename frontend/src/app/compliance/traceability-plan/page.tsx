'use client';

import React, { useState, useCallback } from 'react';
import {
  FileText,
  Building2,
  MapPin,
  Phone,
  Mail,
  Hash,
  ChevronRight,
  ChevronLeft,
  Download,
  RefreshCw,
  Leaf,
  Package,
  Truck,
  ShoppingCart,
  UtensilsCrossed,
} from 'lucide-react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { useApiMutate } from '@/hooks/use-api-query';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FIRM_TYPES = [
  { id: 'grower', label: 'Grower / Farm', icon: Leaf },
  { id: 'manufacturer', label: 'Manufacturer', icon: Package },
  { id: 'processor', label: 'Processor', icon: Package },
  { id: 'packer', label: 'Packer', icon: Package },
  { id: 'holder', label: 'Holder / Warehouse', icon: Building2 },
  { id: 'distributor', label: 'Distributor', icon: Truck },
  { id: 'retailer', label: 'Retailer', icon: ShoppingCart },
  { id: 'restaurant', label: 'Restaurant / Foodservice', icon: UtensilsCrossed },
];

const FTL_COMMODITIES = [
  { name: 'Leafy Greens', category: 'produce' },
  { name: 'Fresh Tomatoes', category: 'produce' },
  { name: 'Fresh Peppers', category: 'produce' },
  { name: 'Fresh Cucumbers', category: 'produce' },
  { name: 'Fresh Herbs', category: 'produce' },
  { name: 'Melons', category: 'produce' },
  { name: 'Tropical Tree Fruits', category: 'produce' },
  { name: 'Sprouts', category: 'produce' },
  { name: 'Fresh-Cut Fruits', category: 'produce' },
  { name: 'Fresh-Cut Vegetables', category: 'produce' },
  { name: 'Deli Salads', category: 'prepared' },
  { name: 'Finfish', category: 'seafood' },
  { name: 'Crustaceans', category: 'seafood' },
  { name: 'Molluscan Shellfish', category: 'seafood' },
  { name: 'Nut Butters', category: 'other' },
  { name: 'Shell Eggs', category: 'other' },
  { name: 'Soft Cheeses', category: 'dairy' },
];

const STEPS = [
  { id: 'firm', title: 'Firm Information', description: 'Your business details' },
  { id: 'type', title: 'Firm Type', description: 'Your role in the supply chain' },
  { id: 'commodities', title: 'Commodities', description: 'FTL products you handle' },
  { id: 'records', title: 'Record Keeping', description: 'Where you store records' },
  { id: 'review', title: 'Review & Generate', description: 'Confirm and generate your plan' },
];

const RECORD_TYPES = ['electronic', 'paper', 'hybrid'];

const selectableTileClasses = (selected: boolean) =>
  cn(
    'rounded-md border px-4 py-3 text-left text-ui transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none',
    selected
      ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
      : 'border-re-border bg-re-surface-card text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
  );

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface FirmFormData {
  firm_name: string;
  firm_address: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  gln: string;
  fda_registration: string;
}

export default function TraceabilityPlanPage() {
  const [step, setStep] = useState(0);
  const [firmData, setFirmData] = useState<FirmFormData>({
    firm_name: '', firm_address: '', contact_name: '',
    contact_email: '', contact_phone: '', gln: '', fda_registration: '',
  });
  const [firmType, setFirmType] = useState<string | null>(null);
  const [selectedCommodities, setSelectedCommodities] = useState<string[]>([]);
  const [recordSystem, setRecordSystem] = useState('electronic');
  const [tlcFormat, setTlcFormat] = useState('[PLANT]-[YYYYMMDD]-[SEQ]');
  const [generatedPlan, setGeneratedPlan] = useState<string | null>(null);

  const generatePlan = useApiMutate<{ plan_id: string; markdown?: string; plan?: Record<string, unknown> }, unknown>(
    '/fsma/plan/generate?format=markdown',
    { service: 'graph', method: 'POST' },
  );

  const progress = ((step + 1) / STEPS.length) * 100;

  const handleFieldChange = useCallback((field: keyof FirmFormData, value: string) => {
    setFirmData(prev => ({ ...prev, [field]: value }));
  }, []);

  const toggleCommodity = useCallback((name: string) => {
    setSelectedCommodities(prev =>
      prev.includes(name) ? prev.filter(c => c !== name) : [...prev, name]
    );
  }, []);

  const canProceed = () => {
    switch (step) {
      case 0: return firmData.firm_name.trim() !== '' && firmData.firm_address.trim() !== '';
      case 1: return firmType !== null;
      case 2: return selectedCommodities.length > 0;
      case 3: return true;
      default: return true;
    }
  };

  const handleGenerate = useCallback(() => {
    const payload = {
      firm_name: firmData.firm_name,
      firm_address: firmData.firm_address,
      firm_type: firmType!,
      gln: firmData.gln || null,
      fda_registration: firmData.fda_registration || null,
      contact_name: firmData.contact_name,
      contact_email: firmData.contact_email,
      contact_phone: firmData.contact_phone,
      commodities: selectedCommodities.map(name => ({
        name,
        category: FTL_COMMODITIES.find(c => c.name === name)?.category || 'produce',
        cte_types: ['receiving', 'shipping', 'transformation'],
        tlc_assignment_method: 'internal',
      })),
      record_locations: [{
        location_type: recordSystem,
        system_name: recordSystem === 'electronic' ? 'RegEngine' : 'Paper records',
        physical_address: firmData.firm_address,
        backup_procedure: 'Cloud backup with RegEngine',
        retention_period: '2_years',
      }],
      tlc_format: tlcFormat,
    };

    generatePlan.mutate(payload, {
      onSuccess: (data: Record<string, unknown>) => {
        // The markdown format returns raw text as StreamingResponse,
        // but if we get JSON back, extract the content
        if (typeof data === 'string') {
          setGeneratedPlan(data);
        } else if (data.markdown) {
          setGeneratedPlan(data.markdown as string);
        } else {
          setGeneratedPlan(JSON.stringify(data, null, 2));
        }
      },
    });
  }, [firmData, firmType, selectedCommodities, recordSystem, tlcFormat, generatePlan]);

  const handleDownload = useCallback(() => {
    if (!generatedPlan) return;
    const blob = new Blob([generatedPlan], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `traceability-plan-${firmData.firm_name.replace(/\s+/g, '-').toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [generatedPlan, firmData.firm_name]);

  // If plan is generated, show it
  if (generatedPlan) {
    return (
      <PageContainer width="tool">
        <PageHeader
          title="Traceability Plan Generated"
          description={`${firmData.firm_name} — FSMA 204 Traceability Plan`}
          secondaryActions={
            <>
              <Button variant="secondary" onClick={handleDownload}>
                <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Download (.md)
              </Button>
              <Button
                variant="secondary"
                onClick={() => { setGeneratedPlan(null); setStep(4); }}
              >
                <RefreshCw className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Regenerate
              </Button>
            </>
          }
        />

        <Card>
          <CardContent>
            <div className="overflow-x-auto whitespace-pre-wrap font-mono text-[0.8125rem] leading-relaxed text-re-text-secondary">
              {generatedPlan}
            </div>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer width="tool">
      <PageHeader
        title="Traceability Plan"
        description="Generate your FSMA 204 traceability plan in minutes"
      />

      <Card>
        <CardHeader className="flex-col items-stretch gap-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <CardTitle>{STEPS[step].title}</CardTitle>
              <CardDescription className="mt-1">{STEPS[step].description}</CardDescription>
            </div>
            <Badge tone="neutral" mono>
              Step {step + 1} of {STEPS.length}
            </Badge>
          </div>
          <Progress value={progress} className="h-1.5 bg-re-surface-inset" aria-label={`Step ${step + 1} of ${STEPS.length}`} />
        </CardHeader>

        <CardContent className="min-h-[400px]">
          {step === 0 && (
            <div className="space-y-4">
              <Field label="Firm Name" htmlFor="plan-firm-name" required>
                <Input
                  id="plan-firm-name"
                  value={firmData.firm_name}
                  onChange={e => handleFieldChange('firm_name', e.target.value)}
                  placeholder="Your company name"
                  leadingIcon={<Building2 strokeWidth={1.75} />}
                />
              </Field>
              <Field label="Address" htmlFor="plan-firm-address" required>
                <Input
                  id="plan-firm-address"
                  value={firmData.firm_address}
                  onChange={e => handleFieldChange('firm_address', e.target.value)}
                  placeholder="123 Main St, Anytown, CA 90210"
                  leadingIcon={<MapPin strokeWidth={1.75} />}
                />
              </Field>
              <Field label="Contact Name" htmlFor="plan-contact-name">
                <Input
                  id="plan-contact-name"
                  value={firmData.contact_name}
                  onChange={e => handleFieldChange('contact_name', e.target.value)}
                  placeholder="Jane Smith"
                  leadingIcon={<Building2 strokeWidth={1.75} />}
                />
              </Field>
              <Field label="Contact Email" htmlFor="plan-contact-email">
                <Input
                  id="plan-contact-email"
                  type="email"
                  value={firmData.contact_email}
                  onChange={e => handleFieldChange('contact_email', e.target.value)}
                  placeholder="contact@yourcompany.com"
                  leadingIcon={<Mail strokeWidth={1.75} />}
                />
              </Field>
              <Field label="Contact Phone" htmlFor="plan-contact-phone">
                <Input
                  id="plan-contact-phone"
                  type="tel"
                  value={firmData.contact_phone}
                  onChange={e => handleFieldChange('contact_phone', e.target.value)}
                  placeholder="(555) 123-4567"
                  leadingIcon={<Phone strokeWidth={1.75} />}
                />
              </Field>
              <Field label="GLN (optional)" htmlFor="plan-gln">
                <Input
                  id="plan-gln"
                  value={firmData.gln}
                  onChange={e => handleFieldChange('gln', e.target.value)}
                  placeholder="0614141000005"
                  leadingIcon={<Hash strokeWidth={1.75} />}
                  mono
                />
              </Field>
              <Field label="FDA Registration (optional)" htmlFor="plan-fda-registration">
                <Input
                  id="plan-fda-registration"
                  value={firmData.fda_registration}
                  onChange={e => handleFieldChange('fda_registration', e.target.value)}
                  placeholder="12345678"
                  leadingIcon={<Hash strokeWidth={1.75} />}
                  mono
                />
              </Field>
            </div>
          )}

          {step === 1 && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {FIRM_TYPES.map(ft => {
                const Icon = ft.icon;
                const isSelected = firmType === ft.id;
                return (
                  <button
                    key={ft.id}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => setFirmType(ft.id)}
                    className={selectableTileClasses(isSelected)}
                  >
                    <span className="flex items-center gap-3">
                      <Icon
                        className="h-4 w-4 shrink-0 text-re-text-tertiary"
                        strokeWidth={1.75}
                        aria-hidden="true"
                      />
                      <span className="font-medium">{ft.label}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <p className="text-ui text-re-text-secondary">
                Select the FDA Food Traceability List commodities your facility handles.
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3">
                {FTL_COMMODITIES.map(comm => {
                  const isSelected = selectedCommodities.includes(comm.name);
                  return (
                    <button
                      key={comm.name}
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => toggleCommodity(comm.name)}
                      className={selectableTileClasses(isSelected)}
                    >
                      <span className={isSelected ? 'font-medium' : undefined}>{comm.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <fieldset>
                <legend className="mb-2 text-ui font-medium text-re-text-primary">Record Storage Type</legend>
                <div className="flex flex-wrap gap-2">
                  {RECORD_TYPES.map(type => (
                    <button
                      key={type}
                      type="button"
                      aria-pressed={recordSystem === type}
                      onClick={() => setRecordSystem(type)}
                      className={cn(selectableTileClasses(recordSystem === type), 'capitalize')}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </fieldset>
              <Field
                label="TLC Format Template"
                htmlFor="plan-tlc-format"
                hint="Example: ACME-20260404-001"
              >
                <Input
                  id="plan-tlc-format"
                  type="text"
                  value={tlcFormat}
                  onChange={e => setTlcFormat(e.target.value)}
                  placeholder="[PLANT]-[YYYYMMDD]-[SEQ]"
                  mono
                />
              </Field>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <h3 className="text-subheading text-re-text-primary">Review Your Information</h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-label text-re-text-muted">Firm</p>
                  <p className="mt-1 text-ui text-re-text-primary">{firmData.firm_name}</p>
                </div>
                <div>
                  <p className="text-label text-re-text-muted">Type</p>
                  <p className="mt-1 text-ui capitalize text-re-text-primary">{firmType}</p>
                </div>
                <div>
                  <p className="text-label text-re-text-muted">Address</p>
                  <p className="mt-1 text-ui text-re-text-primary">{firmData.firm_address}</p>
                </div>
                <div>
                  <p className="text-label text-re-text-muted">Contact</p>
                  <p className="mt-1 text-ui text-re-text-primary">{firmData.contact_name || 'Not provided'}</p>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-label text-re-text-muted">Commodities ({selectedCommodities.length})</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {selectedCommodities.map(c => (
                      <Badge key={c} tone="neutral">{c}</Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-label text-re-text-muted">Records</p>
                  <p className="mt-1 text-ui capitalize text-re-text-primary">{recordSystem}</p>
                </div>
                <div>
                  <p className="text-label text-re-text-muted">TLC Format</p>
                  <p className="mt-1 font-mono text-[0.8125rem] text-re-text-primary">{tlcFormat}</p>
                </div>
              </div>

              <Button
                className="mt-6 w-full"
                size="lg"
                onClick={handleGenerate}
                loading={generatePlan.isPending}
                leadingIcon={<FileText strokeWidth={1.75} aria-hidden="true" />}
              >
                {generatePlan.isPending ? 'Generating Plan...' : 'Generate Traceability Plan'}
              </Button>

              {generatePlan.isError && (
                <Callout tone="danger" role="alert">
                  Failed to generate plan. Please try again.
                </Callout>
              )}
            </div>
          )}
        </CardContent>

        <CardFooter className="justify-between">
          <Button
            variant="secondary"
            onClick={() => setStep(prev => prev - 1)}
            disabled={step === 0}
          >
            <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            Back
          </Button>

          {step < STEPS.length - 1 && (
            <Button
              onClick={() => setStep(prev => prev + 1)}
              disabled={!canProceed()}
            >
              Next
              <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Button>
          )}
        </CardFooter>
      </Card>
    </PageContainer>
  );
}
