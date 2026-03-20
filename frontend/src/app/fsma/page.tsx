'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { HelpTooltip } from '@/components/ui/tooltip';

// FSMA Components
import { SupplyChainGraph, MiniSupplyChain, FacilityCard } from '@/components/fsma/supply-chain-graph';
import { RecallTimer, SLAGauge } from '@/components/fsma/recall-timer';
import { MassBalanceWidget } from '@/components/fsma/mass-balance-widget';

import { ComplianceReadiness } from '@/components/fsma/compliance-readiness';
import { DriftAlertsWidget } from '@/components/fsma/drift-alerts';

// Hooks
import { useAuth } from '@/lib/auth-context';
import {
  useFSMADashboard,
  useRecallDrills,
  useRecallReadiness,
  useForwardTrace,
  useMassBalance,
  useCreateRecallDrill,
  useExportTrace,
  useExportComplianceReport,
  useSupplierHealth,
} from '@/hooks/use-fsma';

// Types
import type { Facility, RecallDrillType } from '@/types/fsma';

import {
  Shield,
  Search,
  AlertTriangle,
  Clock,
  Activity,
  TrendingUp,
  Bell,
  Package,
  MapPin,
  ArrowRight,
  PlayCircle,
  Key,
  RefreshCw,
  CheckCircle,
  XCircle,
  Building2,
} from 'lucide-react';

// Demo facilities for visualization when no API
const DEMO_FACILITIES: Facility[] = [
  { gln: '1234567890123', name: 'Fresh Farms', type: 'FARM' },
  { gln: '2345678901234', name: 'Sunshine Packing', type: 'PROCESSOR' },
  { gln: '3456789012345', name: 'Metro Distribution', type: 'DISTRIBUTOR' },
  { gln: '4567890123456', name: 'City Grocery', type: 'RETAILER' },
];

export default function FSMADashboardPage() {
  const { apiKey } = useAuth();
  const [tlcQuery, setTlcQuery] = useState('');
  const [activeTlc, setActiveTlc] = useState<string | null>(null);
  const [selectedFacility, setSelectedFacility] = useState<Facility | null>(null);

  // API hooks
  const dashboard = useFSMADashboard(apiKey || '');
  const recallDrills = useRecallDrills(apiKey || '');
  const readiness = useRecallReadiness(apiKey || '');
  const createDrill = useCreateRecallDrill(apiKey || '');
  const exportTrace = useExportTrace(apiKey || '');
  const exportCompliance = useExportComplianceReport(apiKey || '');
  const supplierHealth = useSupplierHealth(apiKey || '');

  // Trace query (only when activeTlc is set)
  const traceResult = useForwardTrace(activeTlc || '', apiKey || '', !!activeTlc && !!apiKey);
  const massBalance = useMassBalance(activeTlc || '', apiKey || '', !!activeTlc && !!apiKey);

  const handleTrace = () => {
    if (tlcQuery.trim()) {
      setActiveTlc(tlcQuery.trim());
    }
  };

  const handleStartDrill = async (type: RecallDrillType = 'FORWARD', fallbackTlc = 'TLC1001') => {
    const tlc = activeTlc || fallbackTlc;
    try {
      await createDrill.mutateAsync({
        type,
        target_tlc: tlc,
        reason: 'Mock drill initiated from dashboard',
      });
    } catch (error) {
      console.error('Failed to start drill:', error);
    }
  };

  // Get active drill if any
  const activeDrill = recallDrills.data?.drills?.find(
    d => d.status === 'IN_PROGRESS' || d.status === 'PENDING'
  );

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-lg bg-emerald-100 dark:bg-emerald-900">
                <Shield className="h-8 w-8 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-4xl font-bold">FSMA 204 Dashboard</h1>
                  <Badge className="bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 text-xs">GA</Badge>
                </div>
                <p className="text-muted-foreground mt-1">
                  Food Safety Traceability & Recall Management
                  <HelpTooltip content="FDA Food Safety Modernization Act Section 204 requires food facilities to maintain traceability records and respond to recalls within 24 hours." />
                </p>
              </div>
            </div>

            {/* System Status */}
            <div className="flex items-center gap-2">
              {dashboard.data?.system_health === 'HEALTHY' ? (
                <Badge className="bg-green-100 text-green-700">
                  <Activity className="w-3 h-3 mr-1" />
                  All Systems Operational
                </Badge>
              ) : dashboard.data?.system_health === 'DEGRADED' ? (
                <Badge className="bg-amber-100 text-amber-700">
                  <AlertTriangle className="w-3 h-3 mr-1" />
                  Degraded Performance
                </Badge>
              ) : (
                <Badge variant="secondary">
                  <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                  Checking...
                </Badge>
              )}
            </div>
          </div>

          {/* No API Key Warning */}
          {!apiKey && (
            <Card className="border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <Key className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5" />
                  <div className="flex-1">
                    <p className="font-medium text-amber-900 dark:text-amber-100">
                      API Key Required for Full Functionality
                    </p>
                    <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                      Connect to the FSMA backend to access real traceability data and recall drills.
                      Demo visualization is shown below.
                    </p>
                    <Link href="/onboarding">
                      <Button size="sm" variant="outline" className="mt-3">
                        Setup API Key
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </Button>
                    </Link>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <Package className="h-8 w-8 text-blue-500" />
                  <div>
                    <p className="text-2xl font-bold">
                      {dashboard.data?.total_lots?.toLocaleString() || '—'}
                    </p>
                    <p className="text-sm text-muted-foreground">Total Lots</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <MapPin className="h-8 w-8 text-purple-500" />
                  <div>
                    <p className="text-2xl font-bold">
                      {dashboard.data?.total_facilities?.toLocaleString() || '—'}
                    </p>
                    <p className="text-sm text-muted-foreground">Facilities</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <TrendingUp className="h-8 w-8 text-green-500" />
                  <div>
                    <p className="text-2xl font-bold">
                      {dashboard.data?.kde_completeness_percent
                        ? `${dashboard.data.kde_completeness_percent}%`
                        : '—'}
                    </p>
                    <p className="text-sm text-muted-foreground">KDE Complete</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                  <Bell className={`h-8 w-8 ${dashboard.data?.active_recalls ? 'text-red-500' : 'text-muted-foreground'}`} />
                  <div>
                    <p className="text-2xl font-bold">
                      {dashboard.data?.active_recalls ?? '0'}
                    </p>
                    <p className="text-sm text-muted-foreground">Active Recalls</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column - Traceability Query */}
            <div className="lg:col-span-2 space-y-6">
              {/* Trace Query */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Search className="w-5 h-5" />
                    Traceability Query
                  </CardTitle>
                  <CardDescription>
                    Enter a Traceability Lot Code (TLC) to trace through the supply chain
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Enter TLC (e.g., LOT-2025-001)"
                      value={tlcQuery}
                      onChange={(e) => setTlcQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleTrace()}
                      className="font-mono"
                    />
                    <Button onClick={handleTrace} disabled={!tlcQuery.trim()}>
                      <Search className="w-4 h-4 mr-2" />
                      Trace
                    </Button>
                  </div>

                  {/* Demo Facilities Hint */}
                  {!activeTlc && (
                    <p className="text-sm text-muted-foreground">
                      Try: <code className="bg-muted px-1 rounded">LOT-2025-ROMAINE-001</code> or{' '}
                      <code className="bg-muted px-1 rounded">TLC-LETTUCE-BATCH-42</code>
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Supply Chain Visualization */}
              <Card>
                <CardHeader>
                  <CardTitle>Supply Chain Path</CardTitle>
                  <CardDescription>
                    {activeTlc
                      ? `Tracing: ${activeTlc}`
                      : 'Visual representation of the supply chain flow'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {traceResult.isLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <RefreshCw className="w-8 h-8 animate-spin text-muted-foreground" />
                    </div>
                  ) : (
                    <SupplyChainGraph
                      facilities={traceResult.data?.facilities || DEMO_FACILITIES}
                      events={traceResult.data?.events}
                      highlightedFacility={selectedFacility?.gln}
                      onFacilityClick={setSelectedFacility}
                      onExport={activeTlc ? () => exportTrace.mutate({ tlc: activeTlc, direction: 'forward' }) : undefined}
                      animated
                    />
                  )}

                  {/* Trace Statistics */}
                  {traceResult.data && (
                    <div className="grid grid-cols-3 gap-4 mt-6 pt-4 border-t">
                      <div className="text-center">
                        <p className="text-xl font-bold">{traceResult.data.total_facilities}</p>
                        <p className="text-xs text-muted-foreground">Facilities</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xl font-bold">{traceResult.data.total_events}</p>
                        <p className="text-xs text-muted-foreground">Events</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xl font-bold">{traceResult.data.query_time_ms}ms</p>
                        <p className="text-xs text-muted-foreground">Query Time</p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Mass Balance Widget */}
              {activeTlc && (
                <MassBalanceWidget
                  result={massBalance.data}
                  isLoading={massBalance.isLoading}
                />
              )}

              {/* Selected Facility Details */}
              {selectedFacility && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <FacilityCard
                    facility={selectedFacility}
                    events={traceResult.data?.events?.filter(e => e.facility_gln === selectedFacility.gln)}
                    isSelected
                    onClick={() => setSelectedFacility(null)}
                  />
                </motion.div>
              )}
            </div>

            {/* Right Column - Recall & Readiness */}
            <div className="space-y-6">
              {/* Active Recall Timer */}
              <RecallTimer
                drill={activeDrill}
                onCancel={() => { recallDrills.refetch(); }}
                onComplete={() => { recallDrills.refetch(); }}
                onStartDrill={() => handleStartDrill('FORWARD')}
              />

              {/* Compliance Readiness */}
              <ComplianceReadiness
                readiness={readiness.data}
                isLoading={readiness.isLoading}
                onStartDrill={activeTlc ? () => handleStartDrill('FORWARD') : undefined}
                onExportReport={() => exportCompliance.mutate()}
              />

              {/* Supplier Data Quality */}
              {supplierHealth.data?.suppliers && supplierHealth.data.suppliers.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-purple-500" />
                      Supplier Data Quality
                    </CardTitle>
                    <CardDescription>KDE completeness by supplier</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {supplierHealth.data.suppliers.slice(0, 5).map((supplier: { gln: string; name?: string; completeness_rate?: number; alert_count?: number }) => (
                        <div key={supplier.gln} className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{supplier.name || supplier.gln}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all ${
                                    (supplier.completeness_rate || 0) >= 90 ? 'bg-green-500' :
                                    (supplier.completeness_rate || 0) >= 70 ? 'bg-amber-500' : 'bg-red-500'
                                  } ${
                                    (supplier.completeness_rate || 0) >= 95 ? 'w-[95%]' :
                                    (supplier.completeness_rate || 0) >= 90 ? 'w-[90%]' :
                                    (supplier.completeness_rate || 0) >= 80 ? 'w-4/5' :
                                    (supplier.completeness_rate || 0) >= 70 ? 'w-[70%]' :
                                    (supplier.completeness_rate || 0) >= 50 ? 'w-1/2' :
                                    (supplier.completeness_rate || 0) >= 25 ? 'w-1/4' : 'w-[10%]'
                                  }`}
                                />
                              </div>
                              <span className="text-xs text-muted-foreground w-10 text-right">
                                {Math.round(supplier.completeness_rate || 0)}%
                              </span>
                            </div>
                          </div>
                          {(supplier.alert_count || 0) > 0 && (
                            <Badge variant="secondary" className="ml-2 text-xs">
                              {supplier.alert_count} alert{supplier.alert_count !== 1 ? 's' : ''}
                            </Badge>
                          )}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Drift Alerts Widget */}
              <DriftAlertsWidget />

              {/* Recent Alerts */}
              {dashboard.data?.recent_alerts && dashboard.data.recent_alerts.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-500" />
                      Recent Alerts
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {dashboard.data.recent_alerts.slice(0, 5).map((alert) => (
                        <div
                          key={alert.id}
                          className="flex items-start gap-2 p-2 rounded bg-muted/50 text-sm"
                        >
                          {alert.severity === 'CRITICAL' ? (
                            <XCircle className="w-4 h-4 text-red-500 mt-0.5" />
                          ) : alert.severity === 'WARNING' ? (
                            <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5" />
                          ) : (
                            <CheckCircle className="w-4 h-4 text-blue-500 mt-0.5" />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="truncate">{alert.message}</p>
                            <p className="text-xs text-muted-foreground">{alert.source}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Quick Actions */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">Quick Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Link href="/fsma/assessment">
                    <Button variant="default" className="w-full justify-start bg-emerald-600 hover:bg-emerald-700">
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Readiness Assessment
                    </Button>
                  </Link>
                  <Link href="/fsma/market">
                    <Button variant="outline" className="w-full justify-start">
                      <Building2 className="w-4 h-4 mr-2" />
                      Browse Target Market
                    </Button>
                  </Link>
                  <Link href="/fsma/integration">
                    <Button variant="outline" className="w-full justify-start">
                      <ArrowRight className="w-4 h-4 mr-2" />
                      Integration Blueprint
                    </Button>
                  </Link>
                  <Link href="/trace">
                    <Button variant="outline" className="w-full justify-start">
                      <Search className="w-4 h-4 mr-2" />
                      Advanced Trace Query
                    </Button>
                  </Link>
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => activeTlc && handleStartDrill('BACKWARD')}
                    disabled={!activeTlc}
                  >
                    <PlayCircle className="w-4 h-4 mr-2" />
                    Start Backward Drill
                  </Button>
                  <Link href="/compliance">
                    <Button variant="outline" className="w-full justify-start">
                      <Shield className="w-4 h-4 mr-2" />
                      View Compliance Checklists
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            </div>
          </div>
        </motion.div>
      </PageContainer>
    </div>
  );
}
