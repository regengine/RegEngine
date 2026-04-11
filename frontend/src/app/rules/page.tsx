'use client';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';

import { useAuth } from '@/lib/auth-context';
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

const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: LucideIcon }> = {
  kde_presence: { label: 'KDE Presence', color: 'text-re-danger', icon: AlertTriangle },
  temporal_ordering: { label: 'Temporal Ordering', color: 'text-re-info', icon: Zap },
  lot_linkage: { label: 'Lot Linkage', color: 'text-purple-500', icon: Scale },
  source_reference: { label: 'Source Reference', color: 'text-re-warning', icon: BookOpen },
  identifier_format: { label: 'Identifier Format', color: 'text-cyan-500', icon: Shield },
  quantity_consistency: { label: 'Quantity', color: 'text-re-success', icon: CheckCircle },
  entity_resolution: { label: 'Entity Resolution', color: 'text-indigo-500', icon: Shield },
  record_completeness: { label: 'Completeness', color: 'text-orange-500', icon: CheckCircle },
  chain_integrity: { label: 'Chain Integrity', color: 'text-slate-500', icon: Shield },
};

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };

export default function RulesDashboardPage() {
  const { apiKey } = useAuth();

  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [severityFilter, setSeverityFilter] = useState<string | undefined>();

  const rules = useRules();
  const seedRules = useSeedRules();

  const ruleList = rules.data?.rules ?? [];

  if (rules.error) {
    return (
      <PageContainer>
        <div className="p-8 text-center">
          <p className="text-muted-foreground">Unable to load data from the control plane API.</p>
          <p className="text-sm text-muted-foreground/60 mt-2">{(rules.error as Error).message}</p>
          <button onClick={() => rules.refetch()} className="mt-4 text-sm text-primary hover:underline">
            Retry
          </button>
        </div>
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

  return (
    <PageContainer>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Scale className="h-6 w-6 text-re-info" />
            Compliance Rules
          </h1>
          <p className="text-muted-foreground mt-1">
            Versioned FSMA 204 compliance rules — every rule is citable, explainable, and independently deployable
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => seedRules.mutate()}
            disabled={seedRules.isPending}
          >
            {seedRules.isPending ? 'Seeding...' : 'Seed Rules'}
          </Button>
          <Badge variant="outline" className="text-sm px-3 py-1">
            {ruleList.length} rules
          </Badge>
        </div>
      </div>

      <DemoBanner visible={!!(rules.data?.__isDemo)} />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Total Rules</p>
            <p className="text-3xl font-bold">{ruleList.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Critical</p>
            <p className="text-3xl font-bold text-re-danger">{criticalCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Warning</p>
            <p className="text-3xl font-bold text-re-warning">{warningCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">Categories</p>
            <p className="text-3xl font-bold text-re-info">{categories.length}</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <select
              className="text-sm border rounded px-2 py-1.5 bg-background"
              value={severityFilter || ''}
              onChange={e => setSeverityFilter(e.target.value || undefined)}
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
            <select
              className="text-sm border rounded px-2 py-1.5 bg-background"
              value={categoryFilter || ''}
              onChange={e => setCategoryFilter(e.target.value || undefined)}
            >
              <option value="">All Categories</option>
              {Object.entries(CATEGORY_CONFIG).map(([key, config]) => (
                <option key={key} value={key}>{config.label}</option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">
              Showing {filtered.length} of {ruleList.length}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Rule List */}
      <div className="space-y-3">
        {rules.isLoading ? (
          [1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-28 w-full" />)
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              <Scale className="h-12 w-12 mx-auto mb-3 text-re-text-secondary" />
              <p className="font-medium">No rules found</p>
              <p className="text-sm">
                {ruleList.length === 0
                  ? 'Click "Seed Rules" to load the 25 built-in FSMA rules'
                  : 'Adjust filters to see matching rules'}
              </p>
            </CardContent>
          </Card>
        ) : (
          filtered.map((rule: RuleDefinition) => {
            const catConfig = CATEGORY_CONFIG[rule.category] || CATEGORY_CONFIG.kde_presence;
            const CatIcon = catConfig.icon;

            return (
              <Card key={rule.rule_id}>
                <CardContent className="pt-4 pb-4">
                  <div className="flex items-start gap-3">
                    {/* Severity indicator */}
                    <div className={`mt-0.5 ${rule.severity === 'critical' ? 'text-re-danger' : rule.severity === 'warning' ? 'text-re-warning' : 'text-re-info'}`}>
                      {rule.severity === 'critical' ? <XCircle className="h-5 w-5" /> :
                       rule.severity === 'warning' ? <AlertTriangle className="h-5 w-5" /> :
                       <CheckCircle className="h-5 w-5" />}
                    </div>

                    {/* Content */}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm">{rule.title}</span>
                        <Badge
                          variant={rule.severity === 'critical' ? 'destructive' : rule.severity === 'warning' ? 'warning' : 'secondary'}
                          className="text-xs"
                        >
                          {rule.severity}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          <CatIcon className={`h-3 w-3 mr-0.5 ${catConfig.color}`} />
                          {catConfig.label}
                        </Badge>
                      </div>

                      {rule.citation_reference && (
                        <p className="text-xs text-re-info mt-1 font-mono">
                          {rule.citation_reference}
                        </p>
                      )}

                      {rule.remediation_suggestion && (
                        <p className="text-xs text-muted-foreground mt-1 italic">
                          Remediation: {rule.remediation_suggestion}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </PageContainer>
  );
}
