'use client';

import { useRef, useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { fieldControlClasses } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

import { useAuth } from '@/lib/auth-context';
import {
  useExceptions,
  useBlockingExceptionCount,
  useResolveException,
  useWaiveException,
  useAssignException,
} from '@/hooks/use-control-plane';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Filter,
  User,
} from 'lucide-react';

const SEVERITY_BADGE: Record<string, { tone: BadgeTone; label: string }> = {
  critical: { tone: 'danger', label: 'Critical' },
  warning: { tone: 'warning', label: 'Warning' },
  info: { tone: 'info', label: 'Info' },
};

/** Exception lifecycle mapped onto the shared compliance-state vocabulary. */
const STATUS_BADGE: Record<string, { state: ComplianceState; label: string }> = {
  open: { state: 'non-compliant', label: 'Open' },
  in_review: { state: 'in-progress', label: 'In Review' },
  awaiting_supplier: { state: 'needs-correction', label: 'Awaiting Supplier' },
  resolved: { state: 'compliant', label: 'Resolved' },
  waived: { state: 'unknown', label: 'Waived' },
};

const FILTER_SELECT = 'h-8 w-auto max-w-[12rem] py-0 pr-8 text-small';

interface ExceptionRow {
  case_id: string;
  severity: string;
  status: string;
  rule_category?: string | null;
  source_supplier?: string | null;
  owner_user_id?: string | null;
  due_date?: string | null;
  recommended_remediation?: string | null;
}

export default function ExceptionQueuePage() {
  const { tenantId, user } = useAuth();
  const tid = tenantId || '';
  const actor = user?.email || user?.id || 'unknown';

  const [severityFilter, setSeverityFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [supplierFilter, setSupplierFilter] = useState('');

  const exceptions = useExceptions(tid, {
    severity: severityFilter,
    status: statusFilter,
    source_supplier: supplierFilter || undefined,
  });
  const blocking = useBlockingExceptionCount(tid);
  const resolveException = useResolveException(tid);
  const waiveException = useWaiveException(tid);
  const assignException = useAssignException(tid);

  const [decision, setDecision] = useState<{ caseId: string; action: 'resolve' | 'waive' } | null>(null);
  const [reason, setReason] = useState('');
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const openDecision = (caseId: string, action: 'resolve' | 'waive') => {
    setDecision({ caseId, action }); setReason(''); setDecisionError(null);
  };
  const confirmDecision = async () => {
    if (!decision || !reason.trim() || submittingRef.current) return;
    submittingRef.current = true; setSubmitting(true); setDecisionError(null);
    try {
      if (decision.action === 'resolve') await resolveException.mutateAsync({ caseId: decision.caseId, resolutionSummary: reason.trim(), resolvedBy: actor });
      else await waiveException.mutateAsync({ caseId: decision.caseId, waiverReason: reason.trim(), waiverApprovedBy: actor });
      setDecision(null); setReason('');
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : 'Unable to save decision. Retry after reviewing the current case.');
    } finally { submittingRef.current = false; setSubmitting(false); }
  };
  const blockingCount = blocking.error ? undefined : blocking.data?.blocking_count;
  const cases = (exceptions.data?.cases ?? []) as ExceptionRow[];

  const pageHeader = (
    <PageHeader
      title="Exception Queue"
      description="Manage compliance exceptions — resolve defects before they block response packages"
      meta={
        blockingCount === undefined ? (
          <StatusBadge state="unknown" label="Blockers unavailable" />
        ) : blockingCount > 0 ? (
          <StatusBadge state="blocked" label={`${blockingCount} Blocking`} />
        ) : (
          <StatusBadge state="compliant" label="No Blockers" />
        )
      }
    />
  );


  if (exceptions.error) {
    return (
      <PageContainer>
        {pageHeader}
        <Callout
          tone="danger"
          role="alert"
          title="Unable to load data from the control plane API."
          action={
            <Button variant="secondary" size="sm" onClick={() => exceptions.refetch()}>
              Retry
            </Button>
          }
        >
          {(exceptions.error as Error).message}
        </Callout>
      </PageContainer>
    );
  }

  const columns: DataTableColumn<ExceptionRow>[] = [
    {
      key: 'severity',
      header: 'Severity',
      width: '6.5rem',
      cell: (exc) => {
        const sev = SEVERITY_BADGE[exc.severity] || SEVERITY_BADGE.info;
        return <Badge tone={sev.tone} size="sm">{sev.label}</Badge>;
      },
    },
    {
      key: 'status',
      header: 'Status',
      width: '9.5rem',
      cell: (exc) => {
        const stat = STATUS_BADGE[exc.status] || STATUS_BADGE.open;
        return <StatusBadge state={stat.state} label={stat.label} size="sm" className="whitespace-nowrap" />;
      },
    },
    {
      key: 'rule_category',
      header: 'Category',
      width: '7.5rem',
      cell: (exc) => (
        <span className="text-re-text-secondary">{exc.rule_category?.replace(/_/g, ' ') || '-'}</span>
      ),
    },
    {
      key: 'source_supplier',
      header: 'Supplier',
      width: '8.5rem',
      cell: (exc) => (
        <span className="block max-w-[12ch] truncate" title={exc.source_supplier || undefined}>
          {exc.source_supplier || '-'}
        </span>
      ),
    },
    {
      key: 'owner_user_id',
      header: 'Owner',
      width: '9rem',
      cell: (exc) =>
        exc.owner_user_id ? (
          <span className="flex items-center gap-1.5 text-re-text-secondary" title={exc.owner_user_id}>
            <User className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
            <span className="max-w-[11ch] truncate">{exc.owner_user_id}</span>
          </span>
        ) : (
          <span className="text-re-text-muted">Unassigned</span>
        ),
    },
    {
      key: 'due_date',
      header: 'Due',
      width: '7rem',
      cell: (exc) => {
        const isOverdue = exc.due_date && new Date(exc.due_date) < new Date();
        if (!exc.due_date) return <span className="text-re-text-muted">-</span>;
        return (
          <span className={cn('flex items-center gap-1.5', isOverdue && 'font-medium text-re-danger')}>
            {isOverdue && (
              <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
            )}
            {new Date(exc.due_date).toLocaleDateString()}
          </span>
        );
      },
    },
    {
      key: 'recommended_remediation',
      header: 'Remediation',
      cell: (exc) => (
        <span
          className="block max-w-[14ch] truncate text-re-text-tertiary xl:max-w-[22ch]"
          title={exc.recommended_remediation || undefined}
        >
          {exc.recommended_remediation || '-'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      width: '11rem',
      cell: (exc) => {
        const isActive = exc.status !== 'resolved' && exc.status !== 'waived';
        if (!isActive) return null;
        return (
          <div className="flex justify-end gap-1">
            <Button
              size="sm"
              variant="secondary"
              disabled={submitting}
              onClick={() => openDecision(exc.case_id, 'resolve')}
            >
              Resolve
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={submitting}
              onClick={() => openDecision(exc.case_id, 'waive')}
            >
              Waive
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <PageContainer>
      {pageHeader}
      <Dialog open={!!decision} onOpenChange={(open) => { if (!open && !submittingRef.current) setDecision(null); }}>
        <DialogContent>
          <DialogTitle>{decision?.action === 'waive' ? 'Waive' : 'Resolve'} exception {decision?.caseId}</DialogTitle>
          <DialogDescription>Document the evidence and rationale for this specific case before signing off.</DialogDescription>
          <label htmlFor="exception-reason">Case-specific reason</label>
          <textarea id="exception-reason" className={fieldControlClasses} value={reason} disabled={submitting} onChange={e => setReason(e.target.value)} />
          {decisionError && <Callout tone="danger" role="alert">{decisionError}</Callout>}
          <Button disabled={!reason.trim() || submitting} onClick={confirmDecision}>{submitting ? 'Saving…' : `Confirm ${decision?.action}`}</Button>
        </DialogContent>
      </Dialog>
      {blocking.error && <Callout tone="warning" role="alert" action={<Button onClick={() => blocking.refetch()}>Retry blocker count</Button>}>Blocking status could not be assessed.</Callout>}

      <DemoBanner visible={!!(exceptions.data?.__isDemo)} />

      <div className="mb-6 mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Open" value={cases.filter(c => c.status === 'open').length} />
        <StatTile label="In Review" value={cases.filter(c => c.status === 'in_review').length} />
        <StatTile
          label="Awaiting Supplier"
          value={cases.filter(c => c.status === 'awaiting_supplier').length}
        />
        <StatTile
          label="Resolved"
          value={cases.filter(c => c.status === 'resolved' || c.status === 'waived').length}
        />
      </div>

      <Section
        spacing="app"
        title="Exception Cases"
        description={exceptions.isLoading ? 'Loading...' : `${cases.length} cases`}
      >
        <DataTable
          caption="Compliance exception cases"
          columns={columns}
          data={cases}
          minWidth="920px"
          stickyFirstColumn
          rowKey={(exc) => exc.case_id}
          status={exceptions.isLoading ? 'loading' : cases.length === 0 ? 'empty' : 'idle'}
          empty={{
            icon: CheckCircle,
            title: 'No exceptions found',
            description: 'No cases match the current filters',
          }}
          toolbar={{
            search: {
              placeholder: 'Filter by supplier...',
              value: supplierFilter,
              onChange: setSupplierFilter,
              label: 'Filter by supplier',
            },
            filters: (
              <>
                <Filter className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                <label htmlFor="exceptions-severity-filter" className="sr-only">
                  Filter by severity
                </label>
                <select
                  id="exceptions-severity-filter"
                  className={cn(fieldControlClasses, FILTER_SELECT)}
                  value={severityFilter || ''}
                  onChange={e => setSeverityFilter(e.target.value || undefined)}
                >
                  <option value="">All Severities</option>
                  <option value="critical">Critical</option>
                  <option value="warning">Warning</option>
                  <option value="info">Info</option>
                </select>
                <label htmlFor="exceptions-status-filter" className="sr-only">
                  Filter by status
                </label>
                <select
                  id="exceptions-status-filter"
                  className={cn(fieldControlClasses, FILTER_SELECT)}
                  value={statusFilter || ''}
                  onChange={e => setStatusFilter(e.target.value || undefined)}
                >
                  <option value="">All Statuses</option>
                  <option value="open">Open</option>
                  <option value="in_review">In Review</option>
                  <option value="awaiting_supplier">Awaiting Supplier</option>
                  <option value="resolved">Resolved</option>
                  <option value="waived">Waived</option>
                </select>
              </>
            ),
          }}
        />
      </Section>
    </PageContainer>
  );
}
