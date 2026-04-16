'use client';

import Link from 'next/link';
import {
  Shield, ShieldCheck, ShieldAlert, TrendingUp, AlertTriangle,
  CheckCircle2, XCircle, Clock, Truck, Leaf, Package, Anchor,
  Building2, ArrowRight, BarChart3, Users, FileText, Zap,
} from 'lucide-react';

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
  { cte: 'Packing', icon: Package, count: 2104, compliant: 2055, pct: 97.7 },
  { cte: 'Shipping', icon: Truck, count: 2680, compliant: 2450, pct: 91.4 },
  { cte: 'Receiving', icon: Building2, count: 2187, compliant: 1989, pct: 90.9 },
  { cte: 'Transformation', icon: Zap, count: 480, compliant: 400, pct: 83.3 },
  { cte: 'FLBR', icon: Anchor, count: 120, compliant: 120, pct: 100 },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DemoPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 py-8 text-white">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-2">Compliance Dashboard</h1>
        <p className="text-[var(--re-text-muted)] text-sm">
          FreshCo Distribution &mdash; 3 facilities, 23 suppliers, 12,847 CTE events
        </p>
      </div>

      {/* Top stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Compliance Score"
          value={`${COMPLIANCE_SCORE}%`}
          icon={<Shield className="w-5 h-5" />}
          color="text-[var(--re-brand)]"
          bg="bg-[var(--re-brand)]/10"
        />
        <StatCard
          label="Total Events"
          value={TOTAL_EVENTS.toLocaleString()}
          icon={<BarChart3 className="w-5 h-5" />}
          color="text-blue-400"
          bg="bg-blue-500/10"
        />
        <StatCard
          label="Active Suppliers"
          value={String(SUPPLIERS)}
          icon={<Users className="w-5 h-5" />}
          color="text-purple-400"
          bg="bg-purple-500/10"
        />
        <StatCard
          label="Open Violations"
          value={String(NON_COMPLIANT_EVENTS)}
          icon={<AlertTriangle className="w-5 h-5" />}
          color="text-amber-400"
          bg="bg-amber-500/10"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* CTE Breakdown */}
        <div className="lg:col-span-2 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-[var(--re-brand)]" />
            Compliance by CTE Type
          </h2>
          <div className="space-y-3">
            {CTE_BREAKDOWN.map((cte) => (
              <div key={cte.cte} className="flex items-center gap-3">
                <cte.icon className="w-4 h-4 text-[var(--re-text-muted)] flex-shrink-0" />
                <span className="text-xs w-28 text-[var(--re-text-secondary)]">{cte.cte}</span>
                <div className="flex-1 bg-[var(--re-surface-base)] rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      cte.pct >= 95 ? 'bg-green-500' :
                      cte.pct >= 90 ? 'bg-amber-500' :
                      'bg-red-500'
                    }`}
                    style={{ width: `${cte.pct}%` }}
                  />
                </div>
                <span className={`text-xs font-mono w-12 text-right ${
                  cte.pct >= 95 ? 'text-green-400' :
                  cte.pct >= 90 ? 'text-amber-400' :
                  'text-red-400'
                }`}>
                  {cte.pct}%
                </span>
                <span className="text-[0.6rem] text-[var(--re-text-disabled)] w-16 text-right">
                  {cte.count.toLocaleString()} events
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Top Rule Violations */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-red-400" />
            Top Rule Violations
          </h2>
          <div className="space-y-2.5">
            {RULE_VIOLATIONS.map((v, i) => (
              <div key={i} className="flex items-start gap-2">
                {v.severity === 'critical'
                  ? <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 flex-shrink-0" />
                  : <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="text-[0.7rem] text-[var(--re-text-primary)] leading-tight">{v.rule}</div>
                  <div className="text-[0.6rem] text-[var(--re-text-disabled)]">{v.count} violations</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Recent Events */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <FileText className="w-4 h-4 text-[var(--re-brand)]" />
            Recent CTE Events
          </h2>
          <div className="space-y-2">
            {RECENT_EVENTS.map((ev, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5 border-b border-[var(--re-surface-border)] last:border-0">
                {ev.status === 'compliant'
                  ? <CheckCircle2 className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                  : <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[0.7rem] font-mono text-[var(--re-text-primary)]">{ev.tlc}</span>
                    <span className="text-[0.55rem] px-1.5 py-0.5 rounded bg-[var(--re-surface-elevated)] text-[var(--re-text-disabled)]">
                      {ev.cte}
                    </span>
                  </div>
                  <div className="text-[0.6rem] text-[var(--re-text-muted)]">{ev.supplier}</div>
                </div>
                <span className="text-[0.6rem] text-[var(--re-text-disabled)]">{ev.time}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Supplier Compliance Grid */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <Users className="w-4 h-4 text-purple-400" />
            Supplier Compliance
          </h2>
          <div className="space-y-2.5">
            {SUPPLIER_SCORES.map((s, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5 border-b border-[var(--re-surface-border)] last:border-0">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  s.status === 'excellent' ? 'bg-green-500' :
                  s.status === 'good' ? 'bg-blue-500' :
                  s.status === 'needs_attention' ? 'bg-amber-500' :
                  'bg-red-500'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="text-[0.7rem] text-[var(--re-text-primary)]">{s.name}</div>
                  <div className="text-[0.6rem] text-[var(--re-text-disabled)]">{s.events.toLocaleString()} events</div>
                </div>
                <span className={`text-sm font-mono font-semibold ${
                  s.score >= 95 ? 'text-green-400' :
                  s.score >= 90 ? 'text-blue-400' :
                  s.score >= 85 ? 'text-amber-400' :
                  'text-red-400'
                }`}>
                  {s.score}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="bg-gradient-to-r from-[var(--re-brand)]/10 to-purple-500/10 border border-[var(--re-brand)]/20 rounded-xl p-8 text-center">
        <h2 className="text-xl font-bold mb-2">This could be your data</h2>
        <p className="text-[var(--re-text-muted)] text-sm mb-6 max-w-lg mx-auto">
          RegEngine connects to your ERP, validates every shipment against FSMA 204 rules in real time,
          and gives you a compliance score your FDA inspector will love.
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link
            href="/#sandbox"
            className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-[var(--re-brand-dark)] transition-colors"
          >
            Try the Sandbox
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 bg-white/10 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-colors"
          >
            See Pricing
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function StatCard({ label, value, icon, color, bg }: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: string;
  bg: string;
}) {
  return (
    <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[0.65rem] text-[var(--re-text-muted)] uppercase tracking-wider">{label}</span>
        <div className={`p-1.5 rounded-lg ${bg}`}>
          <div className={color}>{icon}</div>
        </div>
      </div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
    </div>
  );
}
