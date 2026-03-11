'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { useInitializeLabelBatch } from '@/hooks/use-api';
import { Package, QrCode, Printer, CheckCircle, FileDown } from 'lucide-react';
import { useTenant } from '@/lib/tenant-context';
import type { LabelFormData, LabelBatchInitResponse } from '@/types/labels';
import QRCode from 'qrcode';
import { PDFDownloadLink } from '@react-pdf/renderer';
import { LabelPdfDocument } from '@/components/labels/LabelPdfDocument';

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
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          {/* Page Header */}
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
              <QrCode className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">Traceability Label Generator</h1>
              <p className="text-muted-foreground mt-1">
                Generate FSMA 204 compliant labels with QR codes and ZPL for thermal printing
              </p>
            </div>
          </div>

          {/* Input Form */}
          {step === 'input' && (
            <Card>
              <CardHeader>
                <CardTitle>Label Batch Information</CardTitle>
                <CardDescription>
                  Enter product and traceability information to generate labels
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {error && (
                  <div className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded-md">
                    {error}
                  </div>
                )}
                {/* Packer Information */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">Packer Information</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="packer-gln">Packer GLN *</label>
                      <Input
                        id="packer-gln"
                        value={formData.packerGln}
                        onChange={(e) => handleInputChange('packerGln', e.target.value)}
                        placeholder="0614141000001"
                        required
                        aria-required="true"
                      />
                    </div>
                  </div>
                </div>

                {/* Product Information */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">Product Information</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="gtin">GTIN *</label>
                      <Input
                        id="gtin"
                        value={formData.gtin}
                        onChange={(e) => handleInputChange('gtin', e.target.value)}
                        placeholder="00000012345678"
                        required
                        aria-required="true"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="product-desc">Product Description *</label>
                      <Input
                        id="product-desc"
                        value={formData.productDescription}
                        onChange={(e) => handleInputChange('productDescription', e.target.value)}
                        placeholder="Organic Tomatoes"
                        required
                        aria-required="true"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="plu">PLU (Optional)</label>
                      <Input
                        id="plu"
                        value={formData.plu}
                        onChange={(e) => handleInputChange('plu', e.target.value)}
                        placeholder="4011"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="expected-units">Expected Units *</label>
                      <Input
                        id="expected-units"
                        type="number"
                        value={formData.expectedUnits}
                        onChange={(e) => handleInputChange('expectedUnits', parseInt(e.target.value))}
                        min={1}
                        required
                        aria-required="true"
                      />
                    </div>
                  </div>
                </div>

                {/* Traceability Information */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">Traceability Information</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="lot-number">Lot Number *</label>
                      <Input
                        id="lot-number"
                        value={formData.lotNumber}
                        onChange={(e) => handleInputChange('lotNumber', e.target.value)}
                        placeholder="LOT-2024-001"
                        required
                        aria-required="true"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="pack-date">Pack Date *</label>
                      <Input
                        id="pack-date"
                        type="date"
                        value={formData.packDate}
                        onChange={(e) => handleInputChange('packDate', e.target.value)}
                        required
                        aria-required="true"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="grower-gln">Grower GLN (Optional)</label>
                      <Input
                        id="grower-gln"
                        value={formData.growerGln}
                        onChange={(e) => handleInputChange('growerGln', e.target.value)}
                        placeholder="0614141000002"
                      />
                    </div>
                  </div>
                </div>

                {/* Label Configuration */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">Label Configuration</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="quantity">Quantity *</label>
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
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="uom">Unit of Measure</label>
                      <select
                        id="uom"
                        className="w-full p-2 border rounded-md"
                        value={formData.unitOfMeasure}
                        onChange={(e) => handleInputChange('unitOfMeasure', e.target.value)}
                      >
                        <option value="EA">Each (EA)</option>
                        <option value="LBS">Pounds (LBS)</option>
                        <option value="CASE">Case</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2" htmlFor="packaging-level">Packaging Level</label>
                      <select
                        id="packaging-level"
                        className="w-full p-2 border rounded-md"
                        value={formData.packagingLevel}
                        onChange={(e) => handleInputChange('packagingLevel', e.target.value)}
                      >
                        <option value="item">Item</option>
                        <option value="case">Case</option>
                        <option value="pallet">Pallet</option>
                      </select>
                    </div>
                  </div>
                </div>

                <Button
                  onClick={handleGenerate}
                  disabled={
                    !formData.packerGln ||
                    !formData.gtin ||
                    !formData.productDescription ||
                    !formData.lotNumber ||
                    !formData.packDate ||
                    !formData.quantity
                  }
                  className="w-full"
                >
                  <Package className="mr-2 h-4 w-4" />
                  Generate Labels
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Generating State */}
          {step === 'generating' && (
            <Card>
              <CardContent className="py-16">
                <div className="flex flex-col items-center justify-center space-y-4">
                  <Spinner size="lg" />
                  <p className="text-lg font-medium">Generating labels...</p>
                  <p className="text-sm text-muted-foreground">
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
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <CheckCircle className="h-5 w-5 text-green-500" />
                        Labels Generated Successfully
                      </CardTitle>
                      <CardDescription>
                        Batch ID: {labelResponse.batch_id}
                      </CardDescription>
                    </div>
                    <Button onClick={handleReset} variant="outline">
                      Generate New Batch
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 bg-muted rounded-lg">
                      <p className="text-sm text-muted-foreground">TLC</p>
                      <p className="font-mono text-sm">{labelResponse.tlc}</p>
                    </div>
                    <div className="p-4 bg-muted rounded-lg">
                      <p className="text-sm text-muted-foreground">Serial Range</p>
                      <p className="font-mono text-sm">
                        {labelResponse.reserved_range?.start || 'N/A'} - {labelResponse.reserved_range?.end || 'N/A'}
                      </p>
                    </div>
                    <div className="p-4 bg-muted rounded-lg">
                      <p className="text-sm text-muted-foreground">Labels Generated</p>
                      <p className="font-mono text-sm">{labelResponse.labels.length}</p>
                    </div>
                  </div>

                  <div className="flex gap-4">
                    <Button onClick={handleDownloadZPL} className="flex-1">
                      <Printer className="mr-2 h-4 w-4" />
                      Download ZPL File
                    </Button>
                    <PDFDownloadLink
                      document={
                        <LabelPdfDocument
                          labels={getPdfLabels()}
                          productName={formData.productDescription}
                          batchId={labelResponse.batch_id}
                        />
                      }
                      fileName={`labels-${labelResponse.batch_id}.pdf`}
                      className="flex-1"
                    >
                      {({ loading }) => (
                        <Button className="w-full" disabled={loading}>
                          <FileDown className="mr-2 h-4 w-4" />
                          {loading ? 'Generating PDF...' : 'Download PDF (Click & Print)'}
                        </Button>
                      )}
                    </PDFDownloadLink>
                  </div>
                </CardContent>
              </Card>

              {/* Label Preview */}
              <Card>
                <CardHeader>
                  <CardTitle>Label Preview (First 5)</CardTitle>
                  <CardDescription>QR codes and serial numbers for verification</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {labelResponse.labels.slice(0, 5).map((label, index) => {
                      const qrDataUrl = qrDataUrls[label.serial_number];

                      return (
                        <div key={index} className="p-4 border rounded-lg space-y-2">
                          <p className="text-sm font-semibold">Label {index + 1}</p>
                          <p className="text-xs text-muted-foreground font-mono">
                            Serial: {label.serial}
                          </p>
                          <div className="bg-white p-2 rounded flex items-center justify-center">
                            {qrDataUrl ? (
                              <img src={qrDataUrl} alt={`QR Code ${index + 1}`} className="w-32 h-32" />
                            ) : (
                              <div className="w-32 h-32 flex items-center justify-center text-xs text-muted-foreground">
                                Generating QR...
                              </div>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground truncate">
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
        </motion.div>
      </PageContainer>
    </div>
  );
}
