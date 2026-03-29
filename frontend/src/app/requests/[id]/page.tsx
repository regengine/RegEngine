'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import {
  useRequestCases,
  usePackageHistory,
  useAssemblePackage,
  useSubmitPackage,
  type RequestCase,
} from '@/hooks/use-control-plane';

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Clock,
  FileText,
  Hash,
  Package,
  Send,
  Shield,
  Timer,
  User,
} from 'lucide-react';

interface ResponsePackage {
  package_id: string;
  version_number: number;
  generated_at: string;
  generated_by?: string;
  package_hash?: string;
  diff_from_previous?: Record<string, unknown>;
}

const STAGE_ORDER = [
  'intake', 'scoping', 'collecting', 'gap_analysis',
  'exception_triage', 'assembling', 'internal_review',
  'ready', 'submitted', 'amended',
];

const STAGE_LABELS: Record<string, string> = {
  intake: 'Intake',
  scoping: 'Scoping',
  collecting: 'Collecting',
  gap_analysis: 'Gap Analysis',
  exception_triage: 'Exception Triage',
  assembling: 'Assembling',
  internal_review: 'Internal Review',
  ready: 'Ready',
  submitted: 'Submitted',
  amended: 'Amended',
};

export default function RequestCaseDetailPage() {
  const params = useParams();
  const requestCaseId = params.id as string;
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';

  const requests = useRequestCases(tid);
  const packages = usePackageHistory(tid, requestCaseId);
  const assemblePackage = useAssemblePackage(tid);
  const submitPackage = useSubmitPackage(tid);

  const requestCase = requests.data?.cases?.find(
    (c: RequestCase) => c.request_case_id === requestCaseId
  );
  const packageList = (packages.data?.packages ?? []) as unknown as ResponsePackage[];

  if (requests.isLoading) {
    return (
      <PageContainer>
        <div className="space-y-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-40 w-full" />)}
        </div>
      </PageContainer>
    );
  }

  if (!requestCase) {
    return (
      <PageContainer>
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p className="font-medium">Request case not found</p>
            <Link href="/requests" className="text-sm text-blue-500 hover:underline mt-2 inline-block">
              Back to Request Workflow
            </Link>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  const currentStageIdx = STAGE_ORDER.indexOf(requestCase.package_status);
  const progress = Math.max(5, ((currentStageIdx + 1) / STAGE_ORDER.length) * 100);
  const isOverdue = requestCase.is_overdue;
  const hoursLeft = requestCase.hours_remaining ?? 0;

  return (
    <PageContainer>
      {/* Back link + header */}
      <div className="mb-6">
        <Link href="/requests" className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 mb-4">
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Request Workflow
        </Link>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <Timer className="h-6 w-6 text-blue-500" />
              Request Case
            </h1>
            <p className="text-muted-foreground mt-1">
              {requestCase.requesting_party} — {requestCase.scope_type?.replace(/_/g, ' ')}
            </p>
          </div>
          <div className={`text-right ${isOverdue ? 'text-red-600' : ''}`}>
            <div className="flex items-center gap-2 text-lg font-bold">
              <Clock className="h-5 w-5" />
              {requestCase.countdown_display || `${Math.max(0, hoursLeft).toFixed(1)}h remaining`}
            </div>
            {isOverdue && <Badge variant="destructive">OVERDUE</Badge>}
          </div>
        </div>
      </div>

      {/* Workflow Stage Pipeline */}
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Workflow Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <Progress value={progress} className="h-3 mb-4" />
          <div className="flex flex-wrap gap-1">
            {STAGE_ORDER.map((stage, idx) => {
              const isCurrent = stage === requestCase.package_status;
              const isPast = idx < currentStageIdx;
              return (
                <div
                  key={stage}
                  className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
                    isCurrent ? 'bg-blue-100 text-blue-800 font-bold border border-blue-300' :
                    isPast ? 'bg-green-50 text-green-700' :
                    'text-muted-foreground'
                  }`}
                >
                  {isPast && <CheckCircle className="h-3 w-3" />}
                  {STAGE_LABELS[stage]}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: case details */}
        <div className="lg:col-span-2 space-y-4">
          {/* Scope */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Scope</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground">Requesting Party</dt>
                  <dd className="font-medium">{requestCase.requesting_party}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Scope Type</dt>
                  <dd className="font-medium">{requestCase.scope_type?.replace(/_/g, ' ')}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Received</dt>
                  <dd>{new Date(requestCase.request_received_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Due</dt>
                  <dd className={isOverdue ? 'text-red-600 font-bold' : ''}>
                    {new Date(requestCase.response_due_at).toLocaleString()}
                  </dd>
                </div>
              </dl>

              {requestCase.affected_lots?.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs text-muted-foreground mb-1">Affected Lot Codes</p>
                  <div className="flex flex-wrap gap-1">
                    {requestCase.affected_lots.map((lot: string) => (
                      <Badge key={lot} variant="outline" className="text-xs font-mono">{lot}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {requestCase.affected_facilities?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Affected Facilities</p>
                  <div className="flex flex-wrap gap-1">
                    {requestCase.affected_facilities.map((f: string) => (
                      <Badge key={f} variant="outline" className="text-xs">{f}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Package History */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Package className="h-5 w-5 text-purple-500" />
                Response Packages ({packageList.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {packages.isLoading ? (
                <div className="space-y-2">
                  {[1, 2].map(i => <Skeleton key={i} className="h-16 w-full" />)}
                </div>
              ) : packageList.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No packages assembled yet
                </p>
              ) : (
                <div className="space-y-3">
                  {packageList.map((pkg: ResponsePackage) => (
                    <div key={pkg.package_id} className="border rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs">v{pkg.version_number}</Badge>
                          <span className="text-xs text-muted-foreground">
                            {new Date(pkg.generated_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 text-xs font-mono text-muted-foreground">
                          <Hash className="h-3 w-3" />
                          {pkg.package_hash?.slice(0, 12)}...
                        </div>
                      </div>
                      {pkg.generated_by && (
                        <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                          <User className="h-3 w-3" />
                          {pkg.generated_by}
                        </div>
                      )}
                      {pkg.diff_from_previous && (
                        <div className="mt-2 text-xs bg-muted p-2 rounded">
                          <span className="font-medium">Diff from v{pkg.version_number - 1}:</span>
                          <pre className="mt-1 overflow-x-auto">
                            {JSON.stringify(pkg.diff_from_previous, null, 2).slice(0, 200)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column: stats + actions */}
        <div className="space-y-4">
          {/* Quick Stats */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Case Stats</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Records Collected</span>
                <span className="font-bold">{requestCase.total_records}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Gaps Found</span>
                <span className={`font-bold ${requestCase.gap_count > 0 ? 'text-amber-600' : 'text-green-600'}`}>
                  {requestCase.gap_count}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Active Exceptions</span>
                <span className={`font-bold ${requestCase.active_exception_count > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {requestCase.active_exception_count}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Package Versions</span>
                <span className="font-bold">{packageList.length}</span>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {requestCase.package_status !== 'submitted' && (
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => assemblePackage.mutate({
                    requestCaseId,
                    generatedBy: 'dashboard_user',
                  })}
                  disabled={assemblePackage.isPending}
                >
                  <Package className="h-4 w-4 mr-2" />
                  {assemblePackage.isPending ? 'Assembling...' : 'Assemble Package'}
                </Button>
              )}
              {requestCase.package_status === 'ready' && (
                <Button
                  className="w-full"
                  onClick={() => submitPackage.mutate({
                    requestCaseId,
                    submitted_by: 'dashboard_user',
                    submitted_to: requestCase.requesting_party,
                  })}
                  disabled={submitPackage.isPending}
                >
                  <Send className="h-4 w-4 mr-2" />
                  {submitPackage.isPending ? 'Submitting...' : 'Submit to ' + requestCase.requesting_party}
                </Button>
              )}
              {requestCase.package_status === 'submitted' && (
                <div className="text-center py-3">
                  <CheckCircle className="h-8 w-8 text-green-500 mx-auto mb-2" />
                  <p className="text-sm font-medium text-green-700">Package Submitted</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
