'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { Search, ArrowRight, MapPin, Calendar, Package, AlertTriangle } from 'lucide-react';

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
  const { apiKey } = useAuth();
  const isLoggedIn = Boolean(apiKey);

  const [tlcInput, setTlcInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [traceResult, setTraceResult] = useState<TraceResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTrace = async () => {
    const code = tlcInput.trim();
    if (!code) return;

    if (!isLoggedIn) {
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

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {/* Page Header */}
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900">
              <Search className="h-8 w-8 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">Traceability Query</h1>
              <p className="text-muted-foreground mt-1">
                Trace products through the supply chain by Traceability Lot Code (TLC)
              </p>
            </div>
          </div>

          {/* Search Card */}
          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Trace Lot</CardTitle>
              <CardDescription>
                Enter a Traceability Lot Code (TLC) to view its CTE event chain
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1">
                  <Input
                    placeholder="Enter TLC (e.g., TLC-2026-SAL-0001)"
                    value={tlcInput}
                    onChange={(e) => setTlcInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleTrace()}
                    className="font-mono"
                  />
                </div>
                <Button onClick={handleTrace} disabled={!tlcInput.trim() || isLoading || !isLoggedIn}>
                  {isLoading ? <Spinner size="sm" /> : 'Trace'}
                </Button>
              </div>
              {!isLoggedIn && (
                <p className="text-xs text-muted-foreground mt-2">Sign in to run trace queries.</p>
              )}
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <Card className="mb-8 border-orange-300 dark:border-orange-700">
                <CardContent className="py-4">
                  <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                    <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                    <p className="text-sm">{error}</p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Results */}
          {traceResult && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Summary */}
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Trace Results</CardTitle>
                    <Badge variant="secondary">
                      {traceResult.total_count} event{traceResult.total_count !== 1 ? 's' : ''}
                    </Badge>
                  </div>
                  <CardDescription>
                    <span className="font-mono">{traceResult.tlc_code}</span>
                    {traceResult.product_description && (
                      <span className="ml-2 text-foreground">— {traceResult.product_description}</span>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                      <MapPin className="h-8 w-8 text-primary" />
                      <div>
                        <p className="text-2xl font-bold">{traceResult.facilities.length}</p>
                        <p className="text-sm text-muted-foreground">Facilities</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                      <Calendar className="h-8 w-8 text-primary" />
                      <div>
                        <p className="text-2xl font-bold">{traceResult.events.length}</p>
                        <p className="text-sm text-muted-foreground">CTE Events</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                      <Package className="h-8 w-8 text-primary" />
                      <div>
                        <p className="text-2xl font-bold">{traceResult.total_count}</p>
                        <p className="text-sm text-muted-foreground">Total Records</p>
                      </div>
                    </div>
                  </div>

                  {/* Facility Chain */}
                  <h4 className="font-medium mb-4">Supply Chain Path</h4>
                  <div className="flex flex-wrap items-center gap-2">
                    {traceResult.facilities.map((facility, index) => (
                      <div key={facility.name} className="flex items-center gap-2">
                        <div className="px-3 py-2 rounded-lg border bg-background">
                          <p className="font-medium text-sm">{facility.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {facility.cte_types.map(formatCTEType).join(', ')}
                          </p>
                        </div>
                        {index < traceResult.facilities.length - 1 && (
                          <ArrowRight className="h-4 w-4 text-muted-foreground" />
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Events Timeline */}
              <Card>
                <CardHeader>
                  <CardTitle>CTE Event Timeline</CardTitle>
                  <CardDescription>
                    Each event is cryptographically hashed (SHA-256) for tamper-evident traceability
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {traceResult.events.map((event) => (
                      <div
                        key={event.event_id}
                        className="flex items-start gap-4 p-3 rounded-lg border"
                      >
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
                          className="mt-0.5 flex-shrink-0"
                        >
                          {formatCTEType(event.cte_type)}
                        </Badge>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm">{event.facility_name}</p>
                          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground mt-1">
                            <span>{formatDate(event.event_time)}</span>
                            {event.quantity && event.unit_of_measure && (
                              <span>{event.quantity} {event.unit_of_measure}</span>
                            )}
                          </div>
                          <p className="text-[10px] font-mono text-muted-foreground mt-1 truncate">
                            SHA-256: {event.payload_sha256}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </motion.div>
      </PageContainer>
    </div>
  );
}
