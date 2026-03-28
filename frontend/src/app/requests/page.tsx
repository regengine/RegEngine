'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';

import { useAuth } from '@/lib/auth-context';
import {
  useRequestCases,
  useCreateRequestCase,
  useAssemblePackage,
  useSubmitPackage,
} from '@/hooks/use-control-plane';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  AlertTriangle,
  CheckCircle,
  Clock,
  FileText,
  Package,
  PlayCircle,
  Send,
  Timer,
} from 'lucide-react';

const STATUS_CONFIG: Record<string, { label: string; color: string; progress: number }> = {
  intake: { label: 'Intake', color: 'bg-gray-500', progress: 5 },
  scoping: { label: 'Scoping', color: 'bg-blue-400', progress: 15 },
  collecting: { label: 'Collecting', color: 'bg-blue-500', progress: 30 },
  gap_analysis: { label: 'Gap Analysis', color: 'bg-amber-500', progress: 45 },
  exception_triage: { label: 'Exception Triage', color: 'bg-orange-500', progress: 55 },
  assembling: { label: 'Assembling', color: 'bg-purple-500', progress: 70 },
  internal_review: { label: 'Internal Review', color: 'bg-indigo-500', progress: 80 },
  ready: { label: 'Ready', color: 'bg-green-500', progress: 90 },
  submitted: { label: 'Submitted', color: 'bg-green-600', progress: 100 },
  amended: { label: 'Amended', color: 'bg-teal-500', progress: 100 },
};

export default function RequestWorkflowPage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';

  const [showCreate, setShowCreate] = useState(false);
  const [newRequestParty, setNewRequestParty] = useState('FDA');
  const [newRequestLots, setNewRequestLots] = useState('');

  const requests = useRequestCases(tid);
  const createRequest = useCreateRequestCase(tid);
  const assemblePackage = useAssemblePackage(tid);
  const submitPackage = useSubmitPackage(tid);

  const cases = requests.data?.cases ?? [];
  const activeCases = cases.filter(c => !['submitted', 'amended'].includes(c.package_status));
  const completedCases = cases.filter(c => ['submitted', 'amended'].includes(c.package_status));

  if (requests.error) {
    return (
      <PageContainer>
        <div className="p-8 text-center">
          <p className="text-muted-foreground">Unable to load data from the control plane API.</p>
          <p className="text-sm text-muted-foreground/60 mt-2">{(requests.error as Error).message}</p>
          <button onClick={() => requests.refetch()} className="mt-4 text-sm text-primary hover:underline">
            Retry
          </button>
        </div>
      </PageContainer>
    );
  }

  const handleCreate = async () => {
    const lots = newRequestLots.split(',').map(s => s.trim()).filter(Boolean);
    await createRequest.mutateAsync({
      requesting_party: newRequestParty,
      scope_type: 'tlc_trace',
      affected_lots: lots,
      response_hours: 24,
    });
    setShowCreate(false);
    setNewRequestLots('');
  };

  return (
    <PageContainer>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Timer className="h-6 w-6 text-blue-500" />
            Request-Response Workflow
          </h1>
          <p className="text-muted-foreground mt-1">
            24-hour FDA response readiness — from request intake to sealed package submission
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <PlayCircle className="h-4 w-4 mr-2" />
          New Request Case
        </Button>
      </div>

      <DemoBanner visible={!!(requests.data?.__isDemo)} />

      {/* Create Form */}
      {showCreate && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
          <Card className="mb-6 border-blue-200">
            <CardHeader>
              <CardTitle className="text-lg">Open New Request Case</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Requesting Party</label>
                  <select
                    className="mt-1 w-full border rounded px-3 py-2 text-sm bg-background"
                    value={newRequestParty}
                    onChange={e => setNewRequestParty(e.target.value)}
                  >
                    <option value="FDA">FDA</option>
                    <option value="State DOH">State DOH</option>
                    <option value="Internal Drill">Internal Drill</option>
                    <option value="Customer Audit">Customer Audit</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Affected Lot Codes (comma-separated)</label>
                  <Input
                    className="mt-1"
                    placeholder="TLC-001, TLC-002..."
                    value={newRequestLots}
                    onChange={e => setNewRequestLots(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Button onClick={handleCreate} disabled={createRequest.isPending}>
                  {createRequest.isPending ? 'Creating...' : 'Create Case (24h deadline)'}
                </Button>
                <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Active Cases */}
      <div className="space-y-4 mb-8">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Clock className="h-5 w-5 text-amber-500" />
          Active Cases ({activeCases.length})
        </h2>

        {requests.isLoading ? (
          <div className="space-y-3">
            {[1, 2].map(i => <Skeleton key={i} className="h-40 w-full" />)}
          </div>
        ) : activeCases.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-400" />
              <p className="font-medium">No active request cases</p>
              <p className="text-sm">Create a new case to start a response workflow</p>
            </CardContent>
          </Card>
        ) : (
          activeCases.map(rc => {
            const config = STATUS_CONFIG[rc.package_status] || STATUS_CONFIG.intake;
            const isOverdue = rc.is_overdue;
            const hoursLeft = rc.hours_remaining ?? 0;

            return (
              <motion.div key={rc.request_case_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <Card className={isOverdue ? 'border-red-300 bg-red-50/30' : ''}>
                  <CardContent className="pt-5 pb-4">
                    <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                      {/* Left: case info */}
                      <div className="flex-1 space-y-3">
                        <div className="flex items-center gap-3">
                          <Badge className={`${config.color} text-white`}>{config.label}</Badge>
                          <span className="text-sm font-medium">{rc.requesting_party}</span>
                          <span className="text-xs text-muted-foreground">
                            {rc.scope_type?.replace(/_/g, ' ')}
                          </span>
                        </div>

                        {/* Progress bar */}
                        <div>
                          <Progress value={config.progress} className="h-2" />
                          <div className="flex justify-between mt-1">
                            <span className="text-xs text-muted-foreground">
                              {rc.total_records} records collected
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {rc.gap_count} gaps / {rc.active_exception_count} exceptions
                            </span>
                          </div>
                        </div>

                        {/* Scope */}
                        {rc.affected_lots?.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {rc.affected_lots.slice(0, 5).map(lot => (
                              <Badge key={lot} variant="outline" className="text-xs">{lot}</Badge>
                            ))}
                            {rc.affected_lots.length > 5 && (
                              <Badge variant="outline" className="text-xs">+{rc.affected_lots.length - 5} more</Badge>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Right: countdown + actions */}
                      <div className="flex flex-col items-end gap-2 min-w-[180px]">
                        <div className={`text-right ${isOverdue ? 'text-red-600' : 'text-muted-foreground'}`}>
                          <div className="flex items-center gap-1 text-sm font-medium">
                            <Timer className="h-4 w-4" />
                            {rc.countdown_display || `${Math.max(0, hoursLeft).toFixed(1)}h remaining`}
                          </div>
                          {isOverdue && (
                            <span className="text-xs font-bold text-red-600">OVERDUE</span>
                          )}
                        </div>

                        <div className="flex gap-1">
                          {rc.package_status === 'ready' && (
                            <Button
                              size="sm"
                              onClick={() => submitPackage.mutate({
                                requestCaseId: rc.request_case_id,
                                submitted_by: 'dashboard_user',
                                submitted_to: rc.requesting_party,
                              })}
                            >
                              <Send className="h-3.5 w-3.5 mr-1" />
                              Submit
                            </Button>
                          )}
                          {!['ready', 'submitted'].includes(rc.package_status) && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => assemblePackage.mutate({
                                requestCaseId: rc.request_case_id,
                                generatedBy: 'dashboard_user',
                              })}
                            >
                              <Package className="h-3.5 w-3.5 mr-1" />
                              Assemble
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })
        )}
      </div>

      {/* Completed Cases */}
      {completedCases.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FileText className="h-5 w-5 text-green-500" />
            Completed ({completedCases.length})
          </h2>
          {completedCases.map(rc => (
            <Card key={rc.request_case_id} className="opacity-75">
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Badge className="bg-green-600 text-white">{rc.package_status === 'amended' ? 'Amended' : 'Submitted'}</Badge>
                    <span className="text-sm">{rc.requesting_party}</span>
                    <span className="text-xs text-muted-foreground">{rc.total_records} records</span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(rc.request_received_at).toLocaleDateString()}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </PageContainer>
  );
}
