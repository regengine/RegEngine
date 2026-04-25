'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState } from 'react';
import { Zap, ArrowRight, AlertTriangle, Check, Clock, Database } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { EmailGate } from '@/components/tools/EmailGate';

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

// Intent color mapping
const intentColors: Record<string, { bg: string; text: string; badge: string }> = {
  trace_forward: { bg: 'bg-re-info-muted', text: 'text-re-info', badge: 'bg-blue-200 text-re-info' },
  trace_backward: { bg: 'bg-purple-50', text: 'text-purple-700', badge: 'bg-purple-200 text-purple-800' },
  lot_timeline: { bg: 'bg-re-success-muted', text: 'text-re-success', badge: 'bg-green-200 text-re-success' },
  events_search: { bg: 'bg-re-surface-card', text: 'text-re-text-disabled', badge: 'bg-re-surface-elevated text-re-text-primary' },
  compliance_gaps: { bg: 'bg-orange-50', text: 'text-orange-700', badge: 'bg-orange-200 text-orange-800' },
  orphan_lots: { bg: 'bg-re-danger-muted', text: 'text-re-danger', badge: 'bg-re-danger-muted text-re-danger' },
};

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
      <div className="max-w-4xl mx-auto space-y-8">
        {/* How It Works Section */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          {[
            { step: '1', label: 'Type', desc: 'Ask a natural language question' },
            { step: '2', label: 'Parse', desc: 'Engine detects intent & extracts filters' },
            { step: '3', label: 'Trace', desc: 'Results show your supply chain data' },
          ].map((item) => (
            <div
              key={item.step}
              className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-lg p-4 text-center border border-slate-200"
            >
              <div className="flex items-center justify-center w-10 h-10 bg-re-info text-white rounded-full font-semibold mx-auto mb-2">
                {item.step}
              </div>
              <h4 className="font-semibold text-slate-900 mb-1">{item.label}</h4>
              <p className="text-sm text-slate-600">{item.desc}</p>
            </div>
          ))}
        </div>

        {/* Query Input Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <div className="relative">
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && e.ctrlKey) {
                  handleQuery();
                }
              }}
              placeholder="Where did lot LOT-2024-001 go after leaving the packing facility?"
              className="w-full p-4 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none text-base"
              rows={3}
            />
            <button
              onClick={() => { void handleQuery(); }}
              disabled={!query.trim() || isLoading}
              className="absolute bottom-4 right-4 inline-flex items-center gap-2 px-4 py-2 bg-re-info text-white rounded-lg hover:bg-re-info disabled:bg-slate-400 disabled:cursor-not-allowed transition-colors font-medium"
            >
              <Zap size={18} />
              Ask
            </button>
          </div>

          {/* Example Queries */}
          <div className="space-y-2">
            <p className="text-sm font-medium text-slate-700">Quick examples:</p>
            <div className="flex flex-wrap gap-2">
              {examples.map((example, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    handleExampleClick(example.label);
                    setTimeout(() => { void handleQuery(example.label); }, 100);
                  }}
                  className="px-3 py-2 text-sm bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full transition-colors border border-slate-200"
                >
                  {example.label}
                </button>
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
                <div className="flex items-start gap-2 rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0 text-yellow-600" />
                  <span>{nlpError}</span>
                </div>
              )}
              {isLiveResult && (
                <div className="flex items-center gap-2 rounded-lg border border-green-300 bg-re-success-muted px-4 py-3 text-sm text-re-success">
                  <Check size={16} className="shrink-0 text-re-success" />
                  <span>Live results from your connected supply chain data.</span>
                </div>
              )}

              {/* Query Analysis */}
              <div className={`rounded-lg border-2 p-6 ${intentColors[result.intent].bg}`}>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-slate-900">Query Analysis</h3>
                    <span className={`px-3 py-1 rounded-full text-sm font-semibold ${intentColors[result.intent].badge}`}>
                      {result.intent.replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </div>

                  <div>
                    <p className="text-sm text-slate-600 mb-2">Confidence Score</p>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 bg-slate-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full transition-all ${
                            result.intent === 'trace_forward' || result.intent === 'trace_backward'
                              ? 'bg-re-info'
                              : result.intent === 'lot_timeline'
                              ? 'bg-re-success'
                              : result.intent === 'compliance_gaps'
                              ? 'bg-orange-600'
                              : result.intent === 'orphan_lots'
                              ? 'bg-re-danger'
                              : 'bg-re-surface-elevated'
                          }`}
                          style={{ width: `${result.confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-slate-700 w-12">
                        {Math.round(result.confidence * 100)}%
                      </span>
                    </div>
                  </div>

                  {Object.keys(result.filters).length > 0 && (
                    <div>
                      <p className="text-sm text-slate-600 mb-2">Extracted Filters</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(result.filters).map(([key, value]) => (
                          <span key={key} className="px-3 py-1 bg-white border border-slate-300 rounded-full text-sm text-slate-700">
                            <span className="font-semibold">{key}:</span> {value}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Results Display */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-slate-900">
                  {isLiveResult ? 'Results' : 'Simulated Results'}
                </h3>

                {result.intent === 'trace_forward' || result.intent === 'trace_backward' ? (
                  <div className="bg-white border border-slate-300 rounded-lg p-6">
                    <div className="space-y-4">
                      {(result.results[0] as TraceResult | undefined)?.nodes?.map((node: TraceNode, idx: number) => (
                        <div key={idx} className="flex items-center gap-4">
                          <div className="flex-1 bg-slate-50 rounded-lg p-4 border border-slate-200">
                            <p className="font-medium text-slate-900">{node.facility}</p>
                            <p className="text-sm text-slate-600">GLN: {node.gln}</p>
                            <p className="text-xs text-slate-500 mt-2">{node.date}</p>
                          </div>
                          {idx < ((result.results[0] as TraceResult | undefined)?.nodes?.length || 0) - 1 && (
                            <ArrowRight className="text-slate-400" size={24} />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : result.intent === 'lot_timeline' ? (
                  <div className="space-y-3">
                    {(result.results as Event[]).map((event, idx) => (
                      <div key={event.id} className="flex gap-4">
                        <div className="flex flex-col items-center">
                          <div className="w-4 h-4 bg-re-info rounded-full mt-1" />
                          {idx < (result.results as Event[]).length - 1 && (
                            <div className="w-1 h-12 bg-slate-200 my-2" />
                          )}
                        </div>
                        <div className="bg-white border border-slate-300 rounded-lg p-4 flex-1">
                          <div className="flex items-start justify-between mb-2">
                            <p className="font-semibold text-slate-900">{event.eventType}</p>
                            <span className="text-xs text-slate-500">{event.timestamp}</span>
                          </div>
                          <p className="text-sm text-slate-700">{event.facility}</p>
                          <p className="text-sm text-slate-600">
                            {event.product} · {event.quantity}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : result.intent === 'events_search' ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-300 bg-slate-50">
                          <th className="px-4 py-3 text-left font-semibold text-slate-900">Timestamp</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-900">Event Type</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-900">Facility</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-900">Product</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-900">Lot</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(result.results as Event[]).map((event) => (
                          <tr key={event.id} className="border-b border-slate-200 hover:bg-slate-50">
                            <td className="px-4 py-3 text-slate-700">{event.timestamp}</td>
                            <td className="px-4 py-3 font-medium text-slate-900">{event.eventType}</td>
                            <td className="px-4 py-3 text-slate-700">{event.facility}</td>
                            <td className="px-4 py-3 text-slate-700">{event.product}</td>
                            <td className="px-4 py-3 font-mono text-slate-700">{event.lot}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : result.intent === 'compliance_gaps' ? (
                  <div className="space-y-3">
                    {(result.results as ComplianceGap[]).map((gap, idx) => (
                      <div key={idx} className="bg-white border border-slate-300 rounded-lg p-4">
                        <div className="flex items-start justify-between mb-2">
                          <p className="font-semibold text-slate-900">{gap.gap}</p>
                          <span
                            className={`px-2 py-1 rounded text-xs font-semibold ${
                              gap.severity === 'high'
                                ? 'bg-re-danger-muted text-re-danger'
                                : gap.severity === 'medium'
                                ? 'bg-orange-100 text-orange-800'
                                : 'bg-re-warning-muted text-yellow-800'
                            }`}
                          >
                            {gap.severity.toUpperCase()}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600 mb-3">{gap.affectedLots} affected lots</p>
                        <div className="bg-slate-50 rounded p-3 border-l-4 border-blue-600">
                          <p className="text-sm font-medium text-slate-900">Remediation:</p>
                          <p className="text-sm text-slate-700 mt-1">{gap.remediation}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : result.intent === 'orphan_lots' ? (
                  <div className="space-y-3">
                    {(result.results as OrphanLot[]).map((orphan, idx) => (
                      <div key={idx} className="bg-re-danger-muted border border-re-danger rounded-lg p-4">
                        <div className="flex items-start justify-between mb-2">
                          <p className="font-mono font-semibold text-re-danger">{orphan.lot}</p>
                          <AlertTriangle size={20} className="text-re-danger" />
                        </div>
                        <p className="text-sm text-re-danger mb-1">{orphan.product}</p>
                        <p className="text-sm text-re-danger">Origin: {orphan.origin}</p>
                        <p className="text-xs text-re-danger mt-2">First seen: {orphan.firstSeen}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              {/* API Evidence */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-slate-900">API Endpoints Called</h3>
                <div className="space-y-3">
                  {result.apiEndpoints.map((endpoint, idx) => (
                    <div key={idx} className="bg-slate-50 border border-slate-300 rounded-lg p-4 font-mono text-sm">
                      <p className="text-re-info font-semibold mb-2">{endpoint.path}</p>
                      <p className="text-slate-700 text-xs mb-2">
                        <span className="text-slate-600">Parameters:</span>{' '}
                        {JSON.stringify(endpoint.params)}
                      </p>
                      <p className="text-slate-600 text-xs">
                        <span className="text-slate-700 font-semibold">Result Type:</span> {endpoint.resultType}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* CTA */}
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-lg p-6 text-center text-white">
                <p className="text-lg font-semibold mb-2">
                  This is a demo of RegEngine's query engine.
                </p>
                <p className="text-blue-100 mb-4">
                  Connect your data for live results across your entire supply chain.
                </p>
                <a
                  href="/onboarding"
                  className="inline-flex items-center gap-2 px-6 py-2 bg-white text-re-info rounded-lg font-semibold hover:bg-re-info-muted transition-colors"
                >
                  Get Started
                  <ArrowRight size={18} />
                </a>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Loading State */}
        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center justify-center py-12"
          >
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-slate-200 border-t-blue-600 rounded-full animate-spin" />
              <p className="text-slate-600 font-medium">Parsing query...</p>
            </div>
          </motion.div>
        )}

        {/* Empty State */}
        {!result && !isLoading && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="text-center py-12"
          >
            <Database size={48} className="mx-auto text-slate-400 mb-4" />
            <p className="text-slate-600 text-lg">Ask a question to see simulated traceability results</p>
            <p className="text-slate-500 text-sm mt-2">
              Or click an example above to try a pre-built query
            </p>
          </motion.div>
        )}
      </div>
      </FreeToolPageShell>
    </EmailGate>
  );
}