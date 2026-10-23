'use client';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Search, ArrowRight, AlertTriangle } from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import type { SupplierFDAExportPreviewResponse } from '@/types/api';

/**
 * FSMA 204 Trace Page
 *
 * Queries CTE events by TLC code using the FDA export preview endpoint.
 * Derives the supply chain path from the event sequence.
 */

interface TraceFacility {
  name: string;
  cte_types: string[];
}

interface TraceEvent {
  event_id: string;
  cte_type: string;
  event_time: string;
  facility_name: string;
  quantity: string;
  unit_of_measure: string;
  payload_sha256: string;
}

interface TraceResult {
  tlc_code: string;
  product_description: string | null;
  facilities: TraceFacility[];
  events: TraceEvent[];
  total_count: number;
}

export default function TracePage() {
  const { hasTenantSession } = useAuth();

  const [tlcInput, setTlcInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [traceResult, setTraceResult] = useState<TraceResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTrace = async () => {
    const code = tlcInput.trim();
    if (!code) return;

    if (!hasTenantSession) {
      setError('Sign in to run traceability queries.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setTraceResult(null);

    const start = performance.now();

    try {
      // Query CTE events for this TLC code via FDA export preview
      const preview: SupplierFDAExportPreviewResponse = await apiClient.getSupplierFDAExportPreview(
        undefined, // no facility filter
        500,       // high limit to get all events for this TLC
        code,      // filter by TLC code
      );

      if (!preview.rows || preview.rows.length === 0) {
        setError(`No CTE events found for TLC "${code}". Check the lot code and try again.`);
        setIsLoading(false);
        return;
      }

      // Sort events by time
      const sortedEvents = [...preview.rows].sort(
        (a, b) => new Date(a.event_time).getTime() - new Date(b.event_time).getTime()
      );

      // Derive unique facilities in order of first appearance
      const facilityMap = new Map<string, string[]>();
      for (const event of sortedEvents) {
        const name = event.facility_name;
        if (!facilityMap.has(name)) {
          facilityMap.set(name, []);
        }
        const types = facilityMap.get(name)!;
        if (!types.includes(event.cte_type)) {
          types.push(event.cte_type);
        }
      }

      const facilities: TraceFacility[] = Array.from(facilityMap.entries()).map(([name, cte_types]) => ({
        name,
        cte_types,
      }));

      const events: TraceEvent[] = sortedEvents.map((row) => ({
        event_id: row.event_id,
        cte_type: row.cte_type,
        event_time: row.event_time,
        facility_name: row.facility_name,
        quantity: row.quantity,
        unit_of_measure: row.unit_of_measure,
        payload_sha256: row.payload_sha256,
      }));

      setTraceResult({
        tlc_code: code,
        product_description: sortedEvents[0]?.product_description || null,
        facilities,
        events,
        total_count: preview.total_count,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Trace query failed';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const formatCTEType = (type: string) =>
    type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const summaryStats = traceResult
    ? [
      { label: 'Facilities', value: traceResult.facilities.length },
      { label: 'CTE Events', value: traceResult.events.length },
      { label: 'Total Records', value: traceResult.total_count },
    ]
    : [];

  return (
    <PageContainer>
      <PageHeader
        title="Traceability Query"
        description="Trace products through the supply chain by Traceability Lot Code (TLC)"
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Trace Lot</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-3 md:flex-row">
              <div className="flex-1">
                <label htmlFor="trace-tlc" className="sr-only">Trace Lot</label>
                <Input
                  id="trace-tlc"
                  placeholder="Enter TLC (e.g., TLC-2026-SAL-0001)"
                  value={tlcInput}
                  onChange={(e) => setTlcInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleTrace()}
                  mono
                />
              </div>
              <Button onClick={handleTrace} disabled={!tlcInput.trim() || isLoading || !hasTenantSession}>
                {isLoading ? <Spinner size="sm" /> : 'Trace'}
              </Button>
            </div>
            {!hasTenantSession && (
              <p className="mt-2 text-small text-re-text-tertiary">Sign in to run trace queries.</p>
            )}
          </CardContent>
        </Card>

        {/* Error — the page's one alarm. `Callout` cannot be imported here:
            src/__tests__/pages/trace.test.tsx mocks lucide-react with six
            icons and vitest throws on any other icon access at import time. */}
        {error && (
          <Card
            role="alert"
            className="flex gap-3 border-l-[3px] border-l-re-danger bg-re-danger-bg px-4 py-3 text-ui text-re-text-secondary"
          >
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0 text-re-danger"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <p className="min-w-0 flex-1">{error}</p>
          </Card>
        )}

        {isLoading && (
          <div className="space-y-6" aria-busy="true">
            <Card>
              <CardContent className="space-y-4">
                <Skeleton className="h-5 w-48" />
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <Skeleton className="h-20 w-full" />
                  <Skeleton className="h-20 w-full" />
                  <Skeleton className="h-20 w-full" />
                </div>
                <Skeleton className="h-12 w-full" />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="space-y-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </CardContent>
            </Card>
          </div>
        )}

        {!isLoading && !traceResult && !error && (
          <EmptyState
            icon={Search}
            title="Enter a Traceability Lot Code (TLC) to view its CTE event chain"
          />
        )}

        {traceResult && (
          <div className="space-y-6">
            {/* Summary */}
            <Card>
              <CardHeader className="flex-col items-stretch sm:flex-row sm:items-start">
                <div className="min-w-0">
                  <CardTitle>Trace Results</CardTitle>
                  <CardDescription className="mt-1">
                    <span className="font-mono text-[0.8125rem]">{traceResult.tlc_code}</span>
                    {traceResult.product_description && (
                      <span className="ml-2 text-re-text-secondary">({traceResult.product_description})</span>
                    )}
                  </CardDescription>
                </div>
                <Badge className="w-fit shrink-0">
                  {traceResult.total_count} event{traceResult.total_count !== 1 ? 's' : ''}
                </Badge>
              </CardHeader>
              <CardContent>
                <dl className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
                  {summaryStats.map((stat) => (
                    <Card key={stat.label} variant="inset" padding="compact">
                      <dt className="text-label text-re-text-muted">{stat.label}</dt>
                      <dd className="mt-2 text-title tabular-nums text-re-text-primary">{stat.value}</dd>
                    </Card>
                  ))}
                </dl>

                {/* Facility Chain */}
                <h4 className="mb-3 text-ui font-medium text-re-text-primary">Supply Chain Path</h4>
                <div className="flex flex-wrap items-center gap-2">
                  {traceResult.facilities.map((facility, index) => (
                    <div key={facility.name} className="flex items-center gap-2">
                      <div className="rounded-md border border-re-border bg-re-surface-card px-3 py-2">
                        <p className="text-ui font-medium text-re-text-primary">{facility.name}</p>
                        <p className="text-small text-re-text-tertiary">
                          {facility.cte_types.map(formatCTEType).join(', ')}
                        </p>
                      </div>
                      {index < traceResult.facilities.length - 1 && (
                        <ArrowRight
                          className="h-4 w-4 text-re-text-muted"
                          strokeWidth={1.75}
                          aria-hidden="true"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Events Timeline */}
            <Card>
              <CardHeader>
                <div className="min-w-0">
                  <CardTitle>CTE Event Timeline</CardTitle>
                  <CardDescription className="mt-1">
                    Each event is cryptographically hashed (SHA-256) for tamper-evident traceability
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <ul className="divide-y divide-re-border-subtle">
                  {traceResult.events.map((event) => (
                    <li key={event.event_id} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-start sm:gap-4">
                      <Badge
                        variant={
                          event.cte_type.includes('shipping')
                            ? 'default'
                            : event.cte_type.includes('receiving')
                              ? 'secondary'
                              : event.cte_type.includes('transform')
                                ? 'outline'
                                : 'default'
                        }
                        size="sm"
                        className="w-fit shrink-0 sm:mt-0.5 sm:w-36 sm:justify-center"
                      >
                        {formatCTEType(event.cte_type)}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <p className="text-ui font-medium text-re-text-primary">{event.facility_name}</p>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-small text-re-text-tertiary">
                          <span>{formatDate(event.event_time)}</span>
                          {event.quantity && event.unit_of_measure && (
                            <span className="tabular-nums">{event.quantity} {event.unit_of_measure}</span>
                          )}
                        </div>
                        <p className="mt-1 truncate font-mono text-[0.8125rem] text-re-text-tertiary">
                          SHA-256: {event.payload_sha256}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </PageContainer>
  );
}
