'use client';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';

import { useAuth } from '@/lib/auth-context';
import { useQuery } from '@tanstack/react-query';

import {
  CheckCircle,
  Eye,
  FileText,
  Hash,
  Shield,
  AlertTriangle,
  XCircle,
  Database,
  Timer,
  Lock,
} from 'lucide-react';

const INGESTION_API = '/api/ingestion';

async function auditFetch<T>(endpoint: string, apiKey: string): Promise<T> {
  const response = await fetch(`${INGESTION_API}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-RegEngine-API-Key': apiKey,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

interface AuditSummary {
  records: { total_canonical_events: number; ingestion_sources: Record<string, number> };
  compliance: { total_evaluations: number; pass_rate_percent: number; passed: number; failed: number; warned: number };
  exceptions: { total: number; open: number; critical_open: number };
  requests: { total: number; submitted: number; active: number };
  chain_integrity: { chain_length: number; status: string };
  generated_at: string;
}

export default function AuditReviewPage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';

  const summary = useQuery({
    queryKey: ['audit', 'summary', tid],
    queryFn: () => auditFetch<AuditSummary>(
      `/api/v1/audit/summary?tenant_id=${tid}`, apiKey || ''
    ),
    enabled: !!apiKey && !!tid,
    staleTime: 60_000,
  });

  const rules = useQuery({
    queryKey: ['audit', 'rules', tid],
    queryFn: () => auditFetch<{ rules: any[] }>(
      `/api/v1/audit/rules?tenant_id=${tid}`, apiKey || ''
    ),
    enabled: !!apiKey && !!tid,
    staleTime: 60_000,
  });

  const s = summary.data;

  return (
    <PageContainer>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Eye className="h-6 w-6 text-slate-600" />
            Auditor Review
          </h1>
          <p className="text-muted-foreground mt-1">
            Read-only compliance posture view — evidentiary chain, rule evaluations, exception history
          </p>
        </div>
        <Badge variant="outline" className="flex items-center gap-1 text-sm px-3 py-1">
          <Lock className="h-3.5 w-3.5" />
          Read-Only Mode
        </Badge>
      </div>

      {summary.isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : s ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center gap-2 mb-2">
                  <Database className="h-4 w-4 text-indigo-500" />
                  <span className="text-xs text-muted-foreground uppercase tracking-wider">Records</span>
                </div>
                <p className="text-3xl font-bold">{s.records.total_canonical_events.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {Object.keys(s.records.ingestion_sources).length} source systems
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="h-4 w-4 text-green-500" />
                  <span className="text-xs text-muted-foreground uppercase tracking-wider">Compliance</span>
                </div>
                <p className="text-3xl font-bold">{s.compliance.pass_rate_percent}%</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {s.compliance.passed} pass / {s.compliance.failed} fail / {s.compliance.warned} warn
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  <span className="text-xs text-muted-foreground uppercase tracking-wider">Exceptions</span>
                </div>
                <p className="text-3xl font-bold">{s.exceptions.open}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {s.exceptions.critical_open} critical / {s.exceptions.total} total
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center gap-2 mb-2">
                  <Hash className="h-4 w-4 text-blue-500" />
                  <span className="text-xs text-muted-foreground uppercase tracking-wider">Chain Integrity</span>
                </div>
                <p className="text-3xl font-bold">
                  {s.chain_integrity.status === 'VERIFIED' ? (
                    <span className="text-green-600 flex items-center gap-1">
                      <CheckCircle className="h-6 w-6" /> OK
                    </span>
                  ) : (
                    <span className="text-muted-foreground">N/A</span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {s.chain_integrity.chain_length} chain entries
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Compliance Gauge */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg">Rule Compliance Rate</CardTitle>
              <CardDescription>
                {s.compliance.total_evaluations.toLocaleString()} total evaluations across all records
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Progress
                value={s.compliance.pass_rate_percent}
                className="h-4 mb-2"
              />
              <div className="flex justify-between text-sm">
                <span className="text-green-600">{s.compliance.passed} passed</span>
                <span className="text-red-600">{s.compliance.failed} failed</span>
                <span className="text-amber-600">{s.compliance.warned} warned</span>
              </div>
            </CardContent>
          </Card>

          {/* Ingestion Sources */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Ingestion Sources</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(s.records.ingestion_sources).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No records ingested yet</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(s.records.ingestion_sources).map(([source, count]) => (
                      <div key={source} className="flex justify-between items-center text-sm">
                        <span className="text-muted-foreground">{source.replace(/_/g, ' ')}</span>
                        <Badge variant="outline">{(count as number).toLocaleString()}</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Request Cases</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total Cases</span>
                    <span className="font-bold">{s.requests.total}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Submitted</span>
                    <span className="font-bold text-green-600">{s.requests.submitted}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Active</span>
                    <span className="font-bold text-blue-600">{s.requests.active}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Rule Catalog with Stats */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Shield className="h-5 w-5 text-blue-500" />
                Rule Catalog
              </CardTitle>
              <CardDescription>
                Active compliance rules with evaluation statistics
              </CardDescription>
            </CardHeader>
            <CardContent>
              {rules.isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full" />)}
                </div>
              ) : (
                <div className="space-y-2">
                  {(rules.data?.rules ?? []).map((rule: any) => (
                    <div key={rule.rule_id} className="border rounded-lg p-3 text-sm">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <Badge variant={rule.severity === 'critical' ? 'destructive' : rule.severity === 'warning' ? 'warning' : 'secondary'}>
                              {rule.severity}
                            </Badge>
                            <span className="font-medium">{rule.title}</span>
                          </div>
                          {rule.citation_reference && (
                            <p className="text-xs text-muted-foreground mt-1">{rule.citation_reference}</p>
                          )}
                        </div>
                        <div className="text-right text-xs">
                          {rule.evaluation_stats.total > 0 ? (
                            <>
                              <span className={rule.evaluation_stats.pass_rate_percent >= 90 ? 'text-green-600' : rule.evaluation_stats.pass_rate_percent >= 70 ? 'text-amber-600' : 'text-red-600'}>
                                {rule.evaluation_stats.pass_rate_percent}% pass
                              </span>
                              <p className="text-muted-foreground">
                                {rule.evaluation_stats.total} evals
                              </p>
                            </>
                          ) : (
                            <span className="text-muted-foreground">No evals</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Timestamp */}
          <p className="text-xs text-muted-foreground text-center mt-6">
            Report generated at {new Date(s.generated_at).toLocaleString()}
          </p>
        </>
      ) : null}
    </PageContainer>
  );
}
