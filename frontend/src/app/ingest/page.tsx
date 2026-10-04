'use client';

import { useState, useEffect, useRef } from 'react';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Callout } from '@/components/ui/callout';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { StatTile } from '@/components/ui/stat-tile';
import { HelpTooltip } from '@/components/ui/tooltip';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WorkflowStepper } from '@/components/layout/workflow-stepper';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import type { IngestCSVResponse } from '@/types/api';
import { useIngestURL, useIngestFile } from '@/hooks/use-api';
import { notifyDashboardRefresh } from '@/hooks/use-dashboard-refresh';
import {
  CheckCircle,
  Link2,
  Upload,
  ArrowRight,
  Key,
  ClipboardCheck,
  FlaskConical,
  Globe,
  Landmark,
  Scale
} from 'lucide-react';
import { ColumnSuggestionList } from '@/components/fsma/ColumnSuggestionList';
import { CteSuggestionPrompt } from '@/components/fsma/CteSuggestionPrompt';
import {
  columnSuggestions,
  columnSuggestionsFromUploadError,
  type ColumnSuggestion,
} from '@/lib/column-suggestions';
import { cteSuggestionFromUploadError, type ActionableCteSuggestion } from '@/lib/cte-suggestion';
import { NormalizedDocumentViewer } from './NormalizedDocumentViewer';
import { readSandboxHandoffFromSession } from './sandbox-handoff';

const EXAMPLE_URLS = [
  {
    label: 'FDA Regulations (21 CFR)',
    url: 'https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-21.xml?chapter=I&subchapter=A&part=1',
  },
];

const STATUS_STEPS = [
  { id: 'queued', label: 'Queued' },
  { id: 'parsing', label: 'Parsing' },
  { id: 'extracting', label: 'Extracting' },
  { id: 'completed', label: 'Complete' },
];

const STATUS_PROGRESS: Record<string, number> = {
  queued: 10,
  parsing: 40,
  extracting: 70,
  completed: 100,
};

const SOURCE_BADGES = [
  { label: 'eCFR', icon: Scale },
  { label: 'Federal Register', icon: Landmark },
  { label: 'FDA.gov', icon: Globe },
];

const CAPABILITIES = [
  {
    title: 'OCR Processing',
    body: 'Automatic optical character recognition for scanned documents',
  },
  {
    title: 'NLP Extraction',
    body: 'Extract regulatory entities, obligations, and thresholds using ML',
  },
  {
    title: 'Graph Storage',
    body: 'Store in a graph database with bitemporal modeling for compliance tracking',
  },
];

const SUPPORTED_FORMATS = ['PDF', 'HTML', 'JSON', 'XML', 'CSV', 'Excel (.xlsx)', 'Word (.docx)', 'Plain Text'];

/**
 * Zero-padded, matching the WorkflowStepper. A bare numeral here would collide
 * with the "Events detected: 3" figure in the sandbox-handoff panel, which
 * src/__tests__/pages/ingest-handoff.test.tsx queries by exact text.
 */
function stepNumeral(index: number) {
  return String(index + 1).padStart(2, '0');
}

export default function IngestPage() {
  const searchParams = useSearchParams();
  const fromSandboxHandoff = searchParams.get('from') === 'sandbox-handoff';
  const [sandboxHandoffResult] = useState(() =>
    fromSandboxHandoff ? readSandboxHandoffFromSession() : null
  );
  const { apiKey: storedApiKey, setApiKey: storeApiKey } = useAuth();
  const [url, setUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string>('queued');
  const [statusError, setStatusError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('url');
  const [file, setFile] = useState<File | null>(null);
  const [csvResult, setCsvResult] = useState<IngestCSVResponse | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [cteSuggestion, setCteSuggestion] = useState<ActionableCteSuggestion | null>(null);
  const [errorColumnSuggestions, setErrorColumnSuggestions] = useState<ColumnSuggestion[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submitInFlightRef = useRef(false);

  const ingestMutation = useIngestURL();
  const ingestFileMutation = useIngestFile();
  const isPending = isSubmitting || ingestMutation.isPending || ingestFileMutation.isPending;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setCsvResult(null);
      setCsvError(null);
      setCteSuggestion(null);
      setErrorColumnSuggestions([]);
    }
  };

  // One-way prefill: the stored key resolves after mount, and the field stays
  // user-editable afterwards, so this cannot be a lazy initial value.
  useEffect(() => {
    if (storedApiKey && !apiKey) {
      setApiKey(storedApiKey);
    }
  }, [storedApiKey, apiKey]);

  useEffect(() => {
    if (!jobId || jobId === 'demo-job-123') return;

    const intervalId = window.setInterval(async () => {
      try {
        const statusResponse = await apiClient.getIngestionJob(jobId);
        const normalizedStatus = (statusResponse.status || statusResponse.step || '').toLowerCase();
        if (normalizedStatus) {
          setJobStatus(STATUS_STEPS.some(step => step.id === normalizedStatus) ? normalizedStatus : 'queued');
          if (['completed', 'failed'].includes(normalizedStatus)) {
            window.clearInterval(intervalId);
          }
        }
      } catch (error) {
        console.error('Failed to fetch ingestion status:', error);
        setStatusError('Unable to fetch ingestion status.');
      }
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [jobId]);

  // ``cteType`` is set only by the "Import as <CTE>" prompt: the uploader
  // confirming the CTE Jev suggested for a file the server rejected.
  const handleSubmit = async (e?: React.FormEvent, cteType?: string) => {
    e?.preventDefault();
    if (!apiKey) return;
    if (activeTab === 'url' && !url) return;
    if (activeTab === 'file' && !file) return;
    if (submitInFlightRef.current) return;

    submitInFlightRef.current = true;
    setIsSubmitting(true);
    try {
      // Store the API key for future use
      if (apiKey !== storedApiKey) {
        // The browser proxy reads the cookie written by setApiKey and ignores
        // caller-supplied credential headers. Wait for that write before the
        // upload so a stale key or tenant cannot win the request race.
        try {
          await storeApiKey(apiKey);
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Unable to save API key';
          if (activeTab === 'file') setCsvError(message);
          else setStatusError(message);
          return;
        }
      }
      setJobId(null);
      setJobStatus('queued');
      setStatusError(null);
      setCsvResult(null);
      setCsvError(null);
      setCteSuggestion(null);
      setErrorColumnSuggestions([]);

      // Demonstration Override for the Sales Demo flow
      if (activeTab === 'url' && url === EXAMPLE_URLS[0].url) {
        setJobId('demo-job-123');

        // Simulate real ingestion stages over 3.5 seconds
        setTimeout(() => setJobStatus('parsing'), 800);
        setTimeout(() => setJobStatus('extracting'), 1800);
        setTimeout(() => setJobStatus('completed'), 3500);
        return;
      }

      try {
        if (activeTab === 'file') {
          if (!file) return;
          const result = await ingestFileMutation.mutateAsync({ apiKey, file, cteType });
          setCsvResult(result);
          if (result.accepted > 0) notifyDashboardRefresh();
          return;
        }

        const result = await ingestMutation.mutateAsync({ apiKey, url });
        const returnedJobId = result.job_id || result.doc_id || null;
        if (returnedJobId) {
          setJobId(returnedJobId);
          setJobStatus('queued');
          setStatusError(null);
          notifyDashboardRefresh();
        }
      } catch (error) {
        if (activeTab === 'file') {
          setCsvError(error instanceof Error ? error.message : 'CSV upload failed');
          // Only offered when the server rejected an undeclared file: a
          // declared CTE is never second-guessed.
          setCteSuggestion(cteType ? null : cteSuggestionFromUploadError(error));
          setErrorColumnSuggestions(columnSuggestionsFromUploadError(error));
        } else {
          console.error('Ingestion failed:', error);
        }
      }
    } finally {
      submitInFlightRef.current = false;
      setIsSubmitting(false);
    }
  };

  const activeStepIndex = Math.max(
    STATUS_STEPS.findIndex((step) => step.id === jobStatus),
    0
  );
  const progressValue = STATUS_PROGRESS[jobStatus] ?? 0;

  const csvTitle = csvResult
    ? csvResult.accepted === 0
      ? 'No rows accepted'
      : csvResult.rejected > 0
        ? 'CSV partially accepted'
        : 'CSV processed'
    : '';
  const csvTone = csvResult
    ? csvResult.accepted === 0
      ? 'danger'
      : csvResult.rejected > 0
        ? 'warning'
        : 'success'
    : 'neutral';

  const demoBanner = (
    <Callout tone="warning">
      Simulated walkthrough — sample output
    </Callout>
  );

  return (
    <PageContainer>
      <div className="mb-6">
        <WorkflowStepper currentStep="ingest" completedSteps={storedApiKey ? ['setup'] : []} />
      </div>

      <PageHeader
        title="Document Ingestion"
        description="Submit regulatory document URLs for processing"
        secondaryActions={
          experimentalFeaturesEnabled() ? (
            <Button variant="secondary" asChild>
              <Link href="/ingest/curation">
                <ClipboardCheck className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Open Curation Queue
              </Link>
            </Button>
          ) : undefined
        }
      />

      <div className="space-y-6">
        {fromSandboxHandoff && (
          <Card>
            <CardHeader className="flex-col items-stretch sm:flex-row sm:items-start">
              <div className="min-w-0">
                <CardTitle>Sandbox import mapping handoff</CardTitle>
                <CardDescription className="mt-1.5">
                  This is a saved test-run diagnosis. Map and correct it here before any authenticated feed or evidence workflow uses the data.
                </CardDescription>
              </div>
              <Badge className="w-fit shrink-0">Test run only</Badge>
            </CardHeader>
            <CardContent>
              {sandboxHandoffResult?.ok ? (
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <StatTile label="Events detected" value={sandboxHandoffResult.view.totalEvents} />
                    <StatTile label="Passed checks" value={sandboxHandoffResult.view.passedChecks} />
                    <StatTile label="Needs work" value={sandboxHandoffResult.view.needsWork} />
                    <StatTile label="Blockers" value={sandboxHandoffResult.view.blockerCount} />
                  </div>

                  <div>
                    <div className="text-ui font-medium text-re-text-primary">Detected columns</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {sandboxHandoffResult.view.detectedColumns.length > 0 ? (
                        sandboxHandoffResult.view.detectedColumns.map((column) => (
                          <Badge key={column} size="sm" mono>
                            {column}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-ui text-re-text-tertiary">
                          No headers were carried in the handoff. Confirm the source file before mapping.
                        </span>
                      )}
                    </div>
                  </div>

                  <Callout
                    tone={sandboxHandoffResult.view.blockerCount > 0 ? 'warning' : 'success'}
                    title="Next mapping action"
                  >
                    <p>{sandboxHandoffResult.view.nextMappingAction}</p>
                    {sandboxHandoffResult.view.blockers.length > 0 && (
                      <ul className="mt-3 list-inside list-disc space-y-1">
                        {sandboxHandoffResult.view.blockers.slice(0, 3).map((blocker) => (
                          <li key={blocker}>{blocker}</li>
                        ))}
                      </ul>
                    )}
                  </Callout>

                  <div className="flex flex-col gap-3 sm:flex-row">
                    {experimentalFeaturesEnabled() && (
                      <Button variant="secondary" asChild>
                        <Link href="/ingest/curation">
                          <ClipboardCheck className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                          Open Curation Queue
                        </Link>
                      </Button>
                    )}
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setActiveTab('file')}
                      trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                    >
                      Continue File Mapping
                    </Button>
                  </div>
                </div>
              ) : (
                <Callout tone="warning" title="Sandbox handoff unavailable">
                  {sandboxHandoffResult?.error ?? 'Return to the free sandbox and save a test run before opening import mapping.'}
                </Callout>
              )}
            </CardContent>
          </Card>
        )}

        {!storedApiKey && (
          <Callout
            tone="warning"
            icon={Key}
            title="API Key Required"
            action={
              <Button size="sm" variant="secondary" asChild>
                <Link href="/developer/portal/keys">
                  How to get a key
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
            }
          >
            You need an API key to ingest documents. RegEngine issues live API keys for your workspace; request one and we will send it to you.
          </Callout>
        )}

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            {jobStatus !== 'completed' ? (
              <Card>
                <CardHeader className="flex-col items-stretch sm:flex-row sm:items-start">
                  <div className="min-w-0">
                    <CardTitle>Ingest New Document</CardTitle>
                    <CardDescription className="mt-1.5 max-w-[70ch]">
                      Provide a URL to a regulatory document. Our system will fetch, normalize, and extract regulatory entities with SHA-256 provenance manifests for every extraction.
                    </CardDescription>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
                    {SOURCE_BADGES.map(({ label, icon: Icon }) => (
                      <Badge key={label} size="sm">
                        <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                        {label}
                      </Badge>
                    ))}
                  </div>
                </CardHeader>
                <CardContent>
                  <form onSubmit={handleSubmit} className="space-y-5">
                    <div className="flex flex-col gap-1.5">
                      <label
                        htmlFor="ingest-api-key"
                        className="inline-flex w-fit items-center gap-1 text-ui font-medium text-re-text-primary"
                      >
                        <span>API Key</span>
                        <HelpTooltip content="Your RegEngine API key starting with 'rge_'. Get one from the Admin page or setup wizard." />
                      </label>
                      <Input
                        id="ingest-api-key"
                        type="password"
                        placeholder="rge_..."
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        disabled={isPending}
                        mono
                      />
                      {storedApiKey && (
                        <p className="text-small text-re-text-tertiary">
                          Using your saved API key
                        </p>
                      )}
                    </div>

                    <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                      <TabsList className="w-full">
                        <TabsTrigger value="url">URL Ingestion</TabsTrigger>
                        <TabsTrigger value="file">File Upload</TabsTrigger>
                      </TabsList>

                      <TabsContent value="url" className="space-y-4">
                        <div className="flex flex-col gap-1.5">
                          <label
                            htmlFor="ingest-url"
                            className="inline-flex w-fit items-center gap-1 text-ui font-medium text-re-text-primary"
                          >
                            <span>Document URL</span>
                            <HelpTooltip content="Publicly accessible URL to a PDF, HTML, or JSON document." />
                          </label>
                          <Input
                            id="ingest-url"
                            type="url"
                            placeholder="https://example.com/regulatory-document.pdf"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            disabled={isPending}
                            leadingIcon={<Link2 strokeWidth={1.75} />}
                          />
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <span className="text-small text-re-text-tertiary">Try an example:</span>
                            {EXAMPLE_URLS.map((example) => (
                              <Button
                                key={example.label}
                                variant="link"
                                size="sm"
                                type="button"
                                onClick={() => {
                                  setUrl(example.url);
                                  setActiveTab('url');
                                }}
                              >
                                {example.label}
                              </Button>
                            ))}
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="file" className="space-y-4">
                        <div className="flex flex-col gap-1.5">
                          <label
                            htmlFor="file-upload"
                            className="inline-flex w-fit items-center gap-1 text-ui font-medium text-re-text-primary"
                          >
                            <span>Select CSV</span>
                            <HelpTooltip content="Upload traceability events as CSV with a cte_type or event_type column." />
                          </label>
                          <div className="rounded-lg border border-dashed border-re-border bg-re-surface-card p-8 text-center transition-colors duration-120 hover:border-re-border-strong hover:bg-re-surface-inset motion-reduce:transition-none">
                            <Input
                              type="file"
                              onChange={handleFileChange}
                              disabled={isPending}
                              className="hidden"
                              id="file-upload"
                              accept=".csv,text/csv"
                            />
                            <label htmlFor="file-upload" className="block cursor-pointer">
                              <Upload
                                className="mx-auto mb-4 h-6 w-6 text-re-text-muted"
                                strokeWidth={1.75}
                                aria-hidden="true"
                              />
                              <div className="text-ui font-medium text-re-text-primary">
                                {file ? file.name : 'Click to select or drag file here'}
                              </div>
                              <div className="mt-2 text-small text-re-text-tertiary">
                                CSV files up to 5MB
                              </div>
                            </label>
                          </div>
                        </div>
                      </TabsContent>
                    </Tabs>

                    <Button
                      type="submit"
                      className="w-full"
                      size="lg"
                      disabled={!apiKey || (activeTab === 'url' ? !url : !file) || isPending}
                    >
                      {isPending ? (
                        <>
                          <Spinner size="sm" />
                          Processing...
                        </>
                      ) : (
                        activeTab === 'url' ? 'Ingest Document' : 'Upload & Process'
                      )}
                    </Button>
                  </form>

                  {activeTab === 'file' && csvResult && (
                    <Callout role="status" tone={csvTone} className="mt-6">
                      <h3 className="font-medium text-re-text-primary">{csvTitle}</h3>
                      <p className="mt-1">{csvResult.accepted} of {csvResult.total} rows accepted; {csvResult.rejected} rejected.</p>
                      {csvResult.events.filter(event => event.status === 'rejected').flatMap(event => event.errors).map((error, index) => (
                        <p key={index} className="mt-2">{error}</p>
                      ))}
                      {csvResult.kde_warnings?.map((warning, index) => (
                        <p key={index} className="mt-2">{warning}</p>
                      ))}
                      <ColumnSuggestionList suggestions={columnSuggestions(csvResult.header_mapping_suggestions)} />
                    </Callout>
                  )}

                  {jobId && (
                    <div className="mt-6 space-y-4 rounded-lg border border-re-border-subtle bg-re-surface-inset p-4">
                      {jobId === 'demo-job-123' && demoBanner}
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-ui font-medium text-re-text-primary">Ingestion Progress</p>
                        <Badge size="sm" mono>Job {jobId}</Badge>
                      </div>
                      <ol className="flex items-start">
                        {STATUS_STEPS.map((step, index) => {
                          const isComplete = index < activeStepIndex;
                          const isActive = index === activeStepIndex;
                          return (
                            <li key={step.id} className="flex flex-1 flex-col items-center gap-2 text-center">
                              <span
                                className={`flex h-8 w-8 items-center justify-center rounded-full border font-mono text-label ${isComplete
                                  ? 'border-re-text-primary bg-re-text-primary text-re-surface-card'
                                  : isActive
                                    ? 'border-re-text-primary text-re-text-primary'
                                    : 'border-re-border text-re-text-tertiary'
                                  }`}
                              >
                                {isComplete ? (
                                  <CheckCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                ) : isActive ? (
                                  <Spinner size="sm" />
                                ) : (
                                  stepNumeral(index)
                                )}
                              </span>
                              <span
                                className={`text-small ${isComplete || isActive ? 'text-re-text-primary' : 'text-re-text-tertiary'}`}
                              >
                                {step.label}
                              </span>
                            </li>
                          );
                        })}
                      </ol>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-small text-re-text-tertiary">
                          <span>Status: {jobStatus.toUpperCase()}</span>
                          <span className="tabular-nums">{progressValue}%</span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-re-border-subtle">
                          <div
                            className="h-full bg-re-text-primary transition-all duration-240 motion-reduce:transition-none"
                            style={{ width: `${progressValue}%` }}
                          />
                        </div>
                      </div>
                      {statusError && (
                        <p className="text-small text-re-text-tertiary">{statusError}</p>
                      )}
                    </div>
                  )}

                  {((activeTab === 'url' && ingestMutation.isError) || (activeTab === 'file' && csvError)) && (
                    <Callout tone="danger" role="alert" className="mt-4">
                      <h4 className="font-medium text-re-text-primary">
                        Ingestion Failed
                      </h4>
                      <p className="mt-1">
                        {(activeTab === 'file' ? csvError : ingestMutation.error?.message) || 'An error occurred during ingestion'}
                      </p>
                      {activeTab === 'file' && (
                        <ColumnSuggestionList suggestions={errorColumnSuggestions} />
                      )}
                      {activeTab === 'file' && cteSuggestion && (
                        <CteSuggestionPrompt
                          suggestion={cteSuggestion}
                          disabled={isPending}
                          onImport={(cte) => void handleSubmit(undefined, cte)}
                        />
                      )}
                      <p className="mt-2">
                        Common issues:
                      </p>
                      <ul className="list-inside list-disc">
                        <li>Invalid or expired API key</li>
                        {activeTab === 'file' ? (
                          <>
                            <li>CSV must include a cte_type or event_type column</li>
                            <li>Upload a CSV file up to 5MB</li>
                          </>
                        ) : (
                          <>
                            <li>URL is not publicly accessible</li>
                            <li>Document format not supported (see the Supported Document Formats list below)</li>
                          </>
                        )}
                      </ul>
                    </Callout>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="space-y-4">
                  {jobId === 'demo-job-123' && demoBanner}
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-subheading text-re-text-primary">
                      Ingestion request completed
                    </h3>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setUrl('');
                        setFile(null);
                        setJobId(null);
                        setJobStatus('queued');
                        ingestMutation.reset();
                        ingestFileMutation.reset();
                      }}
                    >
                      Ingest Another
                    </Button>
                  </div>

                  <NormalizedDocumentViewer
                    documentId={ingestMutation.data?.document_id || 'DEMO-DOC-ID'}
                  />
                </CardContent>
              </Card>
            )}
          </div>

          <aside className="space-y-6">
            <Card>
              <CardContent className="space-y-5">
                <div>
                  <div className="flex items-center gap-2 text-ui font-medium text-re-text-primary">
                    <Upload className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    Normal import
                  </div>
                  <p className="mt-2 text-ui text-re-text-secondary">
                    Use URL ingestion for public documents, or File Upload for CSV traceability events.
                  </p>
                </div>
                {experimentalFeaturesEnabled() && (
                  <div className="border-t border-re-border-subtle pt-5">
                    <div className="flex items-center gap-2 text-ui font-medium text-re-text-primary">
                      <FlaskConical className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                      Inflow Lab
                    </div>
                    <p className="mt-2 text-ui text-re-text-secondary">
                      Use the lab for FSMA event simulation and webhook replay so test traffic stays tagged.
                    </p>
                    <Button size="sm" variant="secondary" className="mt-3" asChild>
                      <Link href="/dashboard/inflow-lab">
                        Open Inflow Lab
                        <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      </Link>
                    </Button>
                  </div>
                )}
                <div className="border-t border-re-border-subtle pt-5">
                  <div className="flex items-center gap-2 text-ui font-medium text-re-text-primary">
                    <ClipboardCheck className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    Review before export
                  </div>
                  <p className="mt-2 text-ui text-re-text-secondary">
                    Send normalized records through curation before using FDA export or recall response workflows.
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="divide-y divide-re-border-subtle p-0">
                {CAPABILITIES.map((capability) => (
                  <div key={capability.title} className="px-5 py-4">
                    <h3 className="text-subheading text-re-text-primary">{capability.title}</h3>
                    <p className="mt-1 text-ui text-re-text-secondary">{capability.body}</p>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Supported Document Formats</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {SUPPORTED_FORMATS.map((format) => (
                    <Badge key={format} size="sm">{format}</Badge>
                  ))}
                  <Badge size="sm">EDI (X12/EDIFACT)</Badge>
                </div>
                <p className="mt-3 text-ui text-re-text-secondary">
                  URL ingestion requires the document to be publicly accessible. For private documents, use the File Upload tab above.
                </p>
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>
    </PageContainer>
  );
}
