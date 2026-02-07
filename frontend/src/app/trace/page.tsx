'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { Search, ArrowRight, MapPin, Calendar, Package } from 'lucide-react';

/**
 * FSMA 204 Trace Page
 * 
 * Placeholder UI for forward/backward traceability queries.
 * This page will integrate with the backend trace API.
 */
export default function TracePage() {
  const [tlcInput, setTlcInput] = useState('');
  const [traceDirection, setTraceDirection] = useState<'forward' | 'backward'>('forward');
  const [isLoading, setIsLoading] = useState(false);
  const [traceResult, setTraceResult] = useState<any>(null);

  const handleTrace = async () => {
    if (!tlcInput.trim()) return;

    setIsLoading(true);

    // Simulate API call - in production, this would call the trace API
    setTimeout(() => {
      setTraceResult({
        lot_id: tlcInput,
        direction: traceDirection,
        facilities: [
          { gln: '1234567890123', name: 'Fresh Farms', type: 'FARM' },
          { gln: '2345678901234', name: 'Sunshine Packing', type: 'PROCESSOR' },
          { gln: '3456789012345', name: 'Metro Distribution', type: 'DISTRIBUTOR' },
          { gln: '4567890123456', name: 'City Grocery Store', type: 'RETAILER' },
        ],
        events: [
          { type: 'CREATION', date: '2025-11-01', facility: 'Fresh Farms' },
          { type: 'SHIPPING', date: '2025-11-02', facility: 'Fresh Farms' },
          { type: 'RECEIVING', date: '2025-11-02', facility: 'Sunshine Packing' },
          { type: 'TRANSFORMATION', date: '2025-11-03', facility: 'Sunshine Packing' },
          { type: 'SHIPPING', date: '2025-11-04', facility: 'Sunshine Packing' },
          { type: 'RECEIVING', date: '2025-11-04', facility: 'Metro Distribution' },
          { type: 'SHIPPING', date: '2025-11-05', facility: 'Metro Distribution' },
          { type: 'RECEIVING', date: '2025-11-05', facility: 'City Grocery Store' },
        ],
        query_time_ms: 45.2,
        total_quantity: 500,
      });
      setIsLoading(false);
    }, 1000);
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
                Trace products forward or backward through the supply chain
              </p>
            </div>
          </div>

          {/* Search Card */}
          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Trace Lot</CardTitle>
              <CardDescription>
                Enter a Traceability Lot Code (TLC) to trace its path through the supply chain
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1">
                  <Input
                    placeholder="Enter TLC (e.g., 00012345678901-LOT-2025-A)"
                    value={tlcInput}
                    onChange={(e) => setTlcInput(e.target.value)}
                    className="font-mono"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    variant={traceDirection === 'forward' ? 'default' : 'outline'}
                    onClick={() => setTraceDirection('forward')}
                  >
                    Forward
                  </Button>
                  <Button
                    variant={traceDirection === 'backward' ? 'default' : 'outline'}
                    onClick={() => setTraceDirection('backward')}
                  >
                    Backward
                  </Button>
                </div>
                <Button onClick={handleTrace} disabled={!tlcInput.trim() || isLoading}>
                  {isLoading ? <Spinner size="sm" /> : 'Trace'}
                </Button>
              </div>
            </CardContent>
          </Card>

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
                      {traceResult.query_time_ms}ms
                    </Badge>
                  </div>
                  <CardDescription>
                    {traceResult.direction === 'forward' ? 'Forward' : 'Backward'} trace for {traceResult.lot_id}
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
                        <p className="text-sm text-muted-foreground">Events</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                      <Package className="h-8 w-8 text-primary" />
                      <div>
                        <p className="text-2xl font-bold">{traceResult.total_quantity}</p>
                        <p className="text-sm text-muted-foreground">Units</p>
                      </div>
                    </div>
                  </div>

                  {/* Facility Chain */}
                  <h4 className="font-medium mb-4">Supply Chain Path</h4>
                  <div className="flex flex-wrap items-center gap-2">
                    {traceResult.facilities.map((facility: any, index: number) => (
                      <div key={facility.gln} className="flex items-center gap-2">
                        <div className="px-3 py-2 rounded-lg border bg-background">
                          <p className="font-medium text-sm">{facility.name}</p>
                          <p className="text-xs text-muted-foreground">{facility.type}</p>
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
                  <CardTitle>Event Timeline</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {traceResult.events.map((event: any, index: number) => (
                      <div
                        key={index}
                        className="flex items-center gap-4 p-3 rounded-lg border"
                      >
                        <Badge
                          variant={
                            event.type === 'SHIPPING'
                              ? 'default'
                              : event.type === 'RECEIVING'
                                ? 'secondary'
                                : event.type === 'TRANSFORMATION'
                                  ? 'outline'
                                  : 'default'
                          }
                        >
                          {event.type}
                        </Badge>
                        <div>
                          <p className="font-medium text-sm">{event.facility}</p>
                          <p className="text-xs text-muted-foreground">{event.date}</p>
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
