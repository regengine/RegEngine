'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { HelpTooltip } from '@/components/ui/tooltip';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WorkflowStepper } from '@/components/layout/workflow-stepper';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { useIngestURL, useIngestFile } from '@/hooks/use-api';
import {
  Database,
  CheckCircle,
  AlertCircle,
  Link2,
  Upload,
  ArrowRight,
  Key,
  FileText,
  ClipboardCheck,
  Globe,
  Landmark,
  Scale
} from 'lucide-react';
import { NormalizedDocumentViewer } from './NormalizedDocumentViewer';

const EXAMPLE_URLS = [
  {
    label: 'FDA Regulations (21 CFR)',
    url: 'https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-21.xml?chapter=I&subchapter=A&part=1',
  },
  {
    label: 'SEC Regulations',
    url: 'https://www.sec.gov/rules/final/2023/33-11216.pdf',
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

export default function IngestPage() {
  const { apiKey: storedApiKey, setApiKey: storeApiKey } = useAuth();
  const [url, setUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string>('queued');
  const [statusError, setStatusError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('url');
  const [file, setFile] = useState<File | null>(null);

  const ingestMutation = useIngestURL();
  const ingestFileMutation = useIngestFile();
  const isPending = ingestMutation.isPending || ingestFileMutation.isPending;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  // Initialize API key from stored value
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey) return;
    if (activeTab === 'url' && !url) return;
    if (activeTab === 'file' && !file) return;

    // Store the API key for future use
    if (apiKey !== storedApiKey) {
      storeApiKey(apiKey);
    }
    setJobId(null);
    setJobStatus('queued');
    setStatusError(null);

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
      let result;
      if (activeTab === 'url') {
        result = await ingestMutation.mutateAsync({ apiKey, url });
      } else {
        if (!file) return;
        result = await ingestFileMutation.mutateAsync({ apiKey, file });
      }

      const returnedJobId = (result as any)?.job_id || (result as any)?.doc_id || null;
      if (returnedJobId) {
        setJobId(returnedJobId);
        setJobStatus('queued');
        setStatusError(null);
      }
    } catch (error) {
      console.error('Ingestion failed:', error);
    }
  };

  const handleExampleClick = (exampleUrl: string) => {
    setUrl(exampleUrl);
  };

  const activeStepIndex = Math.max(
    STATUS_STEPS.findIndex((step) => step.id === jobStatus),
    0
  );
  const progressValue = STATUS_PROGRESS[jobStatus] ?? 0;

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-4xl mx-auto"
        >
          {/* Workflow Progress */}
          <div className="mb-8">
            <WorkflowStepper currentStep="ingest" completedSteps={storedApiKey ? ['setup'] : []} />
          </div>

          {/* Page Header */}
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
              <Database className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">Document Ingestion</h1>
              <p className="text-muted-foreground mt-1">
                Submit regulatory document URLs for processing
              </p>
            </div>
          </div>

          {/* No API Key Warning */}
          {!storedApiKey && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6"
            >
              <Card className="border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-3">
                    <Key className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-medium text-amber-900 dark:text-amber-100">
                        API Key Required
                      </p>
                      <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                        You need an API key to ingest documents. Complete the setup wizard to get started.
                      </p>
                      <Link href="/onboarding">
                        <Button size="sm" variant="outline" className="mt-3">
                          Go to Setup
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Quick Start / Demo Ingestion */}
          {/* Ingestion Form */}
          {jobStatus !== 'completed' ? (
            <Card className="mb-8">
              <CardHeader>
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  <div>
                    <CardTitle>Ingest New Document</CardTitle>
                    <CardDescription className="mt-1.5 max-w-[500px]">
                      Provide a URL to a regulatory document. Our system will fetch, normalize, and extract regulatory entities with 100% unbreakable provenance linking.
                    </CardDescription>
                  </div>
                  <div className="flex gap-3 pt-1">
                    <Badge variant="outline" className="flex items-center gap-1.5 py-1 px-2.5 bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-400">
                      <Scale className="h-3 w-3" />
                      eCFR
                    </Badge>
                    <Badge variant="outline" className="flex items-center gap-1.5 py-1 px-2.5 bg-amber-50 dark:bg-amber-900/10 text-amber-700 dark:text-amber-500 border-amber-200 dark:border-amber-900/50">
                      <Landmark className="h-3 w-3" />
                      Federal Register
                    </Badge>
                    <Badge variant="outline" className="flex items-center gap-1.5 py-1 px-2.5 bg-blue-50 dark:bg-blue-900/10 text-blue-700 dark:text-blue-500 border-blue-200 dark:border-blue-900/50">
                      <Globe className="h-3 w-3" />
                      FDA.gov
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="text-sm font-medium mb-2 block">
                      API Key
                      <HelpTooltip content="Your RegEngine API key starting with 'rge_'. Get one from the Admin page or setup wizard." />
                    </label>
                    <Input
                      type="password"
                      placeholder="rge_..."
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      disabled={isPending}
                    />
                    {storedApiKey && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Using your saved API key
                      </p>
                    )}
                  </div>

                  <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsList className="grid w-full grid-cols-2">
                      <TabsTrigger value="url">URL Ingestion</TabsTrigger>
                      <TabsTrigger value="file">File Upload</TabsTrigger>
                    </TabsList>

                    <TabsContent value="url" className="space-y-4 pt-4">
                      <div>
                        <label className="text-sm font-medium mb-2 block">
                          Document URL
                          <HelpTooltip content="Publicly accessible URL to a PDF, HTML, or JSON document." />
                        </label>
                        <div className="relative">
                          <Link2 className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                          <Input
                            type="url"
                            placeholder="https://example.com/regulatory-document.pdf"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            className="pl-10"
                            disabled={isPending}
                          />
                        </div>
                        <div className="flex flex-wrap gap-2 mt-2">
                          <span className="text-xs text-muted-foreground">Try an example:</span>
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
                              className="text-xs h-auto p-0 text-primary hover:underline"
                            >
                              {example.label}
                            </Button>
                          ))}
                        </div>
                      </div>
                    </TabsContent>

                    <TabsContent value="file" className="space-y-4 pt-4">
                      <div>
                        <label className="text-sm font-medium mb-2 block">
                          Select Document
                          <HelpTooltip content="Upload PDF, DOCX, HTML, JSON, or XML file." />
                        </label>
                        <div className="border-2 border-dashed rounded-lg p-8 text-center hover:bg-muted/50 transition-colors">
                          <Input
                            type="file"
                            onChange={handleFileChange}
                            disabled={isPending}
                            className="hidden"
                            id="file-upload"
                            accept=".pdf,.html,.json,.xml,.docx,.txt"
                          />
                          <label htmlFor="file-upload" className="cursor-pointer block">
                            <Upload className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                            <div className="text-sm font-medium">
                              {file ? file.name : 'Click to select or drag file here'}
                            </div>
                            <div className="text-xs text-muted-foreground mt-2">
                              Max size: 20MB
                            </div>
                          </label>
                        </div>
                      </div>
                    </TabsContent>
                  </Tabs>

                  <Button
                    type="submit"
                    className="w-full"
                    disabled={!apiKey || (activeTab === 'url' ? !url : !file) || isPending}
                  >
                    {isPending ? (
                      <>
                        <Spinner size="sm" className="mr-2" />
                        Processing...
                      </>
                    ) : (
                      activeTab === 'url' ? 'Ingest Document' : 'Upload & Process'
                    )}
                  </Button>
                </form>

                {/* Success Viewer */}
                {(ingestMutation.isSuccess || ingestFileMutation.isSuccess) && jobStatus === 'completed' && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-6"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="h-5 w-5 text-emerald-500" />
                        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                          Document Successfully Normalized
                        </h3>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
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
                      documentId={ingestMutation.data?.document_id || ingestFileMutation.data?.document_id || 'DEMO-DOC-ID'}
                    />
                  </motion.div>
                )}

                {jobId && (
                  <div className="mt-6 p-4 rounded-lg border bg-muted/40">
                    <div className="flex items-center justify-between mb-4">
                      <p className="text-sm font-semibold">Ingestion Progress</p>
                      <Badge variant="secondary">Job {jobId}</Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      {STATUS_STEPS.map((step, index) => {
                        const isComplete = index < activeStepIndex;
                        const isActive = index === activeStepIndex;
                        return (
                          <div key={step.id} className="flex-1 flex flex-col items-center">
                            <div
                              className={`h-10 w-10 rounded-full flex items-center justify-center ${isComplete
                                ? 'bg-primary text-primary-foreground'
                                : isActive
                                  ? 'bg-primary/20 text-primary'
                                  : 'bg-muted text-muted-foreground'
                                }`}
                            >
                              {isComplete ? (
                                <CheckCircle className="h-5 w-5" />
                              ) : isActive ? (
                                <Spinner size="sm" />
                              ) : (
                                index + 1
                              )}
                            </div>
                            <span className={`text-xs mt-2 ${isComplete || isActive ? 'text-primary' : 'text-muted-foreground'}`}>
                              {step.label}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-4 space-y-2">
                      <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
                        <span>Status: {jobStatus.toUpperCase()}</span>
                        <span>{progressValue}%</span>
                      </div>
                      <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-2 bg-primary transition-all duration-500"
                          style={{ width: `${progressValue}%` }}
                        />
                      </div>
                    </div>
                    {statusError && (
                      <p className="text-xs text-destructive mt-3">{statusError}</p>
                    )}
                  </div>
                )}

                {/* Error Message */}
                {(ingestMutation.isError || ingestFileMutation.isError) && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-4 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800"
                  >
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mt-0.5" />
                      <div className="flex-1">
                        <h4 className="font-semibold text-red-900 dark:text-red-100">
                          Ingestion Failed
                        </h4>
                        <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                          {(ingestMutation.error as any)?.message || (ingestFileMutation.error as any)?.message || 'An error occurred during ingestion'}
                        </p>
                        <p className="text-sm text-red-700 dark:text-red-300 mt-2">
                          Common issues:
                        </p>
                        <ul className="text-sm text-red-700 dark:text-red-300 list-disc list-inside">
                          <li>Invalid or expired API key</li>
                          <li>URL is not publicly accessible</li>
                          <li>Document format not supported (use PDF, HTML, or JSON)</li>
                        </ul>
                      </div>
                    </div>
                  </motion.div>
                )}
              </CardContent>
            </Card>
          ) : null}

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardContent className="pt-6">
                <h3 className="font-semibold mb-2">OCR Processing</h3>
                <p className="text-sm text-muted-foreground">
                  Automatic optical character recognition for scanned documents
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="font-semibold mb-2">NLP Extraction</h3>
                <p className="text-sm text-muted-foreground">
                  Extract regulatory entities, obligations, and thresholds using ML
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="font-semibold mb-2">Graph Storage</h3>
                <p className="text-sm text-muted-foreground">
                  Store in a graph database with bitemporal modeling for compliance tracking
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Supported Formats */}
          <Card className="mt-8">
            <CardHeader>
              <CardTitle className="text-lg">Supported Document Formats</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">PDF</Badge>
                <Badge variant="secondary">HTML</Badge>
                <Badge variant="secondary">JSON</Badge>
                <Badge variant="secondary">XML</Badge>
                <Badge variant="secondary">CSV</Badge>
                <Badge variant="secondary">Excel (.xlsx)</Badge>
                <Badge variant="secondary">Word (.docx)</Badge>
                <Badge variant="secondary">Plain Text</Badge>
                <Badge variant="outline">EDI (X12/EDIFACT)</Badge>
              </div>
              <p className="text-sm text-muted-foreground mt-3">
                Documents must be publicly accessible via URL. For private documents, use the API directly with file upload.
              </p>
            </CardContent>
          </Card>
        </motion.div>
      </PageContainer>
    </div>
  );
}
