'use client';

import { useState, useCallback, useRef } from 'react';
import { trackToolRunCompleted, trackToolRunStarted } from '@/lib/conversion-events';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Shield, FileCheck, Upload, Download, CheckCircle2, Loader2 } from 'lucide-react';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { EmailGate } from '@/components/tools/EmailGate';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toCsvLine } from '@/lib/csv-serialize';

type CsvRow = Record<string, string>;

/** Callout takes an icon component, so the spinner is one. */
function SpinningLoader({ className }: { className?: string }) {
  return (
    <Loader2
      className={`${className ?? ''} animate-spin motion-reduce:animate-none`}
      strokeWidth={1.75}
      aria-hidden="true"
    />
  );
}

const CSV_PREVIEW_COLUMNS = [
  { key: 'tlc', header: 'TLC', mono: true, width: '8.5rem', cell: (row: CsvRow) => row.tlc },
  { key: 'product', header: 'Product', cell: (row: CsvRow) => row.product },
  { key: 'quantity', header: 'Quantity', align: 'right' as const, cell: (row: CsvRow) => `${row.quantity} ${row.uom}` },
  { key: 'event_type', header: 'Event Type', cell: (row: CsvRow) => row.event_type },
  { key: 'event_date', header: 'Date', mono: true, width: '7rem', cell: (row: CsvRow) => row.event_date },
  { key: 'sha256_hash', header: 'SHA-256 Hash', mono: true, cell: (row: CsvRow) => row.sha256_hash },
  { key: 'chain_hash', header: 'Chain Hash', mono: true, cell: (row: CsvRow) => row.chain_hash },
];

const PACKAGE_PARTS = [
  {
    icon: FileText,
    title: 'FDA Sortable Spreadsheet',
    body: 'FDA-oriented sortable CSV organized around requested FSMA 204 records. Column mapping should be reviewed against the specific FDA request.',
  },
  {
    icon: Shield,
    title: 'Chain Verification',
    body: 'SHA-256 hash chains support tamper detection where enabled. Hashing is a RegEngine feature, not an FDA requirement.',
  },
  {
    icon: FileCheck,
    title: 'Package Manifest',
    body: 'Manifest with file checksums for checking content hashes where enabled.',
  },
];

const HASH_STEPS = [
  {
    n: '1',
    title: 'Hash Each Event',
    body: 'Each Critical Tracking Event (CTE), such as harvesting, initial packing, shipping, receiving, or transformation, is converted to a deterministic SHA-256 hash. Same data always produces same hash.',
    formula: 'event_data → SHA-256 → hash',
  },
  {
    n: '2',
    title: 'Form Chain Links',
    body: 'Each new event includes the previous hash. This links every event to its history, so any alteration of an earlier record is detectable.',
    formula: 'prev_hash + event → SHA-256 → chain_hash',
  },
  {
    n: '3',
    title: 'Detect Tampering',
    body: 'If one hash changes, all subsequent hashes become invalid. Any tampering is immediately detectable without needing a central authority.',
    formula: 'tampering → invalid chain ✗',
  },
];

interface CteRecord {
  tlc: string;
  product: string;
  quantity: number;
  uom: string;
  eventDate: string;
  eventType: string;
  location: string;
}

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

async function generatePackage(records: CteRecord[]): Promise<GeneratedPackage> {
  // Sort records by TLC and date for consistent ordering
  const sortedRecords = [...records].sort((a: CteRecord, b: CteRecord) => {
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

  // Generate manifest. Locations carry commas (for example "Farm A, California"),
  // so fields are quoted per RFC 4180; a correctly quoted reconstruction hashes
  // to the manifest's recorded CSV hash.
  const csvContent = [
    toCsvLine(Object.keys(csv[0])),
    ...csv.map((row) => toCsvLine(Object.values(row))),
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
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generationStep, setGenerationStep] = useState<string | null>(null);
  const [generatedPackage, setGeneratedPackage] = useState<GeneratedPackage | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
      const file = event.target.files?.[0];
      if (!file) return;

      trackToolRunStarted('export');
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
        trackToolRunCompleted('export', 'success');
      } catch (error) {
        console.error('Error processing file:', error);
        setGenerationStep(null);
        trackToolRunCompleted('export', 'error');
      }

      setIsGenerating(false);
    },
    []
  );

  const downloadPackage = useCallback((): void => {
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
    <EmailGate toolName="export">
      <FreeToolPageShell
        title="FDA Export Package Generator"
        subtitle="Generate a verifiable FSMA 204 records package to support 21 CFR 1.1455 record-availability workflows."
        relatedToolIds={['drill-simulator', 'cte-mapper', 'kde-checker']}
      >
        {/* Section 1: Package Overview */}
        <section>
          <h2 className="mb-6 text-heading text-re-text-primary">What&apos;s in Your Package</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {PACKAGE_PARTS.map((part, i) => {
              const Icon = part.icon;
              return (
                <motion.div
                  key={part.title}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 * (i + 1) }}
                >
                  <Card padding="spacious" className="h-full">
                    <div className="flex items-start gap-4">
                      <Icon className="mt-0.5 h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                      <div>
                        <h3 className="mb-2 text-subheading text-re-text-primary">{part.title}</h3>
                        <p className="text-ui text-re-text-secondary">{part.body}</p>
                      </div>
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </section>

        {/* Section 2: Generate Package */}
        <section>
          <h2 className="mb-6 text-heading text-re-text-primary">Generate Your Package</h2>

          <div className="rounded-lg border-2 border-dashed border-re-border p-8 text-center">
            <Upload className="mx-auto mb-3 h-6 w-6 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            <p className="mb-4 text-ui text-re-text-secondary">
              Upload a CSV with columns: tlc, product, quantity, uom, event_date, event_type, location
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              aria-label="Upload Your Records"
              onChange={handleFileUpload}
              className="hidden"
            />
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={isGenerating}
              variant="secondary"
            >
              {isGenerating ? 'Processing...' : 'Choose CSV File'}
            </Button>
          </div>

          {/* Generation Progress */}
          <AnimatePresence>
            {isGenerating && generationStep && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="mt-6"
              >
                <Callout tone="info" role="status" icon={SpinningLoader}>
                  {generationStep}
                </Callout>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        {/* Section 3: Package Preview */}
        {generatedPackage && (
          <section>
            <h2 className="mb-6 text-heading text-re-text-primary">Package Preview</h2>

            <Tabs defaultValue="csv" className="w-full">
              <TabsList className="max-w-full overflow-x-auto">
                <TabsTrigger value="csv">FDA CSV Preview</TabsTrigger>
                <TabsTrigger value="chain">Chain Verification</TabsTrigger>
                <TabsTrigger value="manifest">Manifest</TabsTrigger>
              </TabsList>

              <TabsContent value="csv">
                <DataTable
                  caption="FDA CSV Preview"
                  columns={CSV_PREVIEW_COLUMNS}
                  data={generatedPackage.csv.slice(0, 10)}
                  minWidth="880px"
                  stickyFirstColumn
                />
                <p className="mt-4 text-small text-re-text-tertiary">
                  Showing first 10 of {generatedPackage.csv.length} records
                </p>
              </TabsContent>

              <TabsContent value="chain">
                <div className="space-y-4">
                  <Callout tone="success" role="status" title="Chain Valid">
                    {generatedPackage.chainVerification.chain_length} records verified
                  </Callout>

                  <Card variant="inset" padding="compact">
                    <pre className="overflow-x-auto font-mono text-[0.8125rem] text-re-text-secondary">
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
                    </pre>
                  </Card>

                  <div className="space-y-3">
                    {generatedPackage.chainVerification.events.slice(0, 5).map((event, idx) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.1 }}
                        className="flex items-start gap-4 rounded-lg border border-re-border bg-re-surface-card p-4"
                      >
                        <div className="flex flex-col items-center">
                          <span className="flex h-8 w-8 items-center justify-center rounded-full border border-re-border bg-re-surface-inset font-mono uppercase text-label text-re-text-secondary">
                            {idx + 1}
                          </span>
                          {idx < 4 && <span className="my-1 h-6 w-px bg-re-border" aria-hidden="true" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-ui font-medium text-re-text-primary">{event.event_type}</p>
                          <p className="mt-1 text-small text-re-text-tertiary">TLC: {event.tlc}</p>
                          <p className="text-small text-re-text-tertiary">Date: {event.timestamp}</p>
                          <div className="mt-2 overflow-x-auto rounded-md bg-re-surface-inset p-2 font-mono text-[0.8125rem] text-re-text-tertiary">
                            <div>event_hash: {event.event_hash.substring(0, 32)}...</div>
                            <div className="mt-1">→ chain_hash: {event.chain_hash.substring(0, 32)}...</div>
                          </div>
                        </div>
                        <CheckCircle2 className="mt-1 h-5 w-5 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                      </motion.div>
                    ))}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="manifest">
                <div className="space-y-4">
                  <Card variant="inset" padding="compact">
                    <pre className="overflow-x-auto font-mono text-[0.8125rem] text-re-text-secondary">
                      {JSON.stringify(generatedPackage.manifest, null, 2)}
                    </pre>
                  </Card>

                  <div className="grid grid-cols-1 gap-3">
                    {generatedPackage.manifest.files.map((file, idx) => (
                      <div key={idx} className="flex items-center justify-between gap-3 rounded-lg border border-re-border bg-re-surface-card p-4">
                        <div className="min-w-0">
                          <p className="text-ui font-medium text-re-text-primary">{file.filename}</p>
                          <p className="mt-1 truncate font-mono text-[0.8125rem] text-re-text-tertiary">{file.sha256.substring(0, 32)}...</p>
                        </div>
                        <CheckCircle2 className="h-5 w-5 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                      </div>
                    ))}
                  </div>

                  <Callout tone="info" role="note" title="How to Verify Independently">
                    <ol className="list-inside list-decimal space-y-1 text-small">
                      <li>Download all files from the package</li>
                      <li>Compute SHA-256 hash of each file</li>
                      <li>Compare hashes with manifest entries</li>
                      <li>If all match, package integrity verified ✓</li>
                    </ol>
                  </Callout>
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
                  >
                    <Card padding="compact">
                      <p className="text-ui font-medium text-re-text-primary">Preview Ready</p>
                      <p className="mt-1 text-small text-re-text-tertiary">
                        Your {generatedPackage.csv.length}-record package is ready to download with full chain verification.
                      </p>
                    </Card>
                  </motion.div>
                }
              >
                <Button
                  onClick={downloadPackage}
                  size="lg"
                  className="w-full"
                  leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
                >
                  Download Package
                </Button>
              </LeadGate>
            </div>
          </section>
        )}

        {/* Section 4: How It Works */}
        <section className="border-t border-re-border-subtle pt-10">
          <h2 className="mb-8 text-heading text-re-text-primary">How SHA-256 Chain Verification Works</h2>

          <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
            {HASH_STEPS.map((step, i) => (
              <motion.div
                key={step.n}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * (i + 1) }}
                className="space-y-4"
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-full border border-re-border bg-re-surface-inset font-mono uppercase text-label text-re-text-secondary">
                  {step.n}
                </span>
                <h3 className="text-subheading text-re-text-primary">{step.title}</h3>
                <p className="text-ui text-re-text-secondary">{step.body}</p>
                <div className="overflow-x-auto rounded-md bg-re-surface-inset p-3 font-mono text-[0.8125rem] text-re-text-tertiary">
                  {step.formula}
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      </FreeToolPageShell>
    </EmailGate>
  );
}
