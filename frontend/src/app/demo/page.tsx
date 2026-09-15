'use client';

import Link from 'next/link';
import {
  ShieldAlert, Clock, Truck, Leaf, Package, Anchor,
  Building2, ArrowRight, BarChart3, Users, FileText, Zap,
} from 'lucide-react';
import { DemoBanner } from '@/components/control-plane/demo-banner';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';

// ---------------------------------------------------------------------------
// Synthetic demo data — what a mid-market produce distributor would see
// ---------------------------------------------------------------------------

const COMPLIANCE_SCORE = 94.2;
const TOTAL_EVENTS = 12847;
const COMPLIANT_EVENTS = 12102;
const NON_COMPLIANT_EVENTS = 745;
const SUPPLIERS = 23;
const FACILITIES = 3;

const RECENT_EVENTS = [
  { tlc: 'RVF-ROM-041426-F3-001', cte: 'harvesting', product: 'RM HRTS 3PK 24CT', supplier: 'Rio Verde Farms', status: 'compliant', time: '2h ago' },
  { tlc: 'VFP-SPIN5-041426-001', cte: 'initial_packing', product: 'BABY SPINACH 5OZ CLAM', supplier: 'Valley Fresh Packhouse', status: 'compliant', time: '3h ago' },
  { tlc: 'FL-SHIP-041426-088', cte: 'shipping', product: 'RM HRTS 3PK 24CT', supplier: 'FreshLine Distribution', status: 'non_compliant', time: '4h ago' },
  { tlc: 'MG-RECV-041426-201', cte: 'receiving', product: 'ORG CURLY KALE 1# BAG', supplier: 'Metro Grocery DC', status: 'compliant', time: '5h ago' },
  { tlc: 'GL-CHPROM-041426-A', cte: 'transformation', product: 'CHOPPED ROMAINE 1# BAG', supplier: 'GreenLeaf Processing', status: 'non_compliant', time: '6h ago' },
  { tlc: 'RVF-KALE-041426-F1-002', cte: 'harvesting', product: 'CURLY KALE 24CT', supplier: 'Rio Verde Farms', status: 'compliant', time: '6h ago' },
  { tlc: 'ACS-COOL-041426-007', cte: 'cooling', product: 'BABY SPINACH BULK 20#', supplier: 'Arctic Chain Cold Storage', status: 'compliant', time: '7h ago' },
  { tlc: 'VFP-CIL-041426-001', cte: 'initial_packing', product: 'CILANTRO BNCH 60CT', supplier: 'Valley Fresh Packhouse', status: 'compliant', time: '8h ago' },
];

const RULE_VIOLATIONS = [
  { rule: 'Shipping: Ship-To Location Required', count: 12, severity: 'critical', cte: 'shipping' },
  { rule: 'Receiving: TLC Source Reference Required', count: 8, severity: 'critical', cte: 'receiving' },
  { rule: 'Reference Document Required for All CTEs', count: 15, severity: 'warning', cte: 'all' },
  { rule: 'Transformation: Input TLCs Required', count: 5, severity: 'critical', cte: 'transformation' },
  { rule: 'Receiving: Immediate Previous Source Required', count: 3, severity: 'critical', cte: 'receiving' },
];

const SUPPLIER_SCORES = [
  { name: 'Rio Verde Farms', score: 98.5, events: 3200, status: 'excellent' },
  { name: 'Valley Fresh Packhouse', score: 96.1, events: 2800, status: 'excellent' },
  { name: 'Arctic Chain Cold Storage', score: 94.8, events: 1200, status: 'good' },
  { name: 'FreshLine Distribution', score: 87.3, events: 2400, status: 'needs_attention' },
  { name: 'GreenLeaf Processing', score: 82.1, events: 1800, status: 'at_risk' },
];

const CTE_BREAKDOWN = [
  { cte: 'Harvesting', icon: Leaf, count: 3420, compliant: 3388, pct: 99.1 },
  { cte: 'Cooling', icon: Clock, count: 1856, compliant: 1820, pct: 98.1 },
  { cte: 'Initial Packing', icon: Package, count: 2104, compliant: 2055, pct: 97.7 },
  { cte: 'Shipping', icon: Truck, count: 2680, compliant: 2450, pct: 91.4 },
  { cte: 'Receiving', icon: Building2, count: 2187, compliant: 1989, pct: 90.9 },
  { cte: 'Transformation', icon: Zap, count: 480, compliant: 400, pct: 83.3 },
  { cte: 'FLBR', icon: Anchor, count: 120, compliant: 120, pct: 100 },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const SUPPLIER_STATE: Record<string, ComplianceState> = {
  excellent: 'compliant',
  good: 'compliant',
  needs_attention: 'at-risk',
  at_risk: 'non-compliant',
};

/** Coverage bar tone. The number beside it carries the same meaning in text. */
function coverageTone(pct: number) {
  if (pct >= 95) return 'bg-re-success';
  if (pct >= 90) return 'bg-re-warning';
  return 'bg-re-danger';
}

export default function DemoPage() {
  return (
    <Container width="app" className="py-8">
      <div className="mb-6">
        <DemoBanner visible={true} />
      </div>
      {/* Page header */}
      <PageHeader
        title="Compliance Dashboard"
        description={
          <>
            DEMO WORKSPACE &mdash; FreshCo Distribution is a fictional distributor. Numbers are illustrative.
          </>
        }
      />

      {/* Top stats row */}
      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="FSMA Readiness Score" value={`${COMPLIANCE_SCORE}%`} />
        <StatTile label="Total Events" value={TOTAL_EVENTS.toLocaleString()} />
        <StatTile label="Active Suppliers" value={String(SUPPLIERS)} />
        <StatTile label="Open Violations" value={String(NON_COMPLIANT_EVENTS)} />
      </div>

      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* CTE Breakdown */}
        <Card padding="spacious" className="lg:col-span-2">
          <h2 className="mb-4 flex items-center gap-2 text-subheading text-re-text-primary">
            <BarChart3 className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Compliance by CTE Type
          </h2>
          <ul className="space-y-3">
            {CTE_BREAKDOWN.map((cte) => (
              <li key={cte.cte} className="flex items-center gap-3">
                <cte.icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <span className="w-28 shrink-0 text-ui text-re-text-secondary">{cte.cte}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-re-surface-inset">
                  <div
                    className={`h-full rounded-full ${coverageTone(cte.pct)}`}
                    style={{ width: `${cte.pct}%` }}
                  />
                </div>
                <span className="w-12 shrink-0 text-right font-mono text-ui tabular-nums text-re-text-secondary">
                  {cte.pct}%
                </span>
                <span className="hidden w-24 shrink-0 text-right font-mono text-label tabular-nums text-re-text-muted sm:block">
                  {cte.count.toLocaleString()} events
                </span>
              </li>
            ))}
          </ul>
        </Card>

        {/* Top Rule Violations */}
        <Card padding="spacious">
          <h2 className="mb-4 flex items-center gap-2 text-subheading text-re-text-primary">
            <ShieldAlert className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Top Rule Violations
          </h2>
          <ul className="space-y-3">
            {RULE_VIOLATIONS.map((v, i) => (
              <li key={i} className="flex flex-col gap-1.5">
                <span className="text-ui text-re-text-primary">{v.rule}</span>
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge
                    state={v.severity === 'critical' ? 'non-compliant' : 'at-risk'}
                    size="sm"
                  />
                  <span className="font-mono text-label tabular-nums text-re-text-muted">{v.count} violations</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Events */}
        <Card padding="spacious">
          <h2 className="mb-4 flex items-center gap-2 text-subheading text-re-text-primary">
            <FileText className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Recent CTE Events
          </h2>
          <ul className="divide-y divide-re-border-subtle">
            {RECENT_EVENTS.map((ev, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5">
                <StatusBadge
                  state={ev.status === 'compliant' ? 'compliant' : 'non-compliant'}
                  size="sm"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[0.8125rem] text-re-text-primary">{ev.tlc}</span>
                    <span className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-label text-re-text-muted">
                      {ev.cte}
                    </span>
                  </div>
                  <div className="text-ui text-re-text-tertiary">{ev.supplier}</div>
                </div>
                <span className="font-mono text-label tabular-nums text-re-text-muted">{ev.time}</span>
              </li>
            ))}
          </ul>
        </Card>

        {/* Supplier Compliance Grid */}
        <Card padding="spacious">
          <h2 className="mb-4 flex items-center gap-2 text-subheading text-re-text-primary">
            <Users className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Supplier Compliance
          </h2>
          <ul className="divide-y divide-re-border-subtle">
            {SUPPLIER_SCORES.map((s, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5">
                <StatusBadge state={SUPPLIER_STATE[s.status] ?? 'unknown'} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="text-ui text-re-text-primary">{s.name}</div>
                  <div className="font-mono text-label tabular-nums text-re-text-muted">{s.events.toLocaleString()} events</div>
                </div>
                <span className="font-mono text-ui tabular-nums text-re-text-secondary">
                  {s.score}%
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* CTA */}
      <Card padding="spacious" className="text-center">
        <h2 className="font-display text-heading-lg text-re-text-primary">This could be your data</h2>
        <p className="mx-auto mt-4 max-w-[68ch] text-ui text-re-text-secondary">
          RegEngine ingests events from your ERP, validates them against 36 FSMA 204 validation rules (33 stateless + 3 cross-event), and surfaces gaps before they become audit findings during a §1.1455(c) records request. The compliance score shown is RegEngine&apos;s internal six-dimension readiness signal — not an FDA-issued rating.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/walkthrough">
              See the full walkthrough
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href="/pricing">See Pricing</Link>
          </Button>
        </div>
      </Card>
    </Container>
  );
}
