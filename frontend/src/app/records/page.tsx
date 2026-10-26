'use client';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { ErrorState } from '@/components/ui/error-state';
import { fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';

import { useAuth } from '@/lib/auth-context';
import { getErrorRequestId, getErrorRetryAfter, getErrorStatus } from '@/lib/api-error';
import {
  useCanonicalEvents,
  useCanonicalEvent,
  type CanonicalEvent,
  type RuleEvaluation,
  type ExceptionCase,
} from '@/hooks/use-control-plane';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  AlertTriangle,
  FileSearch,
  Filter,
} from 'lucide-react';

const SOURCE_LABEL: Record<string, string> = {
  webhook_api: 'Webhook API',
  csv_upload: 'CSV Upload',
  xlsx_upload: 'XLSX Upload',
  epcis_api: 'EPCIS API',
  epcis_xml: 'EPCIS XML',
  manual: 'Manual',
  legacy_v002: 'Legacy',
};

/** Rule-evaluation outcome mapped onto the shared compliance-state vocabulary. */
const RESULT_STATE: Record<string, ComplianceState> = {
  fail: 'non-compliant',
  warn: 'at-risk',
  pass: 'compliant',
};

const FILTER_SELECT = 'h-8 w-auto max-w-[13rem] py-0 pr-8 text-small';

/** Safe 429 copy; appends the Retry-After wait only when it is a plain second count. */
function rateLimitMessage(retryAfterSeconds: number | null): string {
  if (retryAfterSeconds === null) {
    return 'Too many requests. Wait a moment before retrying.';
  }
  return `Too many requests. Wait a moment before retrying. Retry in ${retryAfterSeconds} seconds.`;
}

/** Key/value row for the record detail <dl> — label above value, hairline separated. */
function DetailRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-re-border-subtle py-2 last:border-0">
      <dt className="text-label text-re-text-muted">{term}</dt>
      <dd className="mt-0.5 text-ui text-re-text-primary">{children}</dd>
    </div>
  );
}

export default function CanonicalRecordsPage() {
  const { tenantId } = useAuth();
  const tid = tenantId || '';

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

  const pageHeader = (
    <PageHeader
      title="Canonical Records"
      description="Every record answers: what is it, where did it come from, what rules applied, what failed, what happens next"
      meta={!events.error && events.data ? <Badge>{events.data.total} total records</Badge> : undefined}
    />
  );


  if (events.error) {
    // Fixed safe copy only — the raw backend detail is never rendered.
    const loadErrorMessage = getErrorStatus(events.error) === 429
      ? rateLimitMessage(getErrorRetryAfter(events.error))
      : 'We could not load your records.';
    return (
      <PageContainer className="workspace-load-error">
        {pageHeader}
        <ErrorState
          message={loadErrorMessage}
          onRetry={() => events.refetch()}
          requestId={getErrorRequestId(events.error)}
        />
      </PageContainer>
    );
  }

  const columns: DataTableColumn<CanonicalEvent>[] = [
    {
      key: 'traceability_lot_code',
      header: 'Lot code',
      mono: true,
      width: '20rem',
      cell: (evt) => (
        <button
          type="button"
          aria-pressed={selectedEventId === evt.event_id}
          onClick={() => setSelectedEventId(
            selectedEventId === evt.event_id ? null : evt.event_id
          )}
          className="rounded-sm text-left font-mono text-re-text-primary transition-colors duration-120 hover:text-re-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring aria-pressed:text-re-brand motion-reduce:transition-none"
        >
          {evt.traceability_lot_code}
        </button>
      ),
    },
    {
      key: 'event_type',
      header: 'Event type',
      width: '11rem',
      cell: (evt) => <Badge size="sm">{evt.event_type.replace(/_/g, ' ')}</Badge>,
    },
    {
      key: 'product_reference',
      header: 'Product',
      cell: (evt) => (
        <span className="text-re-text-secondary">{evt.product_reference || 'No product ref'}</span>
      ),
    },
    {
      key: 'source_system',
      header: 'Source',
      width: '10rem',
      cell: (evt) => (
        <span className="text-re-text-tertiary">
          {SOURCE_LABEL[evt.source_system] || evt.source_system}
        </span>
      ),
    },
  ];

  return (
    <PageContainer>
      {pageHeader}

      <DemoBanner visible={!!(events.data?.__isDemo)} />

      <Section spacing="app" title="Traceability Events" className="mt-6">
        <DataTable
          caption="Canonical traceability events"
          columns={columns}
          data={records}
          minWidth="780px"
          rowKey={(evt) => evt.event_id}
          status={events.isLoading ? 'loading' : records.length === 0 ? 'empty' : 'idle'}
          empty={{
            icon: FileSearch,
            title: 'No records found',
            description: 'Adjust filters or ingest traceability events',
          }}
          toolbar={{
            search: {
              placeholder: 'Search by TLC...',
              value: tlcFilter,
              onChange: setTlcFilter,
              label: 'Search by traceability lot code',
            },
            filters: (
              <>
                <Filter className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                <label htmlFor="records-event-type-filter" className="sr-only">
                  Filter by event type
                </label>
                <select
                  id="records-event-type-filter"
                  className={cn(fieldControlClasses, FILTER_SELECT)}
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
              </>
            ),
          }}
        />
      </Section>

      {/* Detail panels sit below the table, so selecting a row never reflows it. */}
      {selectedEventId && (
        <div className="mt-8 space-y-4">
          {eventDetail.isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full" />)}
            </div>
          ) : detail ? (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Record Detail</CardTitle>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedEventId(null)}>
                    Close
                  </Button>
                </CardHeader>
                <CardContent>
                  <dl className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
                    <DetailRow term="Event Type">{detail.event_type.replace(/_/g, ' ')}</DetailRow>
                    <DetailRow term="TLC">
                      <span className="font-mono text-[0.8125rem]">{detail.traceability_lot_code}</span>
                    </DetailRow>
                    <DetailRow term="Product">{detail.product_reference || '-'}</DetailRow>
                    <DetailRow term="Quantity">{detail.quantity} {detail.unit_of_measure}</DetailRow>
                    <DetailRow term="From Facility">
                      <span className="font-mono text-[0.8125rem]">{detail.from_facility_reference || '-'}</span>
                    </DetailRow>
                    <DetailRow term="To Facility">
                      <span className="font-mono text-[0.8125rem]">{detail.to_facility_reference || '-'}</span>
                    </DetailRow>
                    <DetailRow term="Source System">
                      {SOURCE_LABEL[detail.source_system] || detail.source_system}
                    </DetailRow>
                    <DetailRow term="Confidence">{(detail.confidence_score * 100).toFixed(0)}%</DetailRow>
                    <DetailRow term="Event Timestamp">
                      {new Date(detail.event_timestamp).toLocaleString()}
                    </DetailRow>
                    <DetailRow term="Schema Version">{detail.schema_version}</DetailRow>
                  </dl>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Rule Evaluations ({detail.rule_evaluations?.length || 0})</CardTitle>
                </CardHeader>
                <CardContent>
                  {(!detail.rule_evaluations || detail.rule_evaluations.length === 0) ? (
                    <p className="text-ui text-re-text-tertiary">No evaluations recorded yet</p>
                  ) : (
                    <div className="space-y-2">
                      {detail.rule_evaluations.map((ev: RuleEvaluation, i: number) => (
                        <Card key={i} variant="inset" padding="compact">
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="flex min-w-0 items-center gap-2">
                              <StatusBadge
                                state={RESULT_STATE[ev.result] ?? 'unknown'}
                                label={ev.result}
                                size="sm"
                              />
                              <span className="text-ui font-medium text-re-text-primary">
                                {ev.rule_title}
                              </span>
                            </div>
                            {ev.citation_reference && (
                              <span className="whitespace-nowrap font-mono text-small text-re-text-tertiary">
                                {ev.citation_reference}
                              </span>
                            )}
                          </div>
                          {ev.why_failed && (
                            <p className="mt-2 text-ui text-re-danger">{ev.why_failed}</p>
                          )}
                          {ev.remediation_suggestion && ev.result !== 'pass' && (
                            <p className="mt-1 text-ui text-re-text-secondary">
                              {ev.remediation_suggestion}
                            </p>
                          )}
                        </Card>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Provenance Metadata</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="max-h-40 overflow-auto rounded-md bg-re-surface-inset p-3 font-mono text-small text-re-text-secondary">
                    {JSON.stringify(detail.provenance_metadata, null, 2)}
                  </pre>
                </CardContent>
              </Card>

              {detail.exception_cases && detail.exception_cases.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertTriangle
                        className="h-4 w-4 text-re-warning"
                        strokeWidth={1.75}
                        aria-hidden="true"
                      />
                      Linked Exceptions ({detail.exception_cases.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {detail.exception_cases.map((exc: ExceptionCase) => (
                        <div
                          key={exc.case_id}
                          className="flex flex-wrap items-center justify-between gap-2 border-b border-re-border-subtle py-2 last:border-0"
                        >
                          <div className="flex items-center gap-2">
                            <Badge tone={exc.severity === 'critical' ? 'danger' : 'warning'} size="sm">
                              {exc.severity}
                            </Badge>
                            <span className="text-ui text-re-text-secondary">{exc.status}</span>
                          </div>
                          <span className="max-w-[32ch] truncate text-small text-re-text-tertiary">
                            {exc.recommended_remediation}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : null}
        </div>
      )}
    </PageContainer>
  );
}
