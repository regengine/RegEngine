'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState } from 'react';
import { Zap, ArrowRight, AlertTriangle, Check, Database } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { EmailGate } from '@/components/tools/EmailGate';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { isExperimentalToolEnabled } from '@/lib/experimental-features';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { fieldControlClasses } from '@/components/ui/field-control';
import { cn } from '@/lib/utils';

// Types
interface QueryResult {
  intent: string;
  confidence: number;
  filters: Record<string, string>;
  results: unknown[];
  apiEndpoints: Array<{ path: string; params: Record<string, string>; resultType: string }>;
}

interface TraceNode {
  facility: string;
  gln: string;
  date: string;
  type: string;
}

interface Event {
  id: string;
  timestamp: string;
  eventType: string;
  gln: string;
  facility: string;
  product: string;
  lot: string;
  quantity: string;
}

interface ComplianceGap {
  severity: 'high' | 'medium' | 'low';
  gap: string;
  affectedLots: number;
  remediation: string;
}

// Intent → Badge tone. Colour lives in the badge only (SPEC §1.6): the panel
// itself stays on the card surface so a result page never becomes a colour field.
const intentTones: Record<string, BadgeTone> = {
  trace_forward: 'info',
  trace_backward: 'corrected',
  lot_timeline: 'success',
  events_search: 'neutral',
  compliance_gaps: 'warning',
  orphan_lots: 'danger',
};

const severityTones: Record<ComplianceGap['severity'], BadgeTone> = {
  high: 'danger',
  medium: 'warning',
  low: 'warning',
};

const EVENT_COLUMNS = [
  { key: 'timestamp', header: 'Timestamp', mono: true, cell: (row: Event) => row.timestamp },
  { key: 'eventType', header: 'Event Type', cell: (row: Event) => row.eventType },
  { key: 'facility', header: 'Facility', cell: (row: Event) => row.facility },
  { key: 'product', header: 'Product', cell: (row: Event) => row.product },
  { key: 'lot', header: 'Lot', mono: true, cell: (row: Event) => row.lot },
];

// Query parser logic
function parseQuery(query: string): QueryResult {
  const lowerQuery: string = query.toLowerCase();
  let intent: string = 'events_search';
  let confidence: number = 0;
  const filters: Record<string, string> = {};

  // Intent detection
  if (lowerQuery.includes('where did') && (lowerQuery.includes('go') || lowerQuery.includes('end'))) {
    intent = 'trace_forward';
    confidence = 0.95;
  } else if (lowerQuery.includes('where did') && (lowerQuery.includes('come from') || lowerQuery.includes('source') || lowerQuery.includes('origin'))) {
    intent = 'trace_backward';
    confidence = 0.95;
  } else if (lowerQuery.includes('timeline') || lowerQuery.includes('history')) {
    intent = 'lot_timeline';
    confidence = 0.9;
  } else if (lowerQuery.includes('find') || lowerQuery.includes('show') || lowerQuery.includes('list')) {
    if (lowerQuery.includes('gap') || lowerQuery.includes('missing') || lowerQuery.includes('incomplete')) {
      intent = 'compliance_gaps';
      confidence = 0.88;
    } else if (lowerQuery.includes('orphan') || lowerQuery.includes('unlink')) {
      intent = 'orphan_lots';
      confidence = 0.85;
    } else {
      intent = 'events_search';
      confidence = 0.8;
    }
  } else if (lowerQuery.includes('gap') || lowerQuery.includes('missing') || lowerQuery.includes('incomplete')) {
    intent = 'compliance_gaps';
    confidence = 0.87;
  } else if (lowerQuery.includes('orphan') || lowerQuery.includes('unlink')) {
    intent = 'orphan_lots';
    confidence = 0.85;
  } else {
    confidence = 0.75;
  }

  // Filter extraction
  const lotMatch = query.match(/LOT-\d{4}-\d{3}/);
  if (lotMatch) filters['lot'] = lotMatch[0];

  const datePatterns = ['last 30 days', 'last 7 days', 'last 90 days', 'today', 'this week', 'this month'];
  const matchedDate = datePatterns.find(p => lowerQuery.includes(p));
  if (matchedDate) filters['date'] = matchedDate;

  const products = ['romaine lettuce', 'lettuce', 'spinach', 'carrots', 'tomatoes', 'fresh produce', 'produce'];
  const matchedProduct = products.find(p => lowerQuery.includes(p));
  if (matchedProduct) filters['product'] = matchedProduct;

  const eventTypes = ['receiving', 'packing', 'shipping', 'receiving event'];
  const matchedEvent = eventTypes.find(e => lowerQuery.includes(e));
  if (matchedEvent) filters['eventType'] = matchedEvent;

  return {
    intent,
    confidence,
    filters,
    results: generateResults(intent, filters),
    apiEndpoints: generateEndpoints(intent, filters),
  };
}

// Generate realistic demo results
interface TraceResult {
  type: string;
  nodes: TraceNode[];
  lotId?: string;
  product?: string;
}

interface OrphanLot {
  lot: string;
  product: string;
  origin: string;
  firstSeen: string;
}

function generateResults(intent: string, filters: Record<string, string>): unknown[] {
  switch (intent) {
    case 'trace_forward': {
      const nodes: TraceNode[] = [
        { facility: 'Produce Farm CA-001', gln: '0614141234567', date: '2024-03-10 06:00', type: 'Origin' },
        { facility: 'Regional Packing Center', gln: '0614141234568', date: '2024-03-10 14:30', type: 'Packing' },
        { facility: 'Distribution Center LA', gln: '0614141234569', date: '2024-03-11 08:00', type: 'Distribution' },
        { facility: 'Retail Chain Warehouse', gln: '0614141234570', date: '2024-03-11 16:45', type: 'Warehouse' },
      ];
      return [{ type: 'trace', nodes, lotId: filters['lot'] || 'LOT-2024-001' }];
    }
    case 'trace_backward': {
      const nodes: TraceNode[] = [
        { facility: 'Retail Store #432', gln: '0614141234570', date: '2024-03-12 10:00', type: 'Retail' },
        { facility: 'Distribution Center LA', gln: '0614141234569', date: '2024-03-11 22:00', type: 'Distribution' },
        { facility: 'Regional Packing Center', gln: '0614141234568', date: '2024-03-11 06:00', type: 'Packing' },
        { facility: 'Goodrich Farm CA', gln: '0614141234567', date: '2024-03-10 05:30', type: 'Farm' },
      ];
      return [{ type: 'trace', nodes, product: filters['product'] || 'Romaine Lettuce' }];
    }
    case 'lot_timeline': {
      const events: Event[] = [
        {
          id: 'evt-001',
          timestamp: '2024-03-10 06:15',
          eventType: 'Harvest',
          gln: '0614141234567',
          facility: 'Goodrich Farm CA-001',
          product: 'Romaine Lettuce',
          lot: filters['lot'] || 'LOT-2024-001',
          quantity: '5000 lbs',
        },
        {
          id: 'evt-002',
          timestamp: '2024-03-10 14:30',
          eventType: 'Receiving',
          gln: '0614141234568',
          facility: 'Regional Packing Center',
          product: 'Romaine Lettuce',
          lot: filters['lot'] || 'LOT-2024-001',
          quantity: '5000 lbs',
        },
        {
          id: 'evt-003',
          timestamp: '2024-03-10 16:00',
          eventType: 'Processing',
          gln: '0614141234568',
          facility: 'Regional Packing Center',
          product: 'Romaine Lettuce (Packed)',
          lot: filters['lot'] || 'LOT-2024-001',
          quantity: '4800 lbs',
        },
        {
          id: 'evt-004',
          timestamp: '2024-03-11 08:00',
          eventType: 'Shipping',
          gln: '0614141234568',
          facility: 'Regional Packing Center',
          product: 'Romaine Lettuce (Packed)',
          lot: filters['lot'] || 'LOT-2024-001',
          quantity: '4800 lbs',
        },
        {
          id: 'evt-005',
          timestamp: '2024-03-11 16:45',
          eventType: 'Receiving',
          gln: '0614141234569',
          facility: 'Distribution Center LA',
          product: 'Romaine Lettuce (Packed)',
          lot: filters['lot'] || 'LOT-2024-001',
          quantity: '4800 lbs',
        },
      ];
      return events;
    }
    case 'events_search': {
      const dateFilter = filters['date'] || 'last 30 days';
      const events: Event[] = [
        {
          id: 'evt-101',
          timestamp: '2024-03-15 09:30',
          eventType: 'Receiving',
          gln: '0614141234568',
          facility: 'Regional Packing Center',
          product: 'Romaine Lettuce',
          lot: 'LOT-2024-045',
          quantity: '3500 lbs',
        },
        {
          id: 'evt-102',
          timestamp: '2024-03-14 11:00',
          eventType: 'Shipping',
          gln: '0614141234567',
          facility: 'Goodrich Farm CA-001',
          product: 'Romaine Lettuce',
          lot: 'LOT-2024-044',
          quantity: '5000 lbs',
        },
        {
          id: 'evt-103',
          timestamp: '2024-03-13 14:20',
          eventType: 'Packing',
          gln: '0614141234568',
          facility: 'Regional Packing Center',
          product: 'Spinach',
          lot: 'LOT-2024-043',
          quantity: '2200 lbs',
        },
        {
          id: 'evt-104',
          timestamp: '2024-03-12 08:45',
          eventType: 'Receiving',
          gln: '0614141234569',
          facility: 'Distribution Center LA',
          product: 'Carrots',
          lot: 'LOT-2024-042',
          quantity: '8000 lbs',
        },
      ];
      return events;
    }
    case 'compliance_gaps': {
      const gaps: ComplianceGap[] = [
        {
          severity: 'high',
          gap: 'Missing temperature control records at Regional Packing Center',
          affectedLots: 8,
          remediation: 'Install IoT sensors and enable automated logging',
        },
        {
          severity: 'medium',
          gap: 'Incomplete supplier verification documents',
          affectedLots: 3,
          remediation: 'Request COA and GLN verification from 3 suppliers',
        },
        {
          severity: 'low',
          gap: 'Non-standardized lot code format in older shipments',
          affectedLots: 12,
          remediation: 'Update legacy records to FSMA standard format',
        },
      ];
      return gaps;
    }
    case 'orphan_lots': {
      const orphans = [
        { lot: 'LOT-2024-015', product: 'Romaine Lettuce', origin: 'Unknown Supplier', firstSeen: '2024-03-08' },
        { lot: 'LOT-2024-022', product: 'Spinach', origin: 'No matching farm record', firstSeen: '2024-03-11' },
        { lot: 'LOT-2024-031', product: 'Carrots', origin: 'Missing harvest event', firstSeen: '2024-03-13' },
      ];
      return orphans;
    }
    default:
      return [];
  }
}

// Generate API endpoint info
function generateEndpoints(intent: string, filters: Record<string, string>): Array<{ path: string; params: Record<string, string>; resultType: string }> {
  const baseEndpoints: { path: string; params: Record<string, string>; resultType: string }[] = [
    {
      path: '/api/graph/query',
      params: { intent, ...filters },
      resultType: 'QueryResult',
    },
  ];

  if (filters['lot']) {
    baseEndpoints.push({
      path: '/api/graph/lot/{lot}',
      params: { lot: filters['lot'] },
      resultType: 'LotData',
    });
  }

  if (filters['date']) {
    baseEndpoints.push({
      path: '/api/graph/events',
      params: { dateRange: filters['date'] },
      resultType: 'EventList',
    });
  }

  return baseEndpoints;
}

// Example queries
const examples = [
  { label: 'Where did lot LOT-2024-001 go?', intent: 'trace_forward' },
  { label: 'Where did the romaine lettuce come from?', intent: 'trace_backward' },
  { label: 'Show timeline for lot LOT-2024-003', intent: 'lot_timeline' },
  { label: 'Find all receiving events last 30 days', intent: 'events_search' },
  { label: 'Show compliance gaps for fresh produce', intent: 'compliance_gaps' },
  { label: 'Find orphaned lots without matching events', intent: 'orphan_lots' },
];

export default function AskPage() {
  if (!isExperimentalToolEnabled('ask')) {
    return (
      <FeatureNotEnabled
        featureName="Traceability Query Engine"
        backHref="/tools"
        backLabel="Back to free tools"
      />
    );
  }
  return <AskPageContent />;
}

function AskPageContent() {
  const [query, setQuery] = useState<string>('');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isLiveResult, setIsLiveResult] = useState<boolean>(false);
  const [nlpError, setNlpError] = useState<string | null>(null);

  const handleQuery = async (q?: string): Promise<void> => {
    const finalQuery = q || query;
    if (!finalQuery.trim()) return;

    setIsLoading(true);
    setNlpError(null);
    setIsLiveResult(false);

    try {
      // Attempt to call the live NLP service via the server-side proxy.
      const response = await fetchWithCsrf('/api/nlp/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: finalQuery, limit: 50 }),
      });

      if (response.ok) {
        const data = await response.json();
        // Map the NLP service response shape to the local QueryResult type.
        setResult({
          intent: data.intent ?? 'events_search',
          confidence: data.confidence ?? 0,
          filters: data.filters ?? {},
          results: data.results ?? [],
          apiEndpoints: (data.evidence ?? []).map((e: { endpoint: string; params?: Record<string, string>; result_count?: number }) => ({
            path: e.endpoint,
            params: e.params ?? {},
            resultType: 'LiveResult',
          })),
        });
        setIsLiveResult(true);
      } else if (response.status === 503) {
        // NLP service not configured — fall back to local stub with a notice.
        setNlpError('NLP service not configured — showing simulated results.');
        setResult(parseQuery(finalQuery));
      } else {
        const errData = await response.json().catch(() => ({}));
        setNlpError(`NLP service error (${response.status}): ${errData.detail ?? 'unknown error'} — showing simulated results.`);
        setResult(parseQuery(finalQuery));
      }
    } catch (err) {
      setNlpError(`Could not reach NLP service: ${String(err)} — showing simulated results.`);
      setResult(parseQuery(finalQuery));
    } finally {
      setIsLoading(false);
    }
  };

  const handleExampleClick = (example: string): void => {
    setQuery(example);
  };

  return (
    <EmailGate toolName="ask">
      <FreeToolPageShell
        title="Traceability Query Engine"
        subtitle="Ask questions about your supply chain in plain English. No SQL required."
        relatedToolIds={['cte-mapper', 'kde-checker', 'ftl-checker']}
      >
        {/* How It Works Section */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[
            { step: '1', label: 'Type', desc: 'Ask a natural language question' },
            { step: '2', label: 'Parse', desc: 'Engine detects intent & extracts filters' },
            { step: '3', label: 'Trace', desc: 'Results show your supply chain data' },
          ].map((item) => (
            <Card key={item.step} variant="inset" padding="compact" className="text-center">
              <span className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono uppercase text-label text-re-text-secondary">
                {item.step}
              </span>
              <h4 className="mb-1 text-subheading text-re-text-primary">{item.label}</h4>
              <p className="text-ui text-re-text-secondary">{item.desc}</p>
            </Card>
          ))}
        </div>

        {/* Query Input Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <Field label="Ask" htmlFor="ask-query" className="[&>label]:sr-only">
            <Textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && e.ctrlKey) {
                  handleQuery();
                }
              }}
              placeholder="Where did lot LOT-2024-001 go after leaving the packing facility?"
              className={cn(fieldControlClasses, 'h-auto min-h-[88px] resize-none py-3')}
              rows={3}
            />
          </Field>
          <div className="flex justify-end">
            <Button
              onClick={() => { void handleQuery(); }}
              disabled={!query.trim() || isLoading}
              leadingIcon={<Zap size={18} strokeWidth={1.75} aria-hidden="true" />}
            >
              Ask
            </Button>
          </div>

          {/* Example Queries */}
          <div className="space-y-2">
            <p className="text-ui font-medium text-re-text-secondary">Quick examples:</p>
            <div className="flex flex-wrap gap-2">
              {examples.map((example, idx) => (
                <Button
                  key={idx}
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    handleExampleClick(example.label);
                    setTimeout(() => { void handleQuery(example.label); }, 100);
                  }}
                >
                  {example.label}
                </Button>
              ))}
            </div>
          </div>
        </motion.div>

        {/* Results Section */}
        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-6"
            >
              {/* Live vs simulated notice */}
              {nlpError && (
                <Callout tone="warning" role="status" icon={AlertTriangle}>
                  {nlpError}
                </Callout>
              )}
              {isLiveResult && (
                <Callout tone="success" role="status" icon={Check}>
                  Live results from your connected supply chain data.
                </Callout>
              )}

              {/* Query Analysis */}
              <Card padding="spacious">
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="text-subheading text-re-text-primary">Query Analysis</h3>
                    <Badge tone={intentTones[result.intent] ?? 'neutral'} mono>
                      {result.intent.replace(/_/g, ' ').toUpperCase()}
                    </Badge>
                  </div>

                  <div>
                    <p className="mb-2 font-mono uppercase text-label text-re-text-muted">Confidence Score</p>
                    <div className="flex items-center gap-3">
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-re-surface-inset">
                        <div
                          className="h-2 rounded-full bg-re-text-tertiary transition-[width] duration-240 motion-reduce:transition-none"
                          style={{ width: `${result.confidence * 100}%` }}
                        />
                      </div>
                      <span className="w-12 text-ui font-medium tabular-nums text-re-text-secondary">
                        {Math.round(result.confidence * 100)}%
                      </span>
                    </div>
                  </div>

                  {Object.keys(result.filters).length > 0 && (
                    <div>
                      <p className="mb-2 font-mono uppercase text-label text-re-text-muted">Extracted Filters</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(result.filters).map(([key, value]) => (
                          <Badge key={key} tone="neutral" mono>
                            <span className="font-medium">{key}:</span> {value}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Card>

              {/* Results Display */}
              <div className="space-y-4">
                <h3 className="text-subheading text-re-text-primary">
                  {isLiveResult ? 'Results' : 'Simulated Results'}
                </h3>

                {result.intent === 'trace_forward' || result.intent === 'trace_backward' ? (
                  <Card padding="spacious">
                    <div className="space-y-4">
                      {(result.results[0] as TraceResult | undefined)?.nodes?.map((node: TraceNode, idx: number) => (
                        <div key={idx} className="flex items-center gap-4">
                          <div className="min-w-0 flex-1 rounded-md border border-re-border-subtle bg-re-surface-inset p-4">
                            <p className="text-ui font-medium text-re-text-primary">{node.facility}</p>
                            <p className="font-mono text-[0.8125rem] text-re-text-secondary">GLN: {node.gln}</p>
                            <p className="mt-2 font-mono text-[0.8125rem] text-re-text-tertiary">{node.date}</p>
                          </div>
                          {idx < ((result.results[0] as TraceResult | undefined)?.nodes?.length || 0) - 1 && (
                            <ArrowRight className="shrink-0 text-re-text-tertiary" size={20} strokeWidth={1.75} aria-hidden="true" />
                          )}
                        </div>
                      ))}
                    </div>
                  </Card>
                ) : result.intent === 'lot_timeline' ? (
                  <div className="space-y-3">
                    {(result.results as Event[]).map((event, idx) => (
                      <div key={event.id} className="flex gap-4">
                        <div className="flex flex-col items-center" aria-hidden="true">
                          <span className="mt-1 h-3 w-3 rounded-full border border-re-border-strong bg-re-surface-card" />
                          {idx < (result.results as Event[]).length - 1 && (
                            <span className="my-2 h-12 w-px bg-re-border" />
                          )}
                        </div>
                        <Card padding="compact" className="min-w-0 flex-1">
                          <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                            <p className="text-ui font-medium text-re-text-primary">{event.eventType}</p>
                            <span className="font-mono text-[0.8125rem] text-re-text-tertiary">{event.timestamp}</span>
                          </div>
                          <p className="text-ui text-re-text-secondary">{event.facility}</p>
                          <p className="text-ui text-re-text-tertiary">
                            {event.product} · {event.quantity}
                          </p>
                        </Card>
                      </div>
                    ))}
                  </div>
                ) : result.intent === 'events_search' ? (
                  <DataTable
                    caption={isLiveResult ? 'Results' : 'Simulated Results'}
                    columns={EVENT_COLUMNS}
                    data={result.results as Event[]}
                    rowKey={(row) => row.id}
                    stickyFirstColumn
                  />
                ) : result.intent === 'compliance_gaps' ? (
                  <div className="space-y-3">
                    {(result.results as ComplianceGap[]).map((gap, idx) => (
                      <Card key={idx} padding="compact">
                        <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                          <p className="text-ui font-medium text-re-text-primary">{gap.gap}</p>
                          <Badge tone={severityTones[gap.severity]} size="sm" mono>
                            {gap.severity.toUpperCase()}
                          </Badge>
                        </div>
                        <p className="mb-3 text-ui text-re-text-secondary">{gap.affectedLots} affected lots</p>
                        <Callout tone="info" role="note" title="Remediation:">
                          {gap.remediation}
                        </Callout>
                      </Card>
                    ))}
                  </div>
                ) : result.intent === 'orphan_lots' ? (
                  <div className="space-y-3">
                    {(result.results as OrphanLot[]).map((orphan, idx) => (
                      <Callout
                        key={idx}
                        tone="danger"
                        role="alert"
                        icon={AlertTriangle}
                        title={<span className="font-mono">{orphan.lot}</span>}
                      >
                        <p>{orphan.product}</p>
                        <p>Origin: {orphan.origin}</p>
                        <p className="mt-2 text-small">First seen: {orphan.firstSeen}</p>
                      </Callout>
                    ))}
                  </div>
                ) : null}
              </div>

              {/* API Evidence */}
              <div className="space-y-4">
                <h3 className="text-subheading text-re-text-primary">Endpoints this query would call</h3>
                <div className="space-y-3">
                  {result.apiEndpoints.map((endpoint, idx) => (
                    <Card key={idx} variant="inset" padding="compact" className="overflow-x-auto font-mono text-[0.8125rem]">
                      <p className="mb-2 font-medium text-re-text-primary">{endpoint.path}</p>
                      <p className="mb-2 text-re-text-secondary">
                        <span className="text-re-text-tertiary">Parameters:</span>{' '}
                        {JSON.stringify(endpoint.params)}
                      </p>
                      <p className="text-re-text-secondary">
                        <span className="font-medium text-re-text-tertiary">Result Type:</span> {endpoint.resultType}
                      </p>
                    </Card>
                  ))}
                </div>
              </div>

              {/* CTA */}
              <Card variant="inset" padding="spacious" className="text-center">
                <p className="mb-2 text-subheading text-re-text-primary">
                  This is a demo of RegEngine&apos;s query engine.
                </p>
                <p className="mb-4 text-ui text-re-text-secondary">
                  Connect your data for live results across your entire supply chain.
                </p>
                <Button asChild>
                  <a href="/onboarding">
                    Get Started
                    <ArrowRight size={18} strokeWidth={1.75} aria-hidden="true" />
                  </a>
                </Button>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Loading State */}
        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-4 py-6"
            aria-busy="true"
          >
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-40 w-full rounded-lg" />
            <p className="text-center text-ui font-medium text-re-text-secondary">Parsing query...</p>
          </motion.div>
        )}

        {/* Empty State */}
        {!result && !isLoading && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <EmptyState
              icon={Database}
              title="Ask a question to see simulated traceability results"
              description="Or click an example above to try a pre-built query"
            />
          </motion.div>
        )}
      </FreeToolPageShell>
    </EmailGate>
  );
}
