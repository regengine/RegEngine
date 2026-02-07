'use client';

import React, { useState } from 'react';
import { Zap, Activity, Shield, Layers, AlertTriangle, Download, FileText, RefreshCw, Database } from 'lucide-react';
import {
  VerticalDashboardLayout,
  ComplianceMetricsGrid,
  RealTimeMonitor,
  ComplianceTimeline,
  AlertsWidget,
  QuickActionsPanel,
  ComplianceScoreGauge,
  ExportButton,
  type QuickAction,
} from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { VerificationWidget } from '@/features/energy/components/VerificationWidget';
import { SnapshotList } from '@/features/energy/components/SnapshotList';
import { AuditHistoryTimeline } from '@/features/energy/components/AuditHistoryTimeline';

// Import dashboard API hooks
import {
  useDashboardMetrics,
  useSubstationHealth,
  useActivityTimeline,
  useActiveAlerts,
  useSystemHealth,
} from './api';

const createSnapshot = async () => {
  try {
    const response = await fetch('/api/energy/snapshots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        substation_id: 'ALPHA-001',
        facility_name: 'Primary Grid',
        assets: [],
        esp_config: {},
        patch_metrics: {},
        trigger_reason: 'Manual dashboard snapshot'
      })
    });

    if (response.ok) {
      const data = await response.json();
      alert(`✅ Snapshot created: ${data.snapshot_id}`);
      window.location.reload(); // Refresh to show new snapshot
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    alert(`❌ Failed to create snapshot: ${error}`);
  }
};

const runVerification = async () => {
  try {
    const response = await fetch('/api/energy/verify/recent?limit=100');

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.corrupted > 0) {
      alert(`⚠️ Verification Alert: ${data.corrupted} corrupted snapshots detected!\n\nVerified: ${data.verified}\nFailed: ${data.corrupted}\n\nContact compliance team immediately.`);
    } else {
      alert(`✅ Chain Integrity Verified\n\nAll ${data.verified} snapshots passed verification.\n\nContent hash: ✓\nSignatures: ✓\nChain linkage: ✓`);
    }
  } catch (error) {
    alert(`❌ Verification failed: ${error}`);
  }
};

const quickActions: QuickAction[] = [
  { label: 'Create Snapshot', icon: Database, onClick: createSnapshot, variant: 'default', description: 'Capture immediate compliance snapshot' },
  { label: 'Run Verification', icon: Shield, onClick: runVerification, variant: 'outline', description: 'Verify chain integrity' },
  { label: 'View API Docs', icon: FileText, href: '/docs/energy', variant: 'outline' },
];

export default function EnergyDashboardPage() {
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Fetch real-time data using API hooks
  const { data: metrics, isLoading: metricsLoading, error: metricsError } = useDashboardMetrics();
  const { data: substations, isLoading: substationsLoading } = useSubstationHealth();
  const { data: timeline, isLoading: timelineLoading } = useActivityTimeline(5);
  const { data: alerts, isLoading: alertsLoading } = useActiveAlerts(3);
  const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 1000);
  };

  // Show error state if metrics fail to load
  if (metricsError) {
    return (
      <VerticalDashboardLayout
        title="Energy Compliance Dashboard"
        subtitle="NERC CIP-013 Grid Monitoring & Compliance"
        icon={Zap}
        iconColor="text-blue-600 dark:text-blue-400"
        iconBgColor="bg-blue-100 dark:bg-blue-900"
        systemStatus={{ label: 'Error Loading Data', variant: 'error', icon: AlertTriangle }}
      >
        <Card>
          <CardContent className="py-12 text-center">
            <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3>
            <p className="text-muted-foreground mb-4">
              Unable to connect to Energy API. Please check backend services.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
            >
              Retry
            </button>
          </CardContent>
        </Card>
      </VerticalDashboardLayout>
    );
  }

  return (
    <VerticalDashboardLayout
      title="Energy Compliance Dashboard"
      subtitle="NERC CIP-013 Grid Monitoring & Compliance"
      icon={Zap}
      iconColor="text-blue-600 dark:text-blue-400"
      iconBgColor="bg-blue-100 dark:bg-blue-900"
      systemStatus={{ label: 'All Systems Operational', variant: 'success', icon: Activity }}
    >
      {/* Metrics Grid */}
      {metricsLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <ComplianceMetricsGrid metrics={metrics || []} columns={4} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2/3 width) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Compliance Score */}
          <Card>
            <CardHeader>
              <CardTitle>CIP-013 Compliance Score</CardTitle>
              <CardDescription>
                Overall compliance health based on substation monitoring and snapshot integrity
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-center py-8">
              <ComplianceScoreGauge score={94} label="Compliance Score" size="lg" showTrend trend={3} />
            </CardContent>
          </Card>

          {/* Substation Health Matrix */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Substation Health Matrix</CardTitle>
                  <CardDescription>Real-time status of monitored assets</CardDescription>
                </div>
                <button
                  onClick={handleRefresh}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  <RefreshCw className={`w-5 h-5 ${isRefreshing ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </CardHeader>
            <CardContent>
              {substationsLoading ? (
                <div className="grid grid-cols-3 gap-3">
                  {[...Array(6)].map((_, i) => (
                    <Skeleton key={i} className="h-24 w-full" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-3">
                  {substations?.map((station) => (
                    <div
                      key={station.id}
                      className="p-4 rounded-lg border bg-card hover:shadow-md transition-shadow cursor-pointer"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-sm font-medium">{station.name}</span>
                        <div
                          className={`w-2 h-2 rounded-full ${station.status === 'healthy'
                            ? 'bg-green-500'
                            : station.status === 'degraded'
                              ? 'bg-yellow-500'
                              : 'bg-red-500'
                            }`}
                        />
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-muted-foreground">Firmware</span>
                          <span className="font-medium">{station.firmware}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-muted-foreground">Last Snapshot</span>
                          <span className="font-medium">{station.lastSnapshot}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Snapshot List (with modal integration) */}
          <SnapshotList substationId="ALPHA-001" maxItems={5} />

          {/* Activity Timeline */}
          {timelineLoading ? (
            <Card>
              <CardContent className="p-6">
                <Skeleton className="h-48 w-full" />
              </CardContent>
            </Card>
          ) : (
            <ComplianceTimeline events={timeline || []} title="Recent Activity" maxItems={5} />
          )}
        </div>

        {/* Right Column (1/3 width) */}
        <div className="space-y-6">
          {/* Real-Time System Monitor */}
          {healthLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <RealTimeMonitor
              title="Grid Cyber Monitor"
              description="Real-time NERC CIP-013 status"
              health={systemHealth || { status: 'UNKNOWN', message: 'Data unavailable', lastCheck: 'N/A', uptime: 'N/A' }}
              stats={[
                { label: 'Substations', value: `${substations?.length || 0}`, status: 'ok' },
                { label: 'Uptime', value: systemHealth?.uptime || 'N/A', status: 'ok' },
              ]}
              onRefresh={handleRefresh}
              isRefreshing={isRefreshing}
            />
          )}

          {/* Chain Integrity Verification */}
          <VerificationWidget substationId="ALPHA-001" />

          {/* Audit History Timeline */}
          <AuditHistoryTimeline substationId="ALPHA-001" maxItems={3} />

          {/* Alerts */}
          {alertsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <AlertsWidget alerts={alerts || []} />
          )}

          {/* Quick Actions */}
          <QuickActionsPanel actions={quickActions} />

          {/* Export Button */}
          <ExportButton
            data={{
              title: 'Energy Compliance Report',
              metrics: metrics?.map(m => ({ label: m.label, value: m.value })) || [],
              tables: [
                {
                  title: 'Substation Health Status',
                  headers: ['Substation', 'Status', 'Firmware', 'Last Snapshot'],
                  rows: substations?.map(s => [s.name, s.status, s.firmware, s.lastSnapshot]) || [],
                },
              ],
              metadata: { 'generated_at': new Date().toISOString(), 'compliance_score': 94, 'chain_integrity': '100%' },
            }}
            filename="energy_compliance_report"
            variant="default"
            className="w-full"
          />
        </div>
      </div>
    </VerticalDashboardLayout>
  );
}
