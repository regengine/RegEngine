'use client';

import { useState } from 'react';
import { DemoBanner } from '@/components/control-plane/demo-banner';
import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import { useQuery } from '@tanstack/react-query';

import {
  CheckCircle,
  Circle,
  Flag,
  Rocket,
  Shield,
  Target,
  TrendingUp,
  XCircle,
} from 'lucide-react';

const INGESTION_API = '/api/ingestion';

const LEVEL_CONFIG: Record<number, { icon: any; color: string; bgColor: string }> = {
  0: { icon: Circle, color: 'text-gray-400', bgColor: 'bg-gray-100' },
  1: { icon: Rocket, color: 'text-blue-500', bgColor: 'bg-blue-50' },
  2: { icon: Shield, color: 'text-amber-500', bgColor: 'bg-amber-50' },
  3: { icon: Target, color: 'text-purple-500', bgColor: 'bg-purple-50' },
  4: { icon: TrendingUp, color: 'text-indigo-500', bgColor: 'bg-indigo-50' },
  5: { icon: Flag, color: 'text-green-600', bgColor: 'bg-green-50' },
};

// Demo fallback
const DEMO_ASSESSMENT = {
  maturity_level: 3,
  maturity_name: 'Operational',
  maturity_description: 'Request workflow tested, packages assembled',
  maturity_color: 'purple',
  overall_score: 60,
  items_completed: 12,
  items_total: 20,
  next_steps: [
    { id: 'chain_integrity', level: 4, title: 'Hash chain verified', description: 'Hash chain integrity verification passes with no errors', category: 'integrity', passed: false },
    { id: 'pass_rate_90', level: 4, title: '90% rule pass rate', description: 'Overall rule evaluation pass rate above 90%', category: 'rules', passed: false },
    { id: 'identity_resolved', level: 4, title: 'Entity identity resolved', description: 'Canonical entities registered with no pending ambiguous reviews', category: 'identity', passed: false },
  ],
  levels: {
    0: { name: 'Not Started', description: 'No traceability records in system', color: 'gray' },
    1: { name: 'Ingesting', description: 'Records flowing in, building coverage', color: 'blue' },
    2: { name: 'Validating', description: 'Rules engine active, exceptions managed', color: 'amber' },
    3: { name: 'Operational', description: 'Request workflow tested, packages assembled', color: 'purple' },
    4: { name: 'Audit-Ready', description: 'Full provenance, chain integrity verified', color: 'indigo' },
    5: { name: 'Compliant', description: '24-hour response demonstrated, all CTEs covered', color: 'green' },
  },
};

const DEMO_CHECKLIST = {
  checklist_by_level: {
    1: { level_info: { name: 'Ingesting' }, items: [
      { id: 'ingest_records', title: 'Ingest traceability records', passed: true },
      { id: 'multiple_sources', title: 'Multiple ingestion sources', passed: true },
      { id: 'cte_coverage', title: 'CTE type coverage', passed: true },
      { id: 'facility_identifiers', title: 'Facility identifiers (GLN)', passed: true },
    ], completed: 4, total: 4 },
    2: { level_info: { name: 'Validating' }, items: [
      { id: 'rules_seeded', title: 'Compliance rules loaded', passed: true },
      { id: 'rules_evaluated', title: 'Events evaluated against rules', passed: true },
      { id: 'pass_rate_70', title: '70% rule pass rate', passed: true },
      { id: 'exceptions_managed', title: 'Exceptions being managed', passed: true },
    ], completed: 4, total: 4 },
    3: { level_info: { name: 'Operational' }, items: [
      { id: 'request_case_created', title: 'Request case tested', passed: true },
      { id: 'package_assembled', title: 'Response package assembled', passed: true },
      { id: 'signoff_chain', title: 'Signoff chain tested', passed: true },
      { id: 'fda_export_generated', title: 'FDA export generated', passed: true },
    ], completed: 4, total: 4 },
    4: { level_info: { name: 'Audit-Ready' }, items: [
      { id: 'chain_integrity', title: 'Hash chain verified', passed: false },
      { id: 'provenance_complete', title: 'Full provenance chain', passed: true },
      { id: 'pass_rate_90', title: '90% rule pass rate', passed: false },
      { id: 'identity_resolved', title: 'Entity identity resolved', passed: false },
    ], completed: 1, total: 4 },
    5: { level_info: { name: 'Compliant' }, items: [
      { id: 'request_submitted', title: 'Request case submitted', passed: true },
      { id: 'all_ctes_covered', title: 'All 7 CTE types covered', passed: false },
      { id: 'no_critical_exceptions', title: 'No critical blocking exceptions', passed: false },
      { id: 'pass_rate_95', title: '95% rule pass rate', passed: false },
    ], completed: 1, total: 4 },
  },
};

export default function ReadinessWizardPage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';
  const [isDemo, setIsDemo] = useState(false);

  const assessment = useQuery({
    queryKey: ['readiness', 'assessment', tid],
    queryFn: async () => {
      try {
        const res = await fetch(`${INGESTION_API}/api/v1/readiness/assessment?tenant_id=${tid}`, {
          headers: { 'X-RegEngine-API-Key': apiKey || '' },
        });
        if (!res.ok) throw new Error();
        setIsDemo(false);
        return res.json();
      } catch { setIsDemo(true); return DEMO_ASSESSMENT; }
    },
    staleTime: 60_000,
  });

  const checklist = useQuery({
    queryKey: ['readiness', 'checklist', tid],
    queryFn: async () => {
      try {
        const res = await fetch(`${INGESTION_API}/api/v1/readiness/checklist?tenant_id=${tid}`, {
          headers: { 'X-RegEngine-API-Key': apiKey || '' },
        });
        if (!res.ok) throw new Error();
        setIsDemo(false);
        return res.json();
      } catch { setIsDemo(true); return DEMO_CHECKLIST; }
    },
    staleTime: 60_000,
  });

  const a = assessment.data;
  const cl = checklist.data?.checklist_by_level;

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Target className="h-6 w-6 text-purple-500" />
            Readiness Assessment
          </h1>
          <p className="text-muted-foreground mt-1">
            How ready are you for FSMA 204 compliance? Step-by-step evaluation against actual data.
          </p>
        </div>
      </div>

      <DemoBanner visible={isDemo} />

      {!a ? (
        <div className="space-y-4">{[1,2,3].map(i => <Skeleton key={i} className="h-40" />)}</div>
      ) : (
        <>
          {/* Maturity Level Hero */}
          <Card className="mb-8">
            <CardContent className="pt-6 pb-6">
              <div className="flex flex-col md:flex-row items-center gap-6">
                <div className={`w-24 h-24 rounded-full flex items-center justify-center ${LEVEL_CONFIG[a.maturity_level]?.bgColor || 'bg-gray-100'}`}>
                  <span className={`text-4xl font-bold ${LEVEL_CONFIG[a.maturity_level]?.color || 'text-gray-400'}`}>
                    {a.maturity_level}
                  </span>
                </div>
                <div className="flex-1 text-center md:text-left">
                  <h2 className="text-2xl font-bold">{a.maturity_name}</h2>
                  <p className="text-muted-foreground">{a.maturity_description}</p>
                  <div className="mt-3">
                    <Progress value={a.overall_score} className="h-3" />
                    <p className="text-sm text-muted-foreground mt-1">
                      {a.items_completed} of {a.items_total} requirements met ({a.overall_score}%)
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Level Progress Dots */}
          <div className="flex justify-center gap-2 mb-8">
            {[0, 1, 2, 3, 4, 5].map(level => {
              const config = LEVEL_CONFIG[level];
              const Icon = config.icon;
              const isComplete = level <= a.maturity_level;
              const isCurrent = level === a.maturity_level;
              return (
                <div
                  key={level}
                  className={`flex flex-col items-center gap-1 px-3 py-2 rounded-lg ${
                    isCurrent ? `${config.bgColor} border-2 border-current ${config.color}` :
                    isComplete ? 'bg-green-50' : 'bg-muted/30'
                  }`}
                >
                  <Icon className={`h-5 w-5 ${isComplete ? 'text-green-500' : 'text-muted-foreground'}`} />
                  <span className="text-xs font-medium">{level}</span>
                </div>
              );
            })}
          </div>

          {/* Next Steps */}
          {a.next_steps && a.next_steps.length > 0 && (
            <Card className="mb-8 border-amber-200">
              <CardHeader>
                <CardTitle className="text-lg">Next Steps to Level {a.maturity_level + 1}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {a.next_steps.map((step: any) => (
                    <div key={step.id} className="flex items-start gap-3 p-2 rounded border">
                      <XCircle className="h-5 w-5 text-red-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="font-medium text-sm">{step.title}</p>
                        <p className="text-xs text-muted-foreground">{step.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Full Checklist */}
          {cl && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Full Compliance Checklist</h2>
              {Object.entries(cl).map(([levelStr, levelData]: [string, any]) => {
                const level = parseInt(levelStr);
                const config = LEVEL_CONFIG[level];
                const Icon = config?.icon || Circle;
                const allComplete = levelData.completed === levelData.total;

                return (
                  <Card key={level} className={allComplete ? 'border-green-200' : ''}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Icon className={`h-5 w-5 ${config?.color || 'text-gray-400'}`} />
                        Level {level}: {levelData.level_info.name}
                        <Badge variant={allComplete ? 'default' : 'outline'} className="ml-auto text-xs">
                          {levelData.completed}/{levelData.total}
                        </Badge>
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-1">
                        {levelData.items.map((item: any) => (
                          <div key={item.id} className="flex items-center gap-2 py-1 text-sm">
                            {item.passed ? (
                              <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                            ) : (
                              <Circle className="h-4 w-4 text-muted-foreground shrink-0" />
                            )}
                            <span className={item.passed ? '' : 'text-muted-foreground'}>{item.title}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}
    </PageContainer>
  );
}
