'use client';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { fieldControlClasses } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { cn } from '@/lib/utils';

import { useRules, useSeedRules, type RuleDefinition } from '@/hooks/use-control-plane';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  AlertTriangle,
  BookOpen,
  CheckCircle,
  Filter,
  type LucideIcon,
  Scale,
  Shield,
  XCircle,
  Zap,
} from 'lucide-react';
import { NOT_SET } from '@/lib/empty-values';

/**
 * Category accent uses the categorical token ramp (--re-cat-1..6): a rule's
 * category is a *kind*, not a state, so it must not borrow the status palette.
 */
const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: LucideIcon }> = {
  kde_presence: { label: 'KDE Presence', color: 'text-re-cat-1', icon: AlertTriangle },
  temporal_ordering: { label: 'Temporal Ordering', color: 'text-re-cat-2', icon: Zap },
  lot_linkage: { label: 'Lot Linkage', color: 'text-re-cat-3', icon: Scale },
  source_reference: { label: 'Source Reference', color: 'text-re-cat-4', icon: BookOpen },
  identifier_format: { label: 'Identifier Format', color: 'text-re-cat-5', icon: Shield },
  quantity_consistency: { label: 'Quantity', color: 'text-re-cat-6', icon: CheckCircle },
  entity_resolution: { label: 'Entity Resolution', color: 'text-re-cat-1', icon: Shield },
  record_completeness: { label: 'Completeness', color: 'text-re-cat-2', icon: CheckCircle },
  chain_integrity: { label: 'Chain Integrity', color: 'text-re-cat-3', icon: Shield },
};

/** Severity is a state: icon + label + tone, never colour alone. */
const SEVERITY_CONFIG: Record<string, { tone: BadgeTone; icon: LucideIcon }> = {
  critical: { tone: 'danger', icon: XCircle },
  warning: { tone: 'warning', icon: AlertTriangle },
  info: { tone: 'info', icon: CheckCircle },
};

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };

const FILTER_SELECT = 'h-8 w-auto max-w-[12rem] py-0 pr-8 text-small';

export default function RulesDashboardPage() {
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [severityFilter, setSeverityFilter] = useState<string | undefined>();

  const rules = useRules();
  const seedRules = useSeedRules();

  const ruleList = rules.data?.rules ?? [];

  const pageHeader = (
    <PageHeader
      title="Compliance Rules"
      description="Versioned FSMA 204 compliance rules — every rule is citable, explainable, and independently deployable"
      meta={!rules.error && rules.data ? <Badge>{ruleList.length} rules</Badge> : undefined}
      primaryAction={!rules.error ? (
        <Button onClick={() => seedRules.mutate()} disabled={seedRules.isPending}>
          {seedRules.isPending ? 'Loading...' : 'Load Rules'}
        </Button>
      ) : undefined}
    />
  );

  if (rules.error) {
    return (
      <PageContainer className="workspace-load-error">
        {pageHeader}
        <Callout
          tone="danger"
          role="alert"
          title="Unable to load data from the control plane API."
          action={
            <Button variant="secondary" size="sm" onClick={() => rules.refetch()}>
              Retry
            </Button>
          }
        >
          {(rules.error as Error).message}
        </Callout>
      </PageContainer>
    );
  }

  // Apply filters
  const filtered = ruleList.filter((r: RuleDefinition) => {
    if (categoryFilter && r.category !== categoryFilter) return false;
    if (severityFilter && r.severity !== severityFilter) return false;
    return true;
  }).sort((a: RuleDefinition, b: RuleDefinition) => {
    const sa = SEVERITY_ORDER[a.severity as keyof typeof SEVERITY_ORDER] ?? 9;
    const sb = SEVERITY_ORDER[b.severity as keyof typeof SEVERITY_ORDER] ?? 9;
    return sa - sb;
  });

  // Stats
  const criticalCount = ruleList.filter((r: RuleDefinition) => r.severity === 'critical').length;
  const warningCount = ruleList.filter((r: RuleDefinition) => r.severity === 'warning').length;
  const categories = [...new Set(ruleList.map((r: RuleDefinition) => r.category))];

  const columns: DataTableColumn<RuleDefinition>[] = [
    {
      key: 'severity',
      header: 'Severity',
      width: '8.5rem',
      cell: (rule) => {
        const config = SEVERITY_CONFIG[rule.severity] ?? SEVERITY_CONFIG.info;
        const SeverityIcon = config.icon;
        return (
          <Badge tone={config.tone} size="sm">
            <SeverityIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            {rule.severity}
          </Badge>
        );
      },
    },
    {
      key: 'title',
      header: 'Rule',
      cell: (rule) => <span className="font-medium text-re-text-primary">{rule.title}</span>,
    },
    {
      key: 'category',
      header: 'Category',
      width: '12rem',
      cell: (rule) => {
        const catConfig = CATEGORY_CONFIG[rule.category] || CATEGORY_CONFIG.kde_presence;
        const CatIcon = catConfig.icon;
        return (
          <Badge size="sm">
            <CatIcon
              className={cn('h-3.5 w-3.5', catConfig.color)}
              strokeWidth={1.75}
              aria-hidden="true"
            />
            {catConfig.label}
          </Badge>
        );
      },
    },
    {
      key: 'citation_reference',
      header: 'Citation',
      mono: true,
      width: '12rem',
      cell: (rule) => (
        <span className="text-re-text-secondary">{rule.citation_reference || NOT_SET}</span>
      ),
    },
    {
      key: 'remediation_suggestion',
      header: 'Remediation',
      cell: (rule) => (
        <span className="text-re-text-tertiary">{rule.remediation_suggestion || NOT_SET}</span>
      ),
    },
  ];

  return (
    <PageContainer>
      {pageHeader}

      <DemoBanner visible={!!(rules.data?.__isDemo)} />

      <div className="mb-6 mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Total Rules" value={ruleList.length} />
        <StatTile label="Critical" value={criticalCount} />
        <StatTile label="Warning" value={warningCount} />
        <StatTile label="Categories" value={categories.length} />
      </div>

      <DataTable
        caption="Compliance rule catalog"
        columns={columns}
        data={filtered}
        minWidth="900px"
        rowKey={(rule) => rule.rule_id}
        status={rules.isLoading ? 'loading' : filtered.length === 0 ? 'empty' : 'idle'}
        empty={{
          icon: Scale,
          title: 'No rules found',
          description:
            ruleList.length === 0
              ? 'Click "Load Rules" to load the 36 built-in FSMA 204 rules'
              : 'Adjust filters to see matching rules',
        }}
        toolbar={{
          filters: (
            <>
              <Filter className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
              <label htmlFor="rules-severity-filter" className="sr-only">
                Filter by severity
              </label>
              <select
                id="rules-severity-filter"
                className={cn(fieldControlClasses, FILTER_SELECT)}
                value={severityFilter || ''}
                onChange={e => setSeverityFilter(e.target.value || undefined)}
              >
                <option value="">All Severities</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
              <label htmlFor="rules-category-filter" className="sr-only">
                Filter by category
              </label>
              <select
                id="rules-category-filter"
                className={cn(fieldControlClasses, FILTER_SELECT)}
                value={categoryFilter || ''}
                onChange={e => setCategoryFilter(e.target.value || undefined)}
              >
                <option value="">All Categories</option>
                {Object.entries(CATEGORY_CONFIG).map(([key, config]) => (
                  <option key={key} value={key}>{config.label}</option>
                ))}
              </select>
              <span className="text-small text-re-text-tertiary">
                Showing {filtered.length} of {ruleList.length}
              </span>
            </>
          ),
        }}
      />
    </PageContainer>
  );
}
