'use client';

import { useEffect, useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import { StatTile } from '@/components/ui/stat-tile';
import { useInitializeLabelBatch } from '@/hooks/use-api';
import { Package, Printer, CheckCircle } from 'lucide-react';
import { useTenant } from '@/lib/tenant-context';
import type { LabelFormData, LabelBatchInitResponse } from '@/types/labels';
import dynamic from 'next/dynamic';

const LabelPdfDownloadSection = dynamic(
  () => import('@/components/labels/LabelPdfDownloadSection'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-10 flex-1 items-center justify-center rounded-md bg-re-surface-inset">
        <span className="text-small text-re-text-tertiary">Loading PDF renderer...</span>
      </div>
    ),
  }
);

type Step = 'input' | 'generating' | 'preview';

export default function LabelsPage() {
  const { tenantId } = useTenant();
  const [step, setStep] = useState<Step>('input');
  const [formData, setFormData] = useState<LabelFormData>({
    packerGln: '',
    gtin: '',
    productDescription: '',
    plu: '',
    expectedUnits: 1,
    lotNumber: '',
    packDate: new Date().toISOString().split('T')[0],
    growerGln: '',
    quantity: 100,
    unitOfMeasure: 'EA',
    packagingLevel: 'item',
  });
  const [labelResponse, setLabelResponse] = useState<LabelBatchInitResponse | null>(null);
  const [qrDataUrls, setQrDataUrls] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const { mutate: initializeBatch, isPending } = useInitializeLabelBatch();

  const handleInputChange = (field: keyof LabelFormData, value: LabelFormData[keyof LabelFormData]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleGenerate = () => {
    setStep('generating');

    const request = {
      packer_gln: formData.packerGln,
      product: {
        gtin: formData.gtin,
        description: formData.productDescription,
        plu: formData.plu || undefined,
        expected_units: formData.expectedUnits,
      },
      traceability: {
        lot_number: formData.lotNumber,
        pack_date: formData.packDate,
        grower_gln: formData.growerGln || undefined,
      },
      quantity: formData.quantity,
      unit_of_measure: formData.unitOfMeasure,
      packaging_level: formData.packagingLevel,
      // Top-level aliases required by API
      lot_code: formData.lotNumber,
      product_name: formData.productDescription,
    };

    initializeBatch(
      { request, tenantId },
      {
        onSuccess: (data) => {
          setLabelResponse(data);
          setStep('preview');
        },
        onError: (error) => {
          console.error('Label generation failed:', error);
          setStep('input');
          setError('Failed to generate labels. Please check your inputs and try again.');
        },
      }
    );
  };

  const handleDownloadZPL = () => {
    if (!labelResponse) return;

    const zplContent = labelResponse.labels.map((label) => label.zpl_code).join('\n\n');
    const blob = new Blob([zplContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `labels-${labelResponse.batch_id}.zpl`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleReset = () => {
    setStep('input');
    setLabelResponse(null);
    setQrDataUrls({});
  };

  useEffect(() => {
    if (!labelResponse) {
      setQrDataUrls({});
      return;
    }

    const generateQrCodes = async () => {
      const entries = await Promise.all(
        labelResponse.labels.slice(0, 5).map(async (label) => {
          // Use required qr_code_data field
          const QRCode = (await import('qrcode')).default;
          const dataUrl = await QRCode.toDataURL(label.qr_code_data, { width: 150, margin: 1 });
          return [label.serial_number, dataUrl] as const;
        })
      );

      setQrDataUrls((prev) => {
        const next = { ...prev };
        entries.forEach(([serial, dataUrl]) => {
          if (serial) next[serial] = dataUrl;
        });
        return next;
      });
    };

    generateQrCodes().catch((error) => {
      console.error('Failed to generate QR codes:', error);
    });
  }, [labelResponse]);

  // Map labels to full LabelData for PDF generation
  const getPdfLabels = () => {
    if (!labelResponse) return [];
    return labelResponse.labels.map(l => ({
      serial: l.serial_number,
      qr_payload: l.qr_code_data,
      product_name: formData.productDescription,
      lot_code: formData.lotNumber,
      pack_date: formData.packDate,
      packer_gln: formData.packerGln,
      grower_gln: formData.growerGln,
      packaging_level: formData.packagingLevel
    }));
  };

  return (
    <PageContainer>
      <PageHeader
        title="Traceability Label Generator"
        description="Generate FSMA 204 traceability labels with QR codes and ZPL for thermal printing"
      />

      {/* Input Form */}
      {step === 'input' && (
        <Card>
          <CardHeader className="flex-col items-stretch gap-1">
            <CardTitle>Label Batch Information</CardTitle>
            <CardDescription>
              Enter product and traceability information to generate labels
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {error && (
              <Callout tone="danger" role="alert">
                {error}
              </Callout>
            )}
            {/* Packer Information */}
            <div className="space-y-4">
              <h3 className="text-subheading text-re-text-primary">Packer Information</h3>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="Packer GLN" htmlFor="packer-gln" required>
                  <Input
                    id="packer-gln"
                    value={formData.packerGln}
                    onChange={(e) => handleInputChange('packerGln', e.target.value)}
                    placeholder="0614141000001"
                    required
                    aria-required="true"
                    mono
                  />
                </Field>
              </div>
            </div>

            {/* Product Information */}
            <div className="space-y-4">
              <h3 className="text-subheading text-re-text-primary">Product Information</h3>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="GTIN" htmlFor="gtin" required>
                  <Input
                    id="gtin"
                    value={formData.gtin}
                    onChange={(e) => handleInputChange('gtin', e.target.value)}
                    placeholder="00000012345678"
                    required
                    aria-required="true"
                    mono
                  />
                </Field>
                <Field label="Product Description" htmlFor="product-desc" required>
                  <Input
                    id="product-desc"
                    value={formData.productDescription}
                    onChange={(e) => handleInputChange('productDescription', e.target.value)}
                    placeholder="Organic Tomatoes"
                    required
                    aria-required="true"
                  />
                </Field>
                <Field label="PLU (Optional)" htmlFor="plu">
                  <Input
                    id="plu"
                    value={formData.plu}
                    onChange={(e) => handleInputChange('plu', e.target.value)}
                    placeholder="4011"
                    mono
                  />
                </Field>
                <Field label="Expected Units" htmlFor="expected-units" required>
                  <Input
                    id="expected-units"
                    type="number"
                    value={formData.expectedUnits}
                    onChange={(e) => handleInputChange('expectedUnits', parseInt(e.target.value))}
                    min={1}
                    required
                    aria-required="true"
                  />
                </Field>
              </div>
            </div>

            {/* Traceability Information */}
            <div className="space-y-4">
              <h3 className="text-subheading text-re-text-primary">Traceability Information</h3>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="Lot Number" htmlFor="lot-number" required>
                  <Input
                    id="lot-number"
                    value={formData.lotNumber}
                    onChange={(e) => handleInputChange('lotNumber', e.target.value)}
                    placeholder="LOT-2024-001"
                    required
                    aria-required="true"
                    mono
                  />
                </Field>
                <Field label="Pack Date" htmlFor="pack-date" required>
                  <Input
                    id="pack-date"
                    type="date"
                    value={formData.packDate}
                    onChange={(e) => handleInputChange('packDate', e.target.value)}
                    required
                    aria-required="true"
                  />
                </Field>
                <Field label="Grower GLN (Optional)" htmlFor="grower-gln">
                  <Input
                    id="grower-gln"
                    value={formData.growerGln}
                    onChange={(e) => handleInputChange('growerGln', e.target.value)}
                    placeholder="0614141000002"
                    mono
                  />
                </Field>
              </div>
            </div>

            {/* Label Configuration */}
            <div className="space-y-4">
              <h3 className="text-subheading text-re-text-primary">Label Configuration</h3>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <Field label="Quantity" htmlFor="quantity" required>
                  <Input
                    id="quantity"
                    type="number"
                    value={formData.quantity}
                    onChange={(e) => handleInputChange('quantity', parseInt(e.target.value))}
                    min={1}
                    max={10000}
                    required
                    aria-required="true"
                  />
                </Field>
                <Field label="Unit of Measure" htmlFor="uom">
                  <select
                    id="uom"
                    className={fieldControlClasses}
                    value={formData.unitOfMeasure}
                    onChange={(e) => handleInputChange('unitOfMeasure', e.target.value)}
                  >
                    <option value="EA">Each (EA)</option>
                    <option value="LBS">Pounds (LBS)</option>
                    <option value="CASE">Case</option>
                  </select>
                </Field>
                <Field label="Packaging Level" htmlFor="packaging-level">
                  <select
                    id="packaging-level"
                    className={fieldControlClasses}
                    value={formData.packagingLevel}
                    onChange={(e) => handleInputChange('packagingLevel', e.target.value)}
                  >
                    <option value="item">Item</option>
                    <option value="case">Case</option>
                    <option value="pallet">Pallet</option>
                  </select>
                </Field>
              </div>
            </div>

            <Button
              size="lg"
              onClick={handleGenerate}
              loading={isPending}
              disabled={
                !formData.packerGln ||
                !formData.gtin ||
                !formData.productDescription ||
                !formData.lotNumber ||
                !formData.packDate ||
                !formData.quantity
              }
              className="w-full"
              leadingIcon={<Package strokeWidth={1.75} aria-hidden="true" />}
            >
              Generate Labels
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Generating State */}
      {step === 'generating' && (
        <Card>
          <CardContent className="py-16" aria-busy="true">
            <div className="flex flex-col items-center justify-center space-y-4">
              <Spinner size="lg" />
              <p className="text-subheading text-re-text-primary">Generating labels...</p>
              <p className="text-ui text-re-text-tertiary">
                Creating {formData.quantity} labels with QR codes
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Preview State */}
      {step === 'preview' && labelResponse && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                  Labels Generated Successfully
                </CardTitle>
                <CardDescription className="mt-1">
                  Batch ID: {labelResponse.batch_id}
                </CardDescription>
              </div>
              <Button onClick={handleReset} variant="secondary">
                Generate New Batch
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <StatTile
                  label="TLC"
                  value={<span className="font-mono text-[0.8125rem]">{labelResponse.tlc}</span>}
                />
                <StatTile
                  label="Serial Range"
                  value={
                    <span className="font-mono text-[0.8125rem]">
                      {labelResponse.reserved_range?.start || 'N/A'} - {labelResponse.reserved_range?.end || 'N/A'}
                    </span>
                  }
                />
                <StatTile label="Labels Generated" value={labelResponse.labels.length} />
              </div>

              <div className="flex flex-col gap-4 sm:flex-row">
                <Button
                  onClick={handleDownloadZPL}
                  className="flex-1"
                  leadingIcon={<Printer strokeWidth={1.75} aria-hidden="true" />}
                >
                  Download ZPL File
                </Button>
                <LabelPdfDownloadSection
                  labels={getPdfLabels()}
                  productName={formData.productDescription}
                  batchId={labelResponse.batch_id}
                />
              </div>
            </CardContent>
          </Card>

          {/* Label Preview */}
          <Card>
            <CardHeader className="flex-col items-stretch gap-1">
              <CardTitle>Label Preview (First 5)</CardTitle>
              <CardDescription>QR codes and serial numbers for verification</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {labelResponse.labels.slice(0, 5).map((label, index) => {
                  const qrDataUrl = qrDataUrls[label.serial_number];

                  return (
                    <div key={index} className="space-y-2 rounded-lg border border-re-border p-4">
                      <p className="text-subheading text-re-text-primary">Label {index + 1}</p>
                      <p className="font-mono text-[0.8125rem] text-re-text-tertiary">
                        Serial: {label.serial}
                      </p>
                      <div className="flex items-center justify-center rounded-md bg-white p-2">
                        {qrDataUrl ? (
                          <img src={qrDataUrl} alt={`QR Code ${index + 1}`} className="h-32 w-32" />
                        ) : (
                          <>
                            <Skeleton className="h-32 w-32" />
                            <span className="sr-only">Generating QR...</span>
                          </>
                        )}
                      </div>
                      <p className="truncate font-mono text-[0.8125rem] text-re-text-tertiary">
                        {label.qr_payload}
                      </p>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </PageContainer>
  );
}
