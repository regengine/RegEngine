'use client';

import { DemoBanner } from '@/components/control-plane/demo-banner';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import { useQuery } from '@tanstack/react-query';

import { Lock, Shield } from 'lucide-react';

const INGESTION_API = '/api/ingestion';

async function auditFetch<T>(endpoint: string): Promise<T> {
  const response = await fetchWithCsrf(`${INGESTION_API}${endpoint}`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

interface AuditRule {
  rule_id: string;
  title: string;
  severity: string;
  citation_reference?: string;
  evaluation_stats: {
    total: number;
    pass_rate_percent: number;
  };
}

interface AuditSummary {
  records: { total_canonical_events: number; ingestion_sources: Record<string, number> };
  compliance: { total_evaluations: number; pass_rate_percent: number; passed: number; failed: number; warned: number };
  exceptions: { total: number; open: number; critical_open: number };
  requests: { total: number; submitted: number; active: number };
  chain_integrity: { chain_length: number | null; status: string; errors?: string[]; verified_at?: string | null };
  generated_at: string;
}

const SEVERITY_TONE: Record<string, BadgeTone> = {
  critical: 'danger',
  warning: 'warning',
  info: 'info',
};

export default function AuditReviewPage() {
  if (!experimentalFeaturesEnabled()) {
    return (
      <FeatureNotEnabled
        featureName="Audit review"
        backHref="/dashboard"
        backLabel="Back to dashboard"
      />
    );
  }
  return <AuditReviewContent />;
}

function AuditReviewContent() {
  const { isAuthenticated, tenantId } = useAuth();
  const tid = tenantId || '';

  const summary = useQuery({
    queryKey: ['audit', 'summary', tid],
    queryFn: () => auditFetch<AuditSummary>('/api/v1/audit/summary'),
    enabled: isAuthenticated && !!tid,
    staleTime: 60_000,
  });

  const rules = useQuery({
    queryKey: ['audit', 'rules', tid],
    queryFn: () => auditFetch<{ rules: AuditRule[] }>('/api/v1/audit/rules'),
    enabled: isAuthenticated && !!tid,
    staleTime: 60_000,
  });

  const s = summary.data;
  const ruleList = rules.data?.rules ?? [];

  const ruleColumns: DataTableColumn<AuditRule>[] = [
    {
      key: 'severity',
      header: 'Severity',
      width: '8rem',
      cell: (rule) => (
        <Badge tone={SEVERITY_TONE[rule.severity] ?? 'neutral'} size="sm">{rule.severity}</Badge>
      ),
    },
    {
      key: 'title',
      header: 'Rule',
      cell: (rule) => <span className="font-medium text-re-text-primary">{rule.title}</span>,
    },
    {
      key: 'citation_reference',
      header: 'Citation',
      mono: true,
      width: '12rem',
      cell: (rule) => (
        <span className="text-re-text-tertiary">{rule.citation_reference || '—'}</span>
      ),
    },
    {
      key: 'pass_rate',
      header: 'Pass rate',
      align: 'right',
      width: '9rem',
      cell: (rule) =>
        rule.evaluation_stats.total > 0 ? (
          <span
            className={cn(
              'tabular-nums',
              rule.evaluation_stats.pass_rate_percent >= 90
                ? 'text-re-success'
                : rule.evaluation_stats.pass_rate_percent >= 70
                  ? 'text-re-warning'
                  : 'text-re-danger'
            )}
          >
            {rule.evaluation_stats.pass_rate_percent}% pass
          </span>
        ) : (
          <span className="text-re-text-muted">No evals</span>
        ),
    },
    {
      key: 'evals',
      header: 'Evaluations',
      align: 'right',
      width: '8rem',
      cell: (rule) => (
        <span className="tabular-nums text-re-text-tertiary">{rule.evaluation_stats.total}</span>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Auditor Review"
        description="Read-only compliance posture view — evidentiary chain, rule evaluations, exception history"
        meta={
          <Badge>
            <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            Read-Only Mode
          </Badge>
        }
      />

      <DemoBanner visible={false} />

      {summary.error && (
        <Callout
          tone="danger"
          role="alert"
          className="mb-6"
          title="Unable to load data from the control plane API."
          action={
            <Button variant="secondary" size="sm" onClick={() => summary.refetch()}>
              Retry
            </Button>
          }
        >
          {(summary.error as Error).message}
        </Callout>
      )}

      {summary.isLoading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-32" />)}
        </div>
      ) : s ? (
        <>
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatTile label="Records" value={s.records.total_canonical_events.toLocaleString()}>
              <p className="text-small text-re-text-tertiary">
                {Object.keys(s.records.ingestion_sources).length} source systems
              </p>
            </StatTile>

            <StatTile label="Compliance" value={s.compliance.pass_rate_percent} unit="%">
              <p className="text-small text-re-text-tertiary">
                {s.compliance.passed} pass / {s.compliance.failed} fail / {s.compliance.warned} warn
              </p>
            </StatTile>

            <StatTile label="Exceptions" value={s.exceptions.open}>
              <p className="text-small text-re-text-tertiary">
                {s.exceptions.critical_open} critical / {s.exceptions.total} total
              </p>
            </StatTile>

            <StatTile
              label="Chain Integrity"
              value={
                s.chain_integrity.status === 'VERIFIED'
                  ? 'OK'
                  : s.chain_integrity.status === 'UNVERIFIED'
                    ? 'FAILED'
                    : 'N/A'
              }
            >
              <p className="text-small text-re-text-tertiary">
                {s.chain_integrity.chain_length === null
                  ? 'Chain not checked'
                  : `${s.chain_integrity.chain_length} chain entries`}
              </p>
            </StatTile>
          </div>

          <Card className="mb-6">
            <CardHeader>
              <div className="min-w-0">
                <CardTitle>Rule Compliance Rate</CardTitle>
                <CardDescription className="mt-1">
                  {s.compliance.total_evaluations.toLocaleString()} total evaluations across all records
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Progress value={s.compliance.pass_rate_percent} className="mb-2 h-4" />
              <div className="flex flex-wrap justify-between gap-2 text-ui">
                <span className="text-re-success">{s.compliance.passed} passed</span>
                <span className="text-re-danger">{s.compliance.failed} failed</span>
                <span className="text-re-warning">{s.compliance.warned} warned</span>
              </div>
            </CardContent>
          </Card>

          <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Ingestion Sources</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(s.records.ingestion_sources).length === 0 ? (
                  <p className="text-ui text-re-text-tertiary">No records ingested yet</p>
                ) : (
                  <dl>
                    {Object.entries(s.records.ingestion_sources).map(([source, count]) => (
                      <div
                        key={source}
                        className="flex items-center justify-between border-b border-re-border-subtle py-2 last:border-0"
                      >
                        <dt className="text-ui text-re-text-secondary">{source.replace(/_/g, ' ')}</dt>
                        <dd><Badge size="sm">{(count as number).toLocaleString()}</Badge></dd>
                      </div>
                    ))}
                  </dl>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Request Cases</CardTitle>
              </CardHeader>
              <CardContent>
                <dl>
                  <div className="flex items-center justify-between border-b border-re-border-subtle py-2">
                    <dt className="text-ui text-re-text-secondary">Total Cases</dt>
                    <dd className="tabular-nums text-ui text-re-text-primary">{s.requests.total}</dd>
                  </div>
                  <div className="flex items-center justify-between border-b border-re-border-subtle py-2">
                    <dt className="text-ui text-re-text-secondary">Submitted</dt>
                    <dd className="tabular-nums text-ui text-re-text-primary">{s.requests.submitted}</dd>
                  </div>
                  <div className="flex items-center justify-between py-2">
                    <dt className="text-ui text-re-text-secondary">Active</dt>
                    <dd className="tabular-nums text-ui text-re-text-primary">{s.requests.active}</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          </div>

          <Section
            spacing="app"
            title="Rule Catalog"
            description="Active compliance rules with evaluation statistics"
          >
            <DataTable
              caption="Active compliance rules with evaluation statistics"
              columns={ruleColumns}
              data={ruleList}
              minWidth="880px"
              rowKey={(rule) => rule.rule_id}
              status={rules.isLoading ? 'loading' : ruleList.length === 0 ? 'empty' : 'idle'}
              empty={{
                icon: Shield,
                title: 'No rules published',
                description: 'Rules appear here once the catalog is seeded.',
              }}
            />
          </Section>

          <p className="mt-6 text-center text-small text-re-text-tertiary">
            Report generated at {new Date(s.generated_at).toLocaleString()}
          </p>
        </>
      ) : null}
    </PageContainer>
  );
}
