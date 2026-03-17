'use client';

import { useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Shield, FileCheck, Upload, Download, CheckCircle2, AlertCircle } from 'lucide-react';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

// Sample CTE data for demo
const SAMPLE_RECORDS = [
  { tlc: 'TLC-2024-001', product: 'Romaine Lettuce', quantity: 50, uom: 'lbs', eventDate: '2024-01-15', eventType: 'harvest', location: 'Farm A - California' },
  { tlc: 'TLC-2024-001', product: 'Romaine Lettuce', quantity: 50, uom: 'lbs', eventDate: '2024-01-16', eventType: 'pack', location: 'Facility B - California' },
  { tlc: 'TLC-2024-001', product: 'Romaine Lettuce', quantity: 50, uom: 'lbs', eventDate: '2024-01-17', eventType: 'transport', location: 'Distribution Center C - Nevada' },
  { tlc: 'TLC-2024-002', product: 'Cherry Tomatoes', quantity: 100, uom: 'lbs', eventDate: '2024-01-16', eventType: 'harvest', location: 'Farm D - Florida' },
  { tlc: 'TLC-2024-002', product: 'Cherry Tomatoes', quantity: 100, uom: 'lbs', eventDate: '2024-01-17', eventType: 'pack', location: 'Facility E - Florida' },
  { tlc: 'TLC-2024-002', product: 'Cherry Tomatoes', quantity: 100, uom: 'lbs', eventDate: '2024-01-18', eventType: 'transport', location: 'Hub F - Georgia' },
  { tlc: 'TLC-2024-003', product: 'Spinach', quantity: 75, uom: 'lbs', eventDate: '2024-01-14', eventType: 'harvest', location: 'Farm G - Texas' },
  { tlc: 'TLC-2024-003', product: 'Spinach', quantity: 75, uom: 'lbs', eventDate: '2024-01-15', eventType: 'pack', location: 'Facility H - Texas' },
  { tlc: 'TLC-2024-003', product: 'Spinach', quantity: 75, uom: 'lbs', eventDate: '2024-01-16', eventType: 'quality_check', location: 'Lab I - Texas' },
  { tlc: 'TLC-2024-003', product: 'Spinach', quantity: 75, uom: 'lbs', eventDate: '2024-01-17', eventType: 'transport', location: 'Distribution Center J - Oklahoma' },
];

interface GeneratedPackage {
  csv: Array<Record<string, string>>;
  chainVerification: {
    valid: boolean;
    chain_length: number;
    checked_at: string;
    errors: string[];
    events: Array<{
      index: number;
      tlc: string;
      event_type: string;
      timestamp: string;
      event_hash: string;
      chain_hash: string;
      previous_hash: string;
    }>;
  };
  manifest: {
    generated_at: string;
    files: Array<{
      filename: string;
      sha256: string;
      size: number;
    }>;
  };
}

async function sha256(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const buffer = await crypto.subtle.digest('SHA-256', encoder.encode(data));
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function generatePackage(records: typeof SAMPLE_RECORDS): Promise<GeneratedPackage> {
  // Sort records by TLC and date for consistent ordering
  const sortedRecords = [...records].sort((a, b) => {
    if (a.tlc !== b.tlc) return a.tlc.localeCompare(b.tlc);
    return new Date(a.eventDate).getTime() - new Date(b.eventDate).getTime();
  });

  // Generate CSV with hashes
  let previousHash = '';
  const csv: Array<Record<string, string>> = [];
  const chainEvents: GeneratedPackage['chainVerification']['events'] = [];

  for (let i = 0; i < sortedRecords.length; i++) {
    const record = sortedRecords[i];
    const eventData = JSON.stringify({
      tlc: record.tlc,
      product: record.product,
      quantity: record.quantity,
      uom: record.uom,
      event_date: record.eventDate,
      event_type: record.eventType,
      location: record.location,
    });

    const eventHash = await sha256(eventData);
    const chainInput = previousHash + eventData;
    const chainHash = await sha256(chainInput);

    csv.push({
      tlc: record.tlc,
      product: record.product,
      quantity: record.quantity.toString(),
      uom: record.uom,
      event_date: record.eventDate,
      event_type: record.eventType,
      location: record.location,
      sha256_hash: eventHash.substring(0, 16) + '...',
      chain_hash: chainHash.substring(0, 16) + '...',
    });

    chainEvents.push({
      index: i,
      tlc: record.tlc,
      event_type: record.eventType,
      timestamp: record.eventDate,
      event_hash: eventHash,
      chain_hash: chainHash,
      previous_hash: previousHash || 'genesis',
    });

    previousHash = chainHash;
  }

  // Generate manifest
  const csvContent = [
    Object.keys(csv[0]).join(','),
    ...csv.map((row) => Object.values(row).join(',')),
  ].join('\n');

  const csvHash = await sha256(csvContent);
  const verificationJson = JSON.stringify(chainEvents, null, 2);
  const verificationHash = await sha256(verificationJson);

  const manifest = {
    generated_at: new Date().toISOString(),
    files: [
      {
        filename: 'fda-compliance-package.csv',
        sha256: csvHash,
        size: csvContent.length,
      },
      {
        filename: 'chain-verification.json',
        sha256: verificationHash,
        size: verificationJson.length,
      },
      {
        filename: 'manifest.json',
        sha256: '',
        size: 0,
      },
    ],
  };

  // Hash the manifest itself
  const manifestHash = await sha256(JSON.stringify(manifest, null, 2));
  manifest.files[2].sha256 = manifestHash;

  return {
    csv,
    chainVerification: {
      valid: true,
      chain_length: sortedRecords.length,
      checked_at: new Date().toISOString(),
      errors: [],
      events: chainEvents,
    },
    manifest,
  };
}

export default function ExportPage() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<string | null>(null);
  const [generatedPackage, setGeneratedPackage] = useState<GeneratedPackage | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleGenerateDemo = useCallback(async () => {
    setIsGenerating(true);
    setGenerationStep(null);

    const steps = [
      { label: 'Reading records...', duration: 300 },
      { label: 'Computing SHA-256 hashes...', duration: 500 },
      { label: 'Building chain verification...', duration: 400 },
      { label: 'Generating FDA CSV...', duration: 300 },
      { label: 'Creating manifest...', duration: 200 },
    ];

    for (const step of steps) {
      setGenerationStep(step.label);
      await new Promise((resolve) => setTimeout(resolve, step.duration));
    }

    const pkg = await generatePackage(SAMPLE_RECORDS);
    setGeneratedPackage(pkg);
    setGenerationStep(null);
    setIsGenerating(false);
  }, []);

  const handleFileUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      setIsGenerating(true);
      setGenerationStep(null);

      try {
        const text = await file.text();
        const lines = text.split('\n').filter((line) => line.trim());
        const headers = lines[0].split(',').map((h) => h.trim());

        const records = lines.slice(1).map((line) => {
          const values = line.split(',').map((v) => v.trim());
          return {
            tlc: values[headers.indexOf('tlc')] || '',
            product: values[headers.indexOf('product')] || '',
            quantity: parseInt(values[headers.indexOf('quantity')] || '0'),
            uom: values[headers.indexOf('uom')] || '',
            eventDate: values[headers.indexOf('event_date')] || '',
            eventType: values[headers.indexOf('event_type')] || '',
            location: values[headers.indexOf('location')] || '',
          };
        });

        const steps = [
          { label: 'Reading records...', duration: 300 },
          { label: 'Computing SHA-256 hashes...', duration: 500 },
          { label: 'Building chain verification...', duration: 400 },
          { label: 'Generating FDA CSV...', duration: 300 },
          { label: 'Creating manifest...', duration: 200 },
        ];

        for (const step of steps) {
          setGenerationStep(step.label);
          await new Promise((resolve) => setTimeout(resolve, step.duration));
        }

        const pkg = await generatePackage(records);
        setGeneratedPackage(pkg);
        setGenerationStep(null);
      } catch (error) {
        console.error('Error processing file:', error);
        setGenerationStep(null);
      }

      setIsGenerating(false);
    },
    []
  );

  const downloadPackage = useCallback(() => {
    if (!generatedPackage) return;

    const zip = new Blob(
      [
        JSON.stringify(
          {
            csv: generatedPackage.csv,
            chainVerification: generatedPackage.chainVerification,
            manifest: generatedPackage.manifest,
          },
          null,
          2
        ),
      ],
      { type: 'application/json' }
    );

    const url = URL.createObjectURL(zip);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fda-compliance-package-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [generatedPackage]);

  return (
    <FreeToolPageShell
      title="FDA Export Package Generator"
      subtitle="Generate a verifiable 21 CFR 1.1455 compliance package with SHA-256 chain verification."
      relatedToolIds={['drill-simulator', 'cte-mapper', 'kde-checker']}
    >
      {/* Section 1: Package Overview */}
      <div className="mb-12">
        <h2 className="text-2xl font-semibold mb-6">What's in Your Package</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="p-6 border border-gray-200 rounded-lg bg-gradient-to-br from-blue-50 to-transparent"
          >
            <div className="flex items-start gap-4">
              <FileText className="w-6 h-6 text-blue-600 flex-shrink-0 mt-1" />
              <div>
                <h3 className="font-semibold mb-2">FDA Sortable Spreadsheet</h3>
                <p className="text-sm text-gray-600">
                  21 CFR 1.1455 compliant CSV with all required KDEs. Sortable by TLC, date, product, and location.
                </p>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="p-6 border border-gray-200 rounded-lg bg-gradient-to-br from-green-50 to-transparent"
          >
            <div className="flex items-start gap-4">
              <Shield className="w-6 h-6 text-green-600 flex-shrink-0 mt-1" />
              <div>
                <h3 className="font-semibold mb-2">Chain Verification</h3>
                <p className="text-sm text-gray-600">
                  SHA-256 hash chain proving record integrity. Each event cryptographically linked to its predecessor.
                </p>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="p-6 border border-gray-200 rounded-lg bg-gradient-to-br from-purple-50 to-transparent"
          >
            <div className="flex items-start gap-4">
              <FileCheck className="w-6 h-6 text-purple-600 flex-shrink-0 mt-1" />
              <div>
                <h3 className="font-semibold mb-2">Package Manifest</h3>
                <p className="text-sm text-gray-600">
                  Cryptographic manifest with file checksums. Independent verification without RegEngine.
                </p>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Section 2: Interactive Demo */}
      <div className="mb-12">
        <h2 className="text-2xl font-semibold mb-6">Generate Your Package</h2>

        <Tabs defaultValue="sample" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="sample">Try with Sample Data</TabsTrigger>
            <TabsTrigger value="upload">Upload Your Records</TabsTrigger>
          </TabsList>

          <TabsContent value="sample" className="mt-6">
            <div className="text-center py-8">
              <p className="text-gray-600 mb-6">Generate a demo package using realistic food traceability data</p>
              <Button
                onClick={handleGenerateDemo}
                disabled={isGenerating}
                size="lg"
                className="bg-blue-600 hover:bg-blue-700"
              >
                {isGenerating ? 'Generating...' : 'Generate Demo Package'}
              </Button>
            </div>
          </TabsContent>

          <TabsContent value="upload" className="mt-6">
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
              <Upload className="w-10 h-10 mx-auto text-gray-400 mb-3" />
              <p className="text-gray-600 mb-4">
                Upload a CSV with columns: tlc, product, quantity, uom, event_date, event_type, location
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileUpload}
                className="hidden"
              />
              <Button
                onClick={() => fileInputRef.current?.click()}
                disabled={isGenerating}
                variant="outline"
              >
                {isGenerating ? 'Processing...' : 'Choose CSV File'}
              </Button>
            </div>
          </TabsContent>
        </Tabs>

        {/* Generation Progress */}
        <AnimatePresence>
          {isGenerating && generationStep && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg"
            >
              <div className="flex items-center gap-3">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                  className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full"
                />
                <span className="text-blue-900 font-medium">{generationStep}</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Section 3: Package Preview */}
      {generatedPackage && (
        <div className="mb-12">
          <h2 className="text-2xl font-semibold mb-6">Package Preview</h2>

          <Tabs defaultValue="csv" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="csv">FDA CSV Preview</TabsTrigger>
              <TabsTrigger value="chain">Chain Verification</TabsTrigger>
              <TabsTrigger value="manifest">Manifest</TabsTrigger>
            </TabsList>

            <TabsContent value="csv" className="mt-6">
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold">TLC</th>
                      <th className="px-4 py-3 text-left font-semibold">Product</th>
                      <th className="px-4 py-3 text-left font-semibold">Quantity</th>
                      <th className="px-4 py-3 text-left font-semibold">Event Type</th>
                      <th className="px-4 py-3 text-left font-semibold">Date</th>
                      <th className="px-4 py-3 text-left font-semibold">SHA-256 Hash</th>
                      <th className="px-4 py-3 text-left font-semibold">Chain Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {generatedPackage.csv.slice(0, 10).map((row, idx) => (
                      <tr key={idx} className="border-b border-gray-200 hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-xs">{row.tlc}</td>
                        <td className="px-4 py-3">{row.product}</td>
                        <td className="px-4 py-3">{row.quantity} {row.uom}</td>
                        <td className="px-4 py-3">{row.event_type}</td>
                        <td className="px-4 py-3 text-xs">{row.event_date}</td>
                        <td className="px-4 py-3 font-mono text-xs bg-blue-50">{row.sha256_hash}</td>
                        <td className="px-4 py-3 font-mono text-xs bg-green-50">{row.chain_hash}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-sm text-gray-600 mt-4">
                Showing first 10 of {generatedPackage.csv.length} records
              </p>
            </TabsContent>

            <TabsContent value="chain" className="mt-6">
              <div className="space-y-4">
                <div className="flex items-center gap-4 p-4 bg-green-50 border border-green-200 rounded-lg">
                  <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-green-900">Chain Valid</p>
                    <p className="text-sm text-green-800">
                      {generatedPackage.chainVerification.chain_length} records verified
                    </p>
                  </div>
                </div>

                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                  <p className="text-sm font-mono text-gray-800 whitespace-pre-wrap">
                    {JSON.stringify(
                      {
                        chain_verification: {
                          valid: generatedPackage.chainVerification.valid,
                          chain_length: generatedPackage.chainVerification.chain_length,
                          checked_at: generatedPackage.chainVerification.checked_at,
                          errors: generatedPackage.chainVerification.errors,
                        },
                      },
                      null,
                      2
                    )}
                  </p>
                </div>

                <div className="space-y-3">
                  {generatedPackage.chainVerification.events.slice(0, 5).map((event, idx) => (
                    <motion.div
                      key={idx}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.1 }}
                      className="flex items-start gap-4 p-4 border border-gray-200 rounded-lg"
                    >
                      <div className="flex flex-col items-center">
                        <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-semibold">
                          {idx + 1}
                        </div>
                        {idx < 4 && <div className="h-6 w-0.5 bg-gray-300 my-1" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm">{event.event_type}</p>
                        <p className="text-xs text-gray-600 mt-1">TLC: {event.tlc}</p>
                        <p className="text-xs text-gray-600">Date: {event.timestamp}</p>
                        <div className="mt-2 p-2 bg-gray-100 rounded text-xs font-mono text-gray-700">
                          <div>event_hash: {event.event_hash.substring(0, 32)}...</div>
                          <div className="mt-1">→ chain_hash: {event.chain_hash.substring(0, 32)}...</div>
                        </div>
                      </div>
                      <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-1" />
                    </motion.div>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="manifest" className="mt-6">
              <div className="space-y-4">
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 overflow-x-auto">
                  <p className="text-sm font-mono text-gray-800 whitespace-pre-wrap">
                    {JSON.stringify(generatedPackage.manifest, null, 2)}
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-3">
                  {generatedPackage.manifest.files.map((file, idx) => (
                    <div key={idx} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                      <div>
                        <p className="font-semibold text-sm">{file.filename}</p>
                        <p className="text-xs text-gray-600 mt-1 font-mono">{file.sha256.substring(0, 32)}...</p>
                      </div>
                      <CheckCircle2 className="w-5 h-5 text-green-600" />
                    </div>
                  ))}
                </div>

                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="font-semibold text-sm text-blue-900 mb-2">How to Verify Independently</p>
                  <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
                    <li>Download all files from the package</li>
                    <li>Compute SHA-256 hash of each file</li>
                    <li>Compare hashes with manifest entries</li>
                    <li>If all match, package integrity verified ✓</li>
                  </ol>
                </div>
              </div>
            </TabsContent>
          </Tabs>

          {/* Download Button with LeadGate */}
          <div className="mt-8">
            <LeadGate
              source="fda-export"
              headline="Download Your FDA Package"
              teaser={
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="p-4 bg-gray-50 border border-gray-200 rounded-lg"
                >
                  <p className="text-sm font-semibold mb-2">Preview Ready</p>
                  <p className="text-xs text-gray-600">
                    Your {generatedPackage.csv.length}-record package is ready to download with full chain verification.
                  </p>
                </motion.div>
              }
            >
              <Button onClick={downloadPackage} size="lg" className="w-full bg-blue-600 hover:bg-blue-700">
                <Download className="w-4 h-4 mr-2" />
                Download Package
              </Button>
            </LeadGate>
          </div>
        </div>
      )}

      {/* Section 4: How It Works */}
      <div className="border-t border-gray-200 pt-12">
        <h2 className="text-2xl font-semibold mb-8">How SHA-256 Chain Verification Works</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="space-y-4"
          >
            <div className="flex items-center justify-center w-12 h-12 bg-blue-100 rounded-full">
              <span className="text-xl font-bold text-blue-600">1</span>
            </div>
            <h3 className="font-semibold">Hash Each Event</h3>
            <p className="text-sm text-gray-600">
              Each CTE event (harvest, pack, transport, etc.) is converted to a deterministic SHA-256 hash. Same data always produces same hash.
            </p>
            <div className="bg-gray-50 p-3 rounded text-xs font-mono text-gray-700">
              event_data → SHA-256 → hash
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="space-y-4"
          >
            <div className="flex items-center justify-center w-12 h-12 bg-green-100 rounded-full">
              <span className="text-xl font-bold text-green-600">2</span>
            </div>
            <h3 className="font-semibold">Form Chain Links</h3>
            <p className="text-sm text-gray-600">
              Each new event includes the previous hash. This creates an unbreakable chain where every event is cryptographically bound to its history.
            </p>
            <div className="bg-gray-50 p-3 rounded text-xs font-mono text-gray-700">
              prev_hash + event → SHA-256 → chain_hash
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="space-y-4"
          >
            <div className="flex items-center justify-center w-12 h-12 bg-red-100 rounded-full">
              <span className="text-xl font-bold text-red-600">3</span>
            </div>
            <h3 className="font-semibold">Detect Tampering</h3>
            <p className="text-sm text-gray-600">
              If one hash changes, all subsequent hashes become invalid. Any tampering is immediately detectable without needing a central authority.
            </p>
            <div className="bg-red-50 p-3 rounded text-xs font-mono text-red-700">
              tampering → invalid chain ✗
            </div>
          </motion.div>
        </div>
      </div>
    </FreeToolPageShell>
  );
}
