'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { fetchRecallReport } from '@/lib/api-hooks';
import {
    Download,
    Timer,
    Database,
    ShieldCheck,
    Users,
    Upload,
    GraduationCap,
    AlertTriangle,
    ArrowUp,
    ArrowRight,
    Play,
    Package,
    MapPin,
    Clock,
    CheckCircle2,
    XCircle,
    ShoppingCart,
    Zap,
    Info,
    ChevronDown,
    ChevronUp,
} from 'lucide-react';

/* ── Mock Investigation Data ── */

const INVESTIGATION = {
    scenario: 'Romaine Lettuce — E. coli O157:H7',
    initiated: '2026-03-15T08:30:00Z',
    status: 'IN_PROGRESS' as const,
    response_time_hours: 4.2,
    sla_target: 24,
    lots_at_risk: 12,
    suppliers_impacted: 3,
    facilities_in_chain: 8,
    consumers_potentially_affected: '~2,400',
    total_quantity: '18,200 lbs',
};

const AFFECTED_LOTS = [
    { tlc: 'LOT-ROM-2026-0312A', product: 'Organic Romaine Hearts', facility: 'Salinas Valley Farms', status: 'traced', cte_count: 6, last_event: 'Retail Distribution', risk: 'high' },
    { tlc: 'LOT-ROM-2026-0312B', product: 'Chopped Romaine Mix', facility: 'FreshCut Processing', status: 'traced', cte_count: 5, last_event: 'Transformation', risk: 'high' },
    { tlc: 'LOT-ROM-2026-0311C', product: 'Romaine Hearts 3-Pack', facility: 'Salinas Valley Farms', status: 'traced', cte_count: 4, last_event: 'Shipping', risk: 'medium' },
    { tlc: 'LOT-ROM-2026-0310D', product: 'Organic Romaine Bulk', facility: 'Pacific Coast Growers', status: 'partial', cte_count: 3, last_event: 'Receiving', risk: 'medium' },
    { tlc: 'LOT-ROM-2026-0309E', product: 'Romaine Salad Kit', facility: 'FreshCut Processing', status: 'partial', cte_count: 2, last_event: 'Transformation', risk: 'low' },
];

const TIMELINE_EVENTS = [
    { time: '08:30', label: 'FDA Request Received', desc: 'FSMA 204 records request for romaine lettuce lots from Salinas Valley region', icon: AlertTriangle, color: 'text-red-400', done: true },
    { time: '08:35', label: 'Automated Trace Initiated', desc: 'RegEngine backward trace from retail to harvest across 8 facilities', icon: Zap, color: 'text-[var(--re-brand)]', done: true },
    { time: '08:42', label: '12 Lots Identified', desc: 'Forward trace mapped all downstream distribution — 3 supplier origins confirmed', icon: Package, color: 'text-blue-400', done: true },
    { time: '09:15', label: 'Supplier Notifications Sent', desc: '3 suppliers contacted: Salinas Valley Farms, Pacific Coast Growers, FreshCut Processing', icon: Users, color: 'text-amber-400', done: true },
    { time: '10:00', label: 'FDA CSV Export Generated', desc: '24-hour response package with all CTEs, KDEs, and chain hashes', icon: Download, color: 'text-emerald-400', done: true },
    { time: '—', label: 'Retailer EPCIS Notification', desc: 'GS1 EPCIS 2.0 export for Walmart, Kroger, and Albertsons portals', icon: ShoppingCart, color: 'text-muted-foreground', done: false },
    { time: '—', label: 'Investigation Closed', desc: 'All affected lots accounted for, remediation verified', icon: CheckCircle2, color: 'text-muted-foreground', done: false },
];

const DIMENSIONS = [
    { id: 'trace_speed', name: 'Trace Speed', icon: Timer, score: 78, grade: 'C', color: '#f59e0b',
        findings: ['Average trace-back: 4.2 hours', '3 lots required manual lookups', 'Receiving CTEs averaged 3.1h entry delay'],
        recommendations: ['Reduce CTE entry delay to <2 hours', 'Digitize remaining manual records', 'Run monthly mock drills'] },
    { id: 'data_completeness', name: 'Data Completeness', icon: Database, score: 85, grade: 'B', color: '#10b981',
        findings: ['92% CTEs have all required KDEs', 'GLN coverage: 78% (3 suppliers missing)', 'TLC format consistency: 95%'],
        recommendations: ['Collect missing GLNs from 3 suppliers', 'Standardize TLC format across facilities'] },
    { id: 'chain_integrity', name: 'Chain Integrity', icon: ShieldCheck, score: 95, grade: 'A', color: '#10b981',
        findings: ['SHA-256 hash chain: 100% verified', 'No gaps in event sequence', 'All immutability triggers active'],
        recommendations: ['Maintain current practices'] },
    { id: 'supplier_coverage', name: 'Supplier Coverage', icon: Users, score: 65, grade: 'D', color: '#ef4444',
        findings: ['60% of suppliers using portal', '2 suppliers inactive 30+ days', '1 supplier still paper-based'],
        recommendations: ['Send portal link reminders', 'Offer supplier training', 'Evaluate non-compliant suppliers'] },
    { id: 'export_readiness', name: 'Export Readiness', icon: Upload, score: 88, grade: 'B', color: '#10b981',
        findings: ['FDA CSV export: functional', 'EPCIS 2.0 JSON-LD: functional', 'Exports include SHA-256 hashes'],
        recommendations: ['Test with retailer portals (Walmart, Kroger)'] },
    { id: 'team_readiness', name: 'Team Readiness', icon: GraduationCap, score: 72, grade: 'C', color: '#f59e0b',
        findings: ['Last mock drill: 2 weeks ago (C)', '2 of 5 members trained', 'No documented recall SOP'],
        recommendations: ['Generate SOP via SOP Generator', 'Schedule monthly mock drills', 'Train 3 remaining members'] },
];

const ACTION_ITEMS = [
    { priority: 'HIGH', action: 'Collect missing GLNs from 3 suppliers', impact: '+5 Data Completeness', effort: 'Low' },
    { priority: 'HIGH', action: 'Re-engage 2 inactive suppliers', impact: '+10 Supplier Coverage', effort: 'Low' },
    { priority: 'MEDIUM', action: 'Generate FSMA 204 SOP', impact: '+8 Team Readiness', effort: 'Low' },
    { priority: 'MEDIUM', action: 'Complete training for 3 members', impact: '+10 Team Readiness', effort: 'Medium' },
    { priority: 'MEDIUM', action: 'Reduce CTE entry delay to <2h', impact: '+7 Trace Speed', effort: 'Medium' },
    { priority: 'LOW', action: 'Test EPCIS exports with retailers', impact: '+5 Export Readiness', effort: 'Low' },
];

/* ── Helpers ── */

function gradeColor(grade: string) {
    if (grade === 'A') return '#10b981';
    if (grade === 'B') return '#22c55e';
    if (grade === 'C') return '#f59e0b';
    if (grade === 'D') return '#ef4444';
    return '#dc2626';
}

function riskBadge(risk: string) {
    if (risk === 'high') return 'bg-red-500/10 text-red-400 border-red-500/20';
    if (risk === 'medium') return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
}

/* ── Page Component ── */

export default function RecallReportPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const [expanded, setExpanded] = useState<string | null>(null);
    const [liveData, setLiveData] = useState<Record<string, unknown> | null>(null);
    const [isDemo, setIsDemo] = useState(true);

    // Attempt to fetch real recall data; fall back to demo scenario
    useEffect(() => {
        if (!tenantId || !apiKey) return;
        fetchRecallReport(tenantId, apiKey)
            .then((data) => {
                const record = data as Record<string, unknown> | null;
                if (record && Object.keys(record).length > 0) {
                    setLiveData(record);
                    setIsDemo(false);
                }
            })
            .catch(() => {
                // API not available — show demo scenario
            });
    }, [tenantId, apiKey]);

    const overallScore = Math.round(DIMENSIONS.reduce((s, d) => s + d.score, 0) / DIMENSIONS.length);
    const overallGrade = overallScore >= 90 ? 'A' : overallScore >= 80 ? 'B' : overallScore >= 70 ? 'C' : overallScore >= 60 ? 'D' : 'F';
    const slaPercent = Math.round((INVESTIGATION.response_time_hours / INVESTIGATION.sla_target) * 100);

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Recall Report' },
                ]} />

                {/* Header */}
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-2">
                            <AlertTriangle className="h-6 w-6 sm:h-7 sm:w-7 text-red-400" />
                            Recall Investigation
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">
                            FSMA 204 Traceability Response &amp; Readiness Assessment
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <Link href="/tools/drill-simulator">
                            <Button variant="outline" size="sm" className="rounded-xl min-h-[44px] active:scale-[0.97]">
                                <Play className="h-3.5 w-3.5 mr-1.5" /> Run Mock Drill
                            </Button>
                        </Link>
                        <Button size="sm" className="rounded-xl min-h-[44px] bg-red-600 hover:bg-red-700 text-white active:scale-[0.97]">
                            <Download className="h-3.5 w-3.5 mr-1.5" /> Generate FDA 24-Hour Response
                        </Button>
                    </div>
                </div>

                {/* Data source notice */}
                {isDemo && (
                    <div className="flex items-center gap-2 p-3 rounded-xl bg-blue-500/[0.06] border border-blue-500/20 text-blue-300 text-xs">
                        <Info className="h-3.5 w-3.5 flex-shrink-0" />
                        <span>Sample Scenario — Explore a realistic recall investigation. Your live data populates automatically after onboarding.</span>
                    </div>
                )}

                {/* Risk Summary Banner */}
                <motion.div
                    className="grid grid-cols-2 md:grid-cols-5 gap-2 sm:gap-3"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    <div className="p-3 sm:p-4 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-red-400 tabular-nums">{INVESTIGATION.lots_at_risk}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Lots at Risk</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-amber-500/[0.06] border border-amber-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-amber-400 tabular-nums">{INVESTIGATION.suppliers_impacted}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Suppliers Impacted</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-blue-500/[0.06] border border-blue-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-blue-400 tabular-nums">{INVESTIGATION.facilities_in_chain}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Facilities in Chain</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                        <div className="text-2xl sm:text-3xl font-bold tabular-nums">{INVESTIGATION.consumers_potentially_affected}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Consumers at Risk</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-emerald-500/[0.06] border border-emerald-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-emerald-400 tabular-nums">{INVESTIGATION.response_time_hours}h</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Response Time</div>
                    </div>
                </motion.div>

                {/* SLA + Scenario Row */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
                    {/* SLA Gauge Card */}
                    <Card className="border-[var(--re-border-default)]">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-base flex items-center gap-2">
                                <Clock className="h-4 w-4 text-[var(--re-brand)]" />
                                24-Hour SLA Status
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="flex flex-col items-center">
                            <div className="relative w-36 h-36 sm:w-44 sm:h-44">
                                <svg className="w-full h-full -rotate-90" viewBox="0 0 200 200">
                                    <circle cx="100" cy="100" r="80" stroke="var(--re-border-default)" strokeWidth="10" fill="none" opacity="0.3" />
                                    <motion.circle
                                        cx="100" cy="100" r="80"
                                        stroke="#10b981"
                                        strokeWidth="12" fill="none" strokeLinecap="round"
                                        strokeDasharray={2 * Math.PI * 80}
                                        initial={{ strokeDashoffset: 2 * Math.PI * 80 }}
                                        animate={{ strokeDashoffset: 2 * Math.PI * 80 - (slaPercent / 100) * 2 * Math.PI * 80 }}
                                        transition={{ duration: 1.5, ease: 'easeOut' }}
                                    />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                    <div className="text-3xl sm:text-4xl font-bold text-emerald-400 tabular-nums">{INVESTIGATION.response_time_hours}h</div>
                                    <div className="text-[10px] text-muted-foreground mt-0.5">of 24h SLA</div>
                                </div>
                            </div>
                            <div className="mt-3 flex items-center gap-1.5">
                                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                                <span className="text-xs font-medium text-emerald-400">SLA Met — {(24 - INVESTIGATION.response_time_hours).toFixed(1)}h to spare</span>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Investigation Timeline */}
                    <Card className="border-[var(--re-border-default)] lg:col-span-2">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-base flex items-center gap-2">
                                <Timer className="h-4 w-4 text-[var(--re-brand)]" />
                                Investigation Timeline
                            </CardTitle>
                            <CardDescription className="text-xs">
                                {INVESTIGATION.scenario}
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="relative">
                                {TIMELINE_EVENTS.map((evt, i) => {
                                    const Icon = evt.icon;
                                    return (
                                        <motion.div
                                            key={i}
                                            className="flex gap-3 pb-4 last:pb-0"
                                            initial={{ opacity: 0, x: -10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: 0.1 * i }}
                                        >
                                            {/* Timeline connector */}
                                            <div className="flex flex-col items-center">
                                                <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${evt.done ? 'bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]' : 'bg-[var(--re-surface-card)] border border-dashed border-[var(--re-border-default)]'}`}>
                                                    <Icon className={`h-3.5 w-3.5 ${evt.color}`} />
                                                </div>
                                                {i < TIMELINE_EVENTS.length - 1 && (
                                                    <div className={`w-px flex-1 min-h-[16px] ${evt.done ? 'bg-[var(--re-border-default)]' : 'bg-[var(--re-border-default)] opacity-30'}`} />
                                                )}
                                            </div>
                                            {/* Event content */}
                                            <div className="flex-1 min-w-0 pb-2">
                                                <div className="flex items-center gap-2">
                                                    <span className={`text-xs sm:text-sm font-medium ${evt.done ? '' : 'text-muted-foreground'}`}>{evt.label}</span>
                                                    {evt.done && (
                                                        <Badge variant="secondary" className="text-[9px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">Done</Badge>
                                                    )}
                                                </div>
                                                <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{evt.desc}</p>
                                                <span className="text-[10px] text-muted-foreground font-mono">{evt.time}</span>
                                            </div>
                                        </motion.div>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Affected Lots */}
                <Card className="border-[var(--re-border-default)]">
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-base flex items-center gap-2">
                                <Package className="h-4 w-4 text-[var(--re-brand)]" />
                                Affected Lots ({AFFECTED_LOTS.length})
                            </CardTitle>
                            <span className="text-[10px] text-muted-foreground">{INVESTIGATION.total_quantity} total</span>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {AFFECTED_LOTS.map((lot, i) => (
                                <motion.div
                                    key={lot.tlc}
                                    className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-3 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]"
                                    initial={{ opacity: 0, y: 5 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: 0.05 * i }}
                                >
                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${lot.risk === 'high' ? 'bg-red-400' : lot.risk === 'medium' ? 'bg-amber-400' : 'bg-emerald-400'}`} />
                                        <div className="min-w-0">
                                            <div className="font-mono text-xs truncate">{lot.tlc}</div>
                                            <div className="text-[11px] text-muted-foreground truncate">{lot.product}</div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                                        <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                            <MapPin className="h-3 w-3" /> {lot.facility}
                                        </span>
                                        <Badge variant="secondary" className="text-[9px]">{lot.cte_count} CTEs</Badge>
                                        <Badge variant="secondary" className={`text-[9px] ${riskBadge(lot.risk)}`}>
                                            {lot.risk}
                                        </Badge>
                                        {lot.status === 'traced' ? (
                                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                                        ) : (
                                            <Clock className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" />
                                        )}
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* Readiness Score + Dimensions */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
                    {/* Overall Score */}
                    <Card className="border-[var(--re-border-default)] overflow-hidden">
                        <div className="h-1 bg-gradient-to-r from-[var(--re-brand)] to-blue-500" />
                        <CardContent className="py-5 sm:py-6">
                            <div className="text-xs text-muted-foreground mb-1">Overall Readiness</div>
                            <div className="flex items-baseline gap-3">
                                <span className="text-4xl sm:text-5xl font-bold" style={{ color: gradeColor(overallGrade) }}>
                                    {overallScore}
                                </span>
                                <span className="text-lg text-muted-foreground">/100</span>
                                <Badge className="text-sm px-2.5 py-0.5" style={{ background: gradeColor(overallGrade), color: '#fff' }}>
                                    {overallGrade}
                                </Badge>
                            </div>
                            <div className="text-xs text-muted-foreground mt-3">
                                Response time: <strong className="text-foreground">{INVESTIGATION.response_time_hours}h</strong> (target: &lt;24h)
                            </div>
                            <div className="text-[10px] text-muted-foreground mt-1">
                                21 CFR 1.1455 Assessment · {new Date().toLocaleDateString()}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Dimension Grid */}
                    <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
                        {DIMENSIONS.map((dim) => {
                            const Icon = dim.icon;
                            const isExpanded = expanded === dim.id;
                            return (
                                <motion.div key={dim.id} layout className={isExpanded ? 'sm:col-span-2' : ''}>
                                    <Card
                                        className={`cursor-pointer border transition-all active:scale-[0.98] h-full ${isExpanded ? 'border-[var(--re-brand)]' : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]/50'}`}
                                        onClick={() => setExpanded(isExpanded ? null : dim.id)}
                                    >
                                        <CardContent className="py-3 sm:py-4">
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <Icon className="h-4 w-4 flex-shrink-0" style={{ color: dim.color }} />
                                                    <span className="text-xs sm:text-sm font-medium truncate">{dim.name}</span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-sm font-bold tabular-nums" style={{ color: dim.color }}>{dim.score}</span>
                                                    <Badge className="text-[10px] px-1.5" style={{ background: gradeColor(dim.grade), color: '#fff' }}>{dim.grade}</Badge>
                                                    {isExpanded ? <ChevronUp className="h-3 w-3 text-muted-foreground" /> : <ChevronDown className="h-3 w-3 text-muted-foreground" />}
                                                </div>
                                            </div>
                                            {/* Score bar */}
                                            <div className="w-full bg-[var(--re-surface-card)] rounded-full h-1.5">
                                                <motion.div
                                                    className="h-full rounded-full"
                                                    style={{ background: dim.color }}
                                                    initial={{ width: 0 }}
                                                    animate={{ width: `${dim.score}%` }}
                                                    transition={{ duration: 0.8, delay: 0.1 }}
                                                />
                                            </div>
                                            <AnimatePresence>
                                                {isExpanded && (
                                                    <motion.div
                                                        initial={{ opacity: 0, height: 0 }}
                                                        animate={{ opacity: 1, height: 'auto' }}
                                                        exit={{ opacity: 0, height: 0 }}
                                                        className="mt-3 space-y-2.5 overflow-hidden"
                                                    >
                                                        <div>
                                                            <div className="text-[10px] font-medium text-muted-foreground mb-1">Findings</div>
                                                            <ul className="text-xs space-y-1">
                                                                {dim.findings.map((f, i) => (
                                                                    <li key={i} className="flex items-start gap-1.5 text-muted-foreground">
                                                                        <span>•</span> {f}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                        <div>
                                                            <div className="text-[10px] font-medium text-muted-foreground mb-1">Recommendations</div>
                                                            <ul className="text-xs space-y-1">
                                                                {dim.recommendations.map((r, i) => (
                                                                    <li key={i} className="flex items-start gap-1.5 text-[var(--re-brand)]">
                                                                        <ArrowUp className="h-3 w-3 mt-0.5 flex-shrink-0" /> {r}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>

                {/* Action Items */}
                <Card className="border-[var(--re-border-default)]">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base flex items-center gap-2">
                            <Zap className="h-4 w-4 text-[var(--re-brand)]" />
                            Prioritized Actions
                        </CardTitle>
                        <CardDescription className="text-xs">Address these to improve recall readiness</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {ACTION_ITEMS.map((item, i) => (
                                <motion.div
                                    key={i}
                                    className="flex items-center gap-2 sm:gap-3 p-3 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]"
                                    initial={{ opacity: 0, x: 10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.05 * i }}
                                >
                                    <Badge variant="secondary" className={`text-[9px] px-2 flex-shrink-0 uppercase tracking-widest ${
                                        item.priority === 'HIGH' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                        item.priority === 'MEDIUM' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                        'bg-blue-500/10 text-blue-400 border-blue-500/20'
                                    }`}>
                                        {item.priority}
                                    </Badge>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-xs sm:text-sm">{item.action}</div>
                                        <div className="text-[10px] text-muted-foreground">{item.impact} · {item.effort} effort</div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* What This Means */}
                <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                    <CardContent className="py-4">
                        <div className="flex items-start gap-3">
                            <Info className="h-4 w-4 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                            <div className="text-xs text-muted-foreground leading-relaxed">
                                <span className="font-medium text-foreground">What this means for your facility: </span>
                                {overallScore >= 80
                                    ? 'Your facility can respond to an FDA 204 records request well within the 24-hour mandate. Trace-back, lot identification, and export packaging are all functional. Continue running monthly mock drills to maintain readiness.'
                                    : overallScore >= 60
                                    ? 'Your facility has basic recall capabilities but gaps in supplier coverage and trace speed could delay an FDA response. Address the high-priority actions above to reduce risk before your next audit or inspection.'
                                    : 'Critical gaps in your traceability system would likely prevent a timely response to an FDA records request. Immediate action on supplier onboarding and data completeness is recommended to avoid regulatory exposure.'}
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* No Active Recall — Empty State (shown when no investigation data) */}
                {/* Uncomment when wired to live data:
                {!investigation && (
                    <motion.div className="flex flex-col items-center justify-center py-16 text-center" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <ShieldCheck className="h-12 w-12 text-emerald-400/40 mb-4" />
                        <h2 className="text-lg font-semibold">No Active Recall</h2>
                        <p className="text-sm text-muted-foreground mt-1 max-w-md">Your system is ready for a 24-hour FDA response. Run a mock drill to stay sharp.</p>
                        <Link href="/tools/drill-simulator">
                            <Button size="sm" className="mt-4"><Play className="mr-1.5 h-3.5 w-3.5" /> Simulate Recall Drill</Button>
                        </Link>
                    </motion.div>
                )}
                */}

                {/* Regulatory Footer */}
                <div className="text-center text-[10px] text-muted-foreground py-4 space-y-0.5">
                    <div>Per 21 CFR Part 1, Subpart S · 21 CFR 1.1455 (24-hour mandate) · FSMA Section 204</div>
                    <div>This report is generated from traceability data in your RegEngine instance.</div>
                </div>
            </div>
        </div>
    );
}
