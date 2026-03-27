'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import {
  useCanonicalEvents,
  useCanonicalEvent,
  type CanonicalEventDetail,
  type RuleEvaluation,
} from '@/hooks/use-control-plane';

import {
  AlertTriangle,
  CheckCircle,
  ChevronRight,
  Database,
  Eye,
  FileSearch,
  Search,
  Shield,
  XCircle,
} from 'lucide-react';

const SOURCE_LABEL: Record<string, string> = {
  webhook_api: 'Webhook API',
  csv_upload: 'CSV Upload',
  xlsx_upload: 'XLSX Upload',
  epcis_api: 'EPCIS API',
  epcis_xml: 'EPCIS XML',
  edi: 'EDI',
  manual: 'Manual',
  legacy_v002: 'Legacy',
};

export default function CanonicalRecordsPage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || 'demo';

  const [tlcFilter, setTlcFilter] = useState('');
  const [eventTypeFilter, setEventTypeFilter] = useState<string | undefined>();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const events = useCanonicalEvents(tid, {
    tlc: tlcFilter || undefined,
    event_type: eventTypeFilter,
    limit: 50,
  });
  const eventDetail = useCanonicalEvent(tid, selectedEventId || '');

  const records = events.data?.events ?? [];
  const detail = eventDetail.data;

  if (events.error) {
    return (
      <PageContainer>
        <div className="p-8 text-center">
          <p className="text-muted-foreground">Unable to load data from the control plane API.</p>
          <p className="text-sm text-muted-foreground/60 mt-2">{(events.error as Error).message}</p>
          <button onClick={() => events.refetch()} className="mt-4 text-sm text-primary hover:underline">
            Retry
          </button>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Database className="h-6 w-6 text-indigo-500" />
            Canonical Records
          </h1>
          <p className="text-muted-foreground mt-1">
            Every record answers: what is it, where did it come from, what rules applied, what failed, what happens next
          </p>
        </div>
        <Badge variant="outline" className="text-sm">
          {events.data?.total ?? 0} total records
        </Badge>
      </div>

      {/* Search & Filters */}
      <Card className="mb-6">
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by TLC..."
                className="pl-9 h-9 text-sm"
                value={tlcFilter}
                onChange={e => setTlcFilter(e.target.value)}
              />
            </div>
            <select
              className="text-sm border rounded px-2 py-1.5 bg-background h-9"
              value={eventTypeFilter || ''}
              onChange={e => setEventTypeFilter(e.target.value || undefined)}
            >
              <option value="">All Event Types</option>
              <option value="harvesting">Harvesting</option>
              <option value="cooling">Cooling</option>
              <option value="initial_packing">Initial Packing</option>
              <option value="shipping">Shipping</option>
              <option value="receiving">Receiving</option>
              <option value="transformation">Transformation</option>
            </select>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Records Table */}
        <div className={selectedEventId ? 'lg:col-span-1' : 'lg:col-span-3'}>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Traceability Events</CardTitle>
            </CardHeader>
            <CardContent>
              {events.isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-10 w-full" />)}
                </div>
              ) : records.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <FileSearch className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                  <p className="font-medium">No records found</p>
                  <p className="text-sm">Adjust filters or ingest traceability events</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {records.map(evt => (
                    <button
                      key={evt.event_id}
                      className={`w-full text-left px-3 py-2.5 rounded-md transition-colors hover:bg-muted/50 flex items-center justify-between ${
                        selectedEventId === evt.event_id ? 'bg-muted border' : ''
                      }`}
                      onClick={() => setSelectedEventId(
                        selectedEventId === evt.event_id ? null : evt.event_id
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs shrink-0">
                            {evt.event_type.replace(/_/g, ' ')}
                          </Badge>
                          <span className="text-sm font-mono truncate">{evt.traceability_lot_code}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs text-muted-foreground">
                            {evt.product_reference || 'No product ref'}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {SOURCE_LABEL[evt.source_system] || evt.source_system}
                          </span>
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Detail Panel */}
        <AnimatePresence>
          {selectedEventId && (
            <motion.div
              className="lg:col-span-2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
            >
              {eventDetail.isLoading ? (
                <Card>
                  <CardContent className="pt-6">
                    <div className="space-y-4">
                      {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 w-full" />)}
                    </div>
                  </CardContent>
                </Card>
              ) : detail ? (
                <div className="space-y-4">
                  {/* Record Identity */}
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Eye className="h-5 w-5 text-indigo-500" />
                        Record Detail
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                        <div>
                          <dt className="text-muted-foreground">Event Type</dt>
                          <dd className="font-medium">{detail.event_type.replace(/_/g, ' ')}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">TLC</dt>
                          <dd className="font-mono text-xs">{detail.traceability_lot_code}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Product</dt>
                          <dd>{detail.product_reference || '-'}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Quantity</dt>
                          <dd>{detail.quantity} {detail.unit_of_measure}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">From Facility</dt>
                          <dd className="font-mono text-xs">{detail.from_facility_reference || '-'}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">To Facility</dt>
                          <dd className="font-mono text-xs">{detail.to_facility_reference || '-'}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Source System</dt>
                          <dd>{SOURCE_LABEL[detail.source_system] || detail.source_system}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Confidence</dt>
                          <dd>{(detail.confidence_score * 100).toFixed(0)}%</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Event Timestamp</dt>
                          <dd>{new Date(detail.event_timestamp).toLocaleString()}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Schema Version</dt>
                          <dd>{detail.schema_version}</dd>
                        </div>
                      </dl>
                    </CardContent>
                  </Card>

                  {/* Rule Evaluations */}
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Shield className="h-5 w-5 text-blue-500" />
                        Rule Evaluations ({detail.rule_evaluations?.length || 0})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {(!detail.rule_evaluations || detail.rule_evaluations.length === 0) ? (
                        <p className="text-sm text-muted-foreground py-3">No evaluations recorded yet</p>
                      ) : (
                        <div className="space-y-2">
                          {detail.rule_evaluations.map((ev: RuleEvaluation, i: number) => (
                            <div
                              key={i}
                              className={`rounded-md border p-3 text-sm ${
                                ev.result === 'fail' ? 'border-red-200 bg-red-50/50' :
                                ev.result === 'warn' ? 'border-amber-200 bg-amber-50/50' :
                                'border-green-200 bg-green-50/50'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  {ev.result === 'fail' ? <XCircle className="h-4 w-4 text-red-500 shrink-0" /> :
                                   ev.result === 'warn' ? <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" /> :
                                   <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />}
                                  <span className="font-medium">{ev.rule_title}</span>
                                </div>
                                {ev.citation_reference && (
                                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                                    {ev.citation_reference}
                                  </span>
                                )}
                              </div>
                              {ev.why_failed && (
                                <p className="mt-1 text-red-700 ml-6">{ev.why_failed}</p>
                              )}
                              {ev.remediation_suggestion && ev.result !== 'pass' && (
                                <p className="mt-1 text-muted-foreground ml-6 italic">
                                  {ev.remediation_suggestion}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Provenance */}
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium text-muted-foreground">
                        Provenance Metadata
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <pre className="text-xs bg-muted p-3 rounded overflow-x-auto max-h-40">
                        {JSON.stringify(detail.provenance_metadata, null, 2)}
                      </pre>
                    </CardContent>
                  </Card>

                  {/* Exception Cases */}
                  {detail.exception_cases && detail.exception_cases.length > 0 && (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-lg flex items-center gap-2">
                          <AlertTriangle className="h-5 w-5 text-amber-500" />
                          Linked Exceptions ({detail.exception_cases.length})
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-2">
                          {detail.exception_cases.map((exc: any) => (
                            <div key={exc.case_id} className="flex items-center justify-between border rounded p-2 text-sm">
                              <div className="flex items-center gap-2">
                                <Badge variant={exc.severity === 'critical' ? 'destructive' : 'warning'}>
                                  {exc.severity}
                                </Badge>
                                <span>{exc.status}</span>
                              </div>
                              <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                                {exc.recommended_remediation}
                              </span>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              ) : null}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageContainer>
  );
}
