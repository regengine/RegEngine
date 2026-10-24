'use client';

import { useState } from 'react';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import DashboardLayout from '../dashboard/layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge } from '@/components/ui/status-badge';
import { HelpTooltip } from '@/components/ui/tooltip';

// FSMA Components
import { SupplyChainGraph, FacilityCard } from '@/components/fsma/supply-chain-graph';
import { RecallTimer } from '@/components/fsma/recall-timer';
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
  ArrowRight,
  PlayCircle,
  Key,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { NO_DATA_YET } from '@/lib/empty-values';

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

  const handleStartDrill = async (type: RecallDrillType = 'FORWARD') => {
    const tlc = activeTlc;
    if (!tlc) return;
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
      <PageContainer>
        <PageHeader
          title="FSMA 204 Dashboard"
          description={
            <span className="inline-flex items-start gap-1">
              Food Safety Traceability &amp; Recall Management
              <HelpTooltip content="FDA Food Safety Modernization Act Section 204 (21 CFR Part 1, Subpart S) requires covered persons to maintain traceability records and provide a sortable electronic spreadsheet of those records within 24 hours of an official FDA request, per §1.1455(c)." />
            </span>
          }
          meta={
            <>
              <Badge tone="neutral" size="sm">Supported</Badge>
              {/* System Status */}
              {dashboard.data?.system_health === 'HEALTHY' ? (
                <StatusBadge state="compliant" label="All Systems Operational" size="sm" />
              ) : dashboard.data?.system_health === 'DEGRADED' ? (
                <StatusBadge state="at-risk" label="Degraded Performance" size="sm" />
              ) : (
                <StatusBadge state="in-progress" label="Checking..." size="sm" />
              )}
            </>
          }
        />

        <div className="space-y-6">
          {/* Auth warning */}
          {!isAuthenticated && (
            <Callout
              tone="warning"
              icon={Key}
              title="Sign in to unlock live FSMA data"
              action={
                <Button size="sm" variant="secondary" asChild>
                  <Link href="/login?next=/fsma">
                    Sign In
                    <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                  </Link>
                </Button>
              }
            >
              Cookie-backed session auth powers the live FSMA dashboard. Sign in to see
              your live facilities, lots, and recall readiness below.
            </Callout>
          )}

          {/* Quick Stats */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatTile
              label="Total Lots"
              loading={dashboard.isLoading}
              value={dashboard.data?.total_lots?.toLocaleString() || NO_DATA_YET}
            />
            <StatTile
              label="Facilities"
              loading={dashboard.isLoading}
              value={dashboard.data?.total_facilities?.toLocaleString() || NO_DATA_YET}
            />
            <StatTile
              label="KDE Complete"
              loading={dashboard.isLoading}
              value={
                dashboard.data?.kde_completeness_percent
                  ? `${dashboard.data.kde_completeness_percent}%`
                  : NO_DATA_YET
              }
            />
            <StatTile
              label="Active Recalls"
              loading={dashboard.isLoading}
              value={dashboard.data?.active_recalls ?? '0'}
            />
          </div>

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Left Column - Traceability Query */}
            <div className="space-y-6 lg:col-span-2">
              {/* Trace Query */}
              <Card>
                <CardHeader className="flex-col items-stretch gap-1">
                  <CardTitle className="flex items-center gap-2">
                    <Search className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    Traceability Query
                  </CardTitle>
                  <CardDescription>
                    Enter a Traceability Lot Code (TLC) to trace through the supply chain
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex gap-2">
                    <label htmlFor="fsma-tlc-query" className="sr-only">
                      Traceability Lot Code (TLC)
                    </label>
                    <Input
                      id="fsma-tlc-query"
                      mono
                      placeholder="Enter TLC (e.g., LOT-2025-001)"
                      value={tlcQuery}
                      onChange={(e) => setTlcQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleTrace()}
                    />
                    <Button onClick={handleTrace} disabled={!tlcQuery.trim()}>
                      <Search className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Trace
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Supply Chain Visualization */}
              <Card>
                <CardHeader className="flex-col items-stretch gap-1">
                  <CardTitle>Supply Chain Path</CardTitle>
                  <CardDescription>
                    {activeTlc
                      ? `Tracing: ${activeTlc}`
                      : 'Visual representation of the supply chain flow'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {traceResult.isLoading ? (
                    <div className="flex items-center gap-4 py-12" aria-busy="true">
                      <Skeleton className="h-16 w-16 rounded-lg" />
                      <Skeleton className="h-16 w-16 rounded-lg" />
                      <Skeleton className="h-16 w-16 rounded-lg" />
                      <Skeleton className="h-16 w-16 rounded-lg" />
                    </div>
                  ) : traceResult.isError ? (
                    <Callout tone="danger" role="alert" icon={AlertTriangle}>
                      Couldn&apos;t trace that lot code. Check your connection and retry.
                    </Callout>
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

                  {!traceResult.isLoading && !traceResult.isError && !traceResult.data?.facilities?.length && (
                    <EmptyState
                      bare
                      size="sm"
                      icon={Shield}
                      title="No supply chain data connected yet"
                      description="Import your facilities and lots, then run a traceability query to draw the chain for a lot code."
                      action={
                        <Button variant="secondary" size="sm" asChild>
                          <Link href="/tools/data-import">
                            Import data
                            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                          </Link>
                        </Button>
                      }
                    />
                  )}

                  {/* Trace Statistics */}
                  {traceResult.data && (
                    <div className="mt-6 grid grid-cols-1 gap-4 border-t border-re-border-subtle pt-4 sm:grid-cols-3">
                      <div>
                        <p className="text-label text-re-text-muted">Facilities</p>
                        <p className="mt-1 text-title tabular-nums text-re-text-primary">{traceResult.data.total_facilities}</p>
                      </div>
                      <div>
                        <p className="text-label text-re-text-muted">Events</p>
                        <p className="mt-1 text-title tabular-nums text-re-text-primary">{traceResult.data.total_events}</p>
                      </div>
                      <div>
                        <p className="text-label text-re-text-muted">Query Time</p>
                        <p className="mt-1 text-title tabular-nums text-re-text-primary">{traceResult.data.query_time_ms}ms</p>
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
                <FacilityCard
                  facility={selectedFacility}
                  events={traceResult.data?.events?.filter(e => e.facility_gln === selectedFacility.gln)}
                  isSelected
                  onClick={() => setSelectedFacility(null)}
                />
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
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                      Recent Alerts
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {dashboard.data.recent_alerts.slice(0, 5).map((alert) => (
                        <div
                          key={alert.id}
                          className="flex items-start gap-2 rounded-md bg-re-surface-inset p-2 text-ui"
                        >
                          {alert.severity === 'CRITICAL' ? (
                            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                          ) : alert.severity === 'WARNING' ? (
                            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                          ) : (
                            <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-info" strokeWidth={1.75} aria-hidden="true" />
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-re-text-secondary">{alert.message}</p>
                            <p className="text-small text-re-text-tertiary">{alert.source}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Quick Actions */}
              <Card>
                <CardHeader>
                  <CardTitle>Quick Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button className="w-full justify-start" asChild>
                    <Link href="/fsma/assessment">
                      <CheckCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Readiness Assessment
                    </Link>
                  </Button>
                  <Button variant="secondary" className="w-full justify-start" asChild>
                    <Link href="/fsma/integration">
                      <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Integration Blueprint
                    </Link>
                  </Button>
                  <Button variant="secondary" className="w-full justify-start" asChild>
                    <Link href="/trace">
                      <Search className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Advanced Trace Query
                    </Link>
                  </Button>
                  <Button
                    variant="secondary"
                    className="w-full justify-start"
                    onClick={() => activeTlc && handleStartDrill('BACKWARD')}
                    disabled={!activeTlc}
                  >
                    <PlayCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                    Start Backward Drill
                  </Button>
                  <Button variant="secondary" className="w-full justify-start" asChild>
                    <Link href="/compliance">
                      <Shield className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      View Compliance Checklists
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </PageContainer>
    </DashboardLayout>
  );
}
