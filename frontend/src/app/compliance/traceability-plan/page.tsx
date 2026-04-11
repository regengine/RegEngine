'use client';

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
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
  CheckCircle,
  Loader2,
  Leaf,
  Package,
  Truck,
  ShoppingCart,
  UtensilsCrossed,
} from 'lucide-react';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useApiMutate } from '@/hooks/use-api-query';

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
      <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        <PageContainer>
          <div className="max-w-4xl mx-auto py-12 space-y-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-lg bg-re-success-muted dark:bg-green-900">
                  <CheckCircle className="h-8 w-8 text-re-success dark:text-re-success" />
                </div>
                <div>
                  <h1 className="text-3xl font-bold">Traceability Plan Generated</h1>
                  <p className="text-muted-foreground">
                    {firmData.firm_name} &mdash; FSMA 204 Compliant
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleDownload}>
                  <Download className="w-4 h-4 mr-2" />
                  Download (.md)
                </Button>
                <Button variant="outline" onClick={() => { setGeneratedPlan(null); setStep(4); }}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Regenerate
                </Button>
              </div>
            </div>

            <Card>
              <CardContent className="pt-6">
                <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap font-mono text-sm leading-relaxed">
                  {generatedPlan}
                </div>
              </CardContent>
            </Card>
          </div>
        </PageContainer>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <div className="max-w-3xl mx-auto py-12">
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-re-info-muted dark:bg-blue-900">
              <FileText className="h-8 w-8 text-re-info dark:text-re-info" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">Traceability Plan</h1>
              <p className="text-muted-foreground mt-1">
                Generate your FSMA 204 traceability plan in minutes
              </p>
            </div>
          </div>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <CardTitle>{STEPS[step].title}</CardTitle>
                  <CardDescription>{STEPS[step].description}</CardDescription>
                </div>
                <Badge variant="outline">
                  Step {step + 1} of {STEPS.length}
                </Badge>
              </div>
              <Progress value={progress} className="h-2" />
            </CardHeader>

            <CardContent className="min-h-[400px]">
              <AnimatePresence mode="wait">
                <motion.div
                  key={step}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.2 }}
                >
                  {step === 0 && (
                    <div className="space-y-4">
                      <InputField label="Firm Name" required value={firmData.firm_name}
                        onChange={v => handleFieldChange('firm_name', v)} icon={Building2} placeholder="Your company name" />
                      <InputField label="Address" required value={firmData.firm_address}
                        onChange={v => handleFieldChange('firm_address', v)} icon={MapPin} placeholder="123 Main St, Anytown, CA 90210" />
                      <InputField label="Contact Name" value={firmData.contact_name}
                        onChange={v => handleFieldChange('contact_name', v)} icon={Building2} placeholder="Jane Smith" />
                      <InputField label="Contact Email" value={firmData.contact_email}
                        onChange={v => handleFieldChange('contact_email', v)} icon={Mail} placeholder="contact@yourcompany.com" />
                      <InputField label="Contact Phone" value={firmData.contact_phone}
                        onChange={v => handleFieldChange('contact_phone', v)} icon={Phone} placeholder="(555) 123-4567" />
                      <InputField label="GLN (optional)" value={firmData.gln}
                        onChange={v => handleFieldChange('gln', v)} icon={Hash} placeholder="0614141000005" />
                      <InputField label="FDA Registration (optional)" value={firmData.fda_registration}
                        onChange={v => handleFieldChange('fda_registration', v)} icon={Hash} placeholder="12345678" />
                    </div>
                  )}

                  {step === 1 && (
                    <div className="grid grid-cols-2 gap-3">
                      {FIRM_TYPES.map(ft => {
                        const Icon = ft.icon;
                        const isSelected = firmType === ft.id;
                        return (
                          <button
                            key={ft.id}
                            onClick={() => setFirmType(ft.id)}
                            className={`p-4 rounded-lg border text-left transition-all ${
                              isSelected
                                ? 'border-primary bg-primary/10 ring-2 ring-primary'
                                : 'border-border hover:border-primary/50 hover:bg-muted/50'
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <Icon className={`h-5 w-5 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                              <span className="font-medium">{ft.label}</span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {step === 2 && (
                    <div className="space-y-4">
                      <p className="text-sm text-muted-foreground">
                        Select the FDA Food Traceability List commodities your facility handles.
                      </p>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                        {FTL_COMMODITIES.map(comm => {
                          const isSelected = selectedCommodities.includes(comm.name);
                          return (
                            <button
                              key={comm.name}
                              onClick={() => toggleCommodity(comm.name)}
                              className={`p-3 rounded-lg border text-left text-sm transition-all ${
                                isSelected
                                  ? 'border-primary bg-primary/10'
                                  : 'border-border hover:border-primary/50'
                              }`}
                            >
                              <span className={isSelected ? 'font-medium' : ''}>{comm.name}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {step === 3 && (
                    <div className="space-y-6">
                      <div>
                        <label className="text-sm font-medium mb-2 block">Record Storage Type</label>
                        <div className="flex gap-3">
                          {['electronic', 'paper', 'hybrid'].map(type => (
                            <button
                              key={type}
                              onClick={() => setRecordSystem(type)}
                              className={`px-4 py-2 rounded-lg border capitalize transition-all ${
                                recordSystem === type
                                  ? 'border-primary bg-primary/10 font-medium'
                                  : 'border-border hover:border-primary/50'
                              }`}
                            >
                              {type}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div>
                        <label className="text-sm font-medium mb-2 block">TLC Format Template</label>
                        <input
                          type="text"
                          value={tlcFormat}
                          onChange={e => setTlcFormat(e.target.value)}
                          className="w-full px-3 py-2 border rounded-lg bg-background font-mono text-sm"
                          placeholder="[PLANT]-[YYYYMMDD]-[SEQ]"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                          Example: ACME-20260404-001
                        </p>
                      </div>
                    </div>
                  )}

                  {step === 4 && (
                    <div className="space-y-4">
                      <h3 className="font-semibold">Review Your Information</h3>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">Firm</p>
                          <p className="font-medium">{firmData.firm_name}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Type</p>
                          <p className="font-medium capitalize">{firmType}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Address</p>
                          <p className="font-medium">{firmData.firm_address}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Contact</p>
                          <p className="font-medium">{firmData.contact_name || 'Not provided'}</p>
                        </div>
                        <div className="col-span-2">
                          <p className="text-muted-foreground">Commodities ({selectedCommodities.length})</p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {selectedCommodities.map(c => (
                              <Badge key={c} variant="secondary">{c}</Badge>
                            ))}
                          </div>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Records</p>
                          <p className="font-medium capitalize">{recordSystem}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">TLC Format</p>
                          <p className="font-mono text-xs">{tlcFormat}</p>
                        </div>
                      </div>

                      <Button
                        className="w-full mt-6"
                        size="lg"
                        onClick={handleGenerate}
                        disabled={generatePlan.isPending}
                      >
                        {generatePlan.isPending ? (
                          <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Generating Plan...
                          </>
                        ) : (
                          <>
                            <FileText className="w-4 h-4 mr-2" />
                            Generate Traceability Plan
                          </>
                        )}
                      </Button>

                      {generatePlan.isError && (
                        <p className="text-sm text-re-danger text-center">
                          Failed to generate plan. Please try again.
                        </p>
                      )}
                    </div>
                  )}
                </motion.div>
              </AnimatePresence>
            </CardContent>

            <CardFooter className="flex justify-between">
              <Button
                variant="outline"
                onClick={() => setStep(prev => prev - 1)}
                disabled={step === 0}
              >
                <ChevronLeft className="h-4 w-4 mr-2" />
                Back
              </Button>

              {step < STEPS.length - 1 && (
                <Button
                  onClick={() => setStep(prev => prev + 1)}
                  disabled={!canProceed()}
                >
                  Next
                  <ChevronRight className="h-4 w-4 ml-2" />
                </Button>
              )}
            </CardFooter>
          </Card>
        </div>
      </PageContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Input field helper
// ---------------------------------------------------------------------------

function InputField({
  label, value, onChange, icon: Icon, placeholder, required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  icon: React.ElementType;
  placeholder: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="text-sm font-medium mb-1.5 block">
        {label}{required && <span className="text-re-danger ml-1">*</span>}
      </label>
      <div className="relative">
        <Icon className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-10 pr-3 py-2 border rounded-lg bg-background text-sm"
        />
      </div>
    </div>
  );
}
