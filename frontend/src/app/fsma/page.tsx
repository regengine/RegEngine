'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import DashboardLayout from '../dashboard/layout';
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
// Hooks
import { useAuth } from '@/lib/auth-context';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import {
  useFSMADashboard,
  useRecallDrills,
  useRecallReadiness,
  useForwardTrace,
  useMassBalance,
  useCreateRecallDrill,
  useExportTrace,
  useExportComplianceReport,
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
} from 'lucide-react';

// Empty state shown before a trace is run
const EMPTY_FACILITIES: Facility[] = [];

export default function FSMADashboardPage() {
  if (!experimentalFeaturesEnabled()) {
    return (
      <DashboardLayout>
        <FeatureNotEnabled
          featureName="FSMA readiness dashboard"
          backHref="/dashboard"
          backLabel="Back to dashboard"
        />
      </DashboardLayout>
    );
  }
  return <FSMADashboardContent />;
}

function FSMADashboardContent() {
  const { isAuthenticated } = useAuth();
  const [tlcQuery, setTlcQuery] = useState('');
  const [activeTlc, setActiveTlc] = useState<string | null>(null);
  const [selectedFacility, setSelectedFacility] = useState<Facility | null>(null);

  // API hooks
  const dashboard = useFSMADashboard();
  const recallDrills = useRecallDrills();
  const readiness = useRecallReadiness();
  const createDrill = useCreateRecallDrill();
  const exportTrace = useExportTrace();
  const exportCompliance = useExportComplianceReport();

  // Trace query (only when activeTlc is set)
  const traceResult = useForwardTrace(activeTlc || '', !!activeTlc && isAuthenticated);
  const massBalance = useMassBalance(activeTlc || '', !!activeTlc && isAuthenticated);

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
      if (process.env.NODE_ENV !== 'production') {
        console.error('Failed to start drill:', error);
      }
    }
  };

  // Get active drill if any
  const activeDrill = recallDrills.data?.drills?.find(
    d => d.status === 'IN_PROGRESS' || d.status === 'PENDING'
  );

  return (
    <DashboardLayout>
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
              <div className="p-3 rounded-lg bg-re-brand-muted dark:bg-re-brand">
                <Shield className="h-8 w-8 text-re-brand-dark dark:text-re-brand" />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-4xl font-bold">FSMA 204 Dashboard</h1>
                  <Badge className="bg-re-brand-muted text-re-brand-dark border border-re-brand/20 text-xs">Supported</Badge>
                </div>
                <div className="mt-1 flex items-center gap-1 text-muted-foreground">
                  <p>Food Safety Traceability & Recall Management</p>
                  <HelpTooltip content="FDA Food Safety Modernization Act Section 204 (21 CFR Part 1, Subpart S) requires covered persons to maintain traceability records and provide a sortable electronic spreadsheet of those records within 24 hours of an official FDA request, per §1.1455(c)." />
                </div>
              </div>
            </div>

            {/* System Status */}
            <div className="flex items-center gap-2">
              {dashboard.data?.system_health === 'HEALTHY' ? (
                <Badge className="bg-re-success-muted text-re-success">
                  <Activity className="w-3 h-3 mr-1" />
                  All Systems Operational
                </Badge>
              ) : dashboard.data?.system_health === 'DEGRADED' ? (
                <Badge className="bg-re-warning-muted text-re-warning">
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

          {/* Auth warning */}
          {!isAuthenticated && (
            <Card className="border-re-warning dark:border-re-warning bg-re-warning-muted dark:bg-re-warning/20">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <Key className="h-5 w-5 text-re-warning dark:text-re-warning mt-0.5" />
                  <div className="flex-1">
                    <p className="font-medium text-re-warning dark:text-re-warning">
                      Sign in to unlock live FSMA data
                    </p>
                    <p className="text-sm text-re-warning dark:text-re-warning mt-1">
                      Cookie-backed session auth now powers the live FSMA dashboard. Until you sign in,
                      demo visualization is shown below.
                    </p>
                    <Link href="/login?next=/fsma">
                      <Button size="sm" variant="outline" className="mt-3">
                        Sign In
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
                  <Package className="h-8 w-8 text-re-info" />
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
                  <TrendingUp className="h-8 w-8 text-re-success" />
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
                  <Bell className={`h-8 w-8 ${dashboard.data?.active_recalls ? 'text-re-danger' : 'text-muted-foreground'}`} />
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
                      facilities={traceResult.data?.facilities || EMPTY_FACILITIES}
                      events={traceResult.data?.events}
                      highlightedFacility={selectedFacility?.gln}
                      onFacilityClick={setSelectedFacility}
                      onExport={activeTlc ? () => exportTrace.mutate({ tlc: activeTlc, direction: 'forward' }) : undefined}
                      animated
                    />
                  )}

                  {/* Trace Statistics */}
                  {traceResult.data && (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-6 pt-4 border-t">
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

              {/* Recent Alerts */}
              {dashboard.data?.recent_alerts && dashboard.data.recent_alerts.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-re-warning" />
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
                            <XCircle className="w-4 h-4 text-re-danger mt-0.5" />
                          ) : alert.severity === 'WARNING' ? (
                            <AlertTriangle className="w-4 h-4 text-re-warning mt-0.5" />
                          ) : (
                            <CheckCircle className="w-4 h-4 text-re-info mt-0.5" />
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
                    <Button variant="default" className="w-full justify-start bg-re-brand hover:bg-re-brand-dark">
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Readiness Assessment
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
    </DashboardLayout>
  );
}
