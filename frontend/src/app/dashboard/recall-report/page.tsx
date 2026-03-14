'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    FileText,
    Download,
    Timer,
    Database,
    ShieldCheck,
    Users,
    Upload,
    GraduationCap,
    AlertTriangle,
    ArrowUp,
    Printer,
} from 'lucide-react';

const DIMENSIONS = [
    {
        id: 'trace_speed', name: 'Trace Speed', icon: Timer, score: 78, grade: 'C',
        color: '#f59e0b',
        findings: [
            'Average trace-back time: 4.2 hours',
            '3 lots required manual lookups',
            'Receiving CTEs averaged 3.1h entry delay',
        ],
        recommendations: [
            'Reduce CTE entry delay to under 2 hours',
            'Digitize remaining manual records',
            'Run monthly mock drills',
        ],
    },
    {
        id: 'data_completeness', name: 'Data Completeness', icon: Database, score: 85, grade: 'B',
        color: '#10b981',
        findings: [
            '92% of CTEs have all required KDEs',
            'GLN coverage: 78% (3 suppliers missing)',
            'TLC format consistency: 95%',
        ],
        recommendations: [
            'Collect missing GLNs from 3 suppliers',
            'Standardize TLC format across facilities',
        ],
    },
    {
        id: 'chain_integrity', name: 'Chain Integrity', icon: ShieldCheck, score: 95, grade: 'A',
        color: '#10b981',
        findings: [
            'SHA-256 hash chain: 100% verified',
            'No gaps in event sequence',
            'All immutability triggers active',
        ],
        recommendations: ['Maintain current practices'],
    },
    {
        id: 'supplier_coverage', name: 'Supplier Coverage', icon: Users, score: 65, grade: 'D',
        color: '#ef4444',
        findings: [
            'Only 60% of suppliers using portal',
            '2 suppliers inactive for 30+ days',
            '1 supplier still paper-based',
        ],
        recommendations: [
            'Send portal link reminders',
            'Offer supplier training sessions',
            'Evaluate non-compliant suppliers',
        ],
    },
    {
        id: 'export_readiness', name: 'Export Readiness', icon: Upload, score: 88, grade: 'B',
        color: '#10b981',
        findings: [
            'FDA CSV export: functional',
            'EPCIS 2.0 JSON-LD: functional',
            'Exports include SHA-256 hashes',
        ],
        recommendations: ['Test with retailer portals (Walmart, Kroger)'],
    },
    {
        id: 'team_readiness', name: 'Team Readiness', icon: GraduationCap, score: 72, grade: 'C',
        color: '#f59e0b',
        findings: [
            'Last mock drill: 2 weeks ago (C)',
            '2 of 5 members completed training',
            'No documented recall SOP on file',
        ],
        recommendations: [
            'Generate SOP via SOP Generator',
            'Schedule monthly mock drills',
            'Complete training for 3 remaining members',
        ],
    },
];

const ACTION_ITEMS = [
    { priority: 'HIGH', action: 'Collect missing GLNs from 3 suppliers', impact: '+5 to Data Completeness', effort: 'Low' },
    { priority: 'HIGH', action: 'Re-engage 2 inactive suppliers', impact: '+10 to Supplier Coverage', effort: 'Low' },
    { priority: 'MEDIUM', action: 'Generate FSMA 204 SOP', impact: '+8 to Team Readiness', effort: 'Low' },
    { priority: 'MEDIUM', action: 'Complete training for 3 members', impact: '+10 to Team Readiness', effort: 'Medium' },
    { priority: 'MEDIUM', action: 'Reduce CTE entry delay to <2h', impact: '+7 to Trace Speed', effort: 'Medium' },
    { priority: 'LOW', action: 'Test EPCIS exports with retailers', impact: '+5 to Export Readiness', effort: 'Low' },
];

function gradeColor(grade: string): string {
    if (grade === 'A') return '#10b981';
    if (grade === 'B') return '#22c55e';
    if (grade === 'C') return '#f59e0b';
    if (grade === 'D') return '#ef4444';
    return '#dc2626';
}

export default function RecallReportPage() {
    const [expanded, setExpanded] = useState<string | null>(null);
    const overallScore = Math.round(DIMENSIONS.reduce((s, d) => s + d.score, 0) / DIMENSIONS.length);
    const overallGrade = overallScore >= 90 ? 'A' : overallScore >= 80 ? 'B' : overallScore >= 70 ? 'C' : overallScore >= 60 ? 'D' : 'F';

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <FileText className="h-6 w-6 text-[var(--re-brand)]" />
                            Recall Readiness Report
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            FSMA 204 Traceability Preparedness Assessment
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button disabled title="Coming Soon" variant="outline" size="sm" className="rounded-xl">
                            <Download className="h-3 w-3 mr-1" /> Export PDF
                        </Button>
                        <Button disabled title="Coming Soon" variant="outline" size="sm" className="rounded-xl">
                            <Printer className="h-3 w-3 mr-1" /> Print
                        </Button>
                    </div>
                </div>

                <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
                </div>

                {/* Overall Score Card */}
                <Card className="border-[var(--re-border-default)] overflow-hidden">
                    <div className="h-1 bg-gradient-to-r from-[var(--re-brand)] to-blue-500" />
                    <CardContent className="py-8">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="text-sm text-muted-foreground mb-1">Overall Readiness Score</div>
                                <div className="flex items-baseline gap-3">
                                    <span className="text-5xl font-bold" style={{ color: gradeColor(overallGrade) }}>
                                        {overallScore}
                                    </span>
                                    <span className="text-2xl text-muted-foreground">/100</span>
                                    <Badge className="text-lg px-3 py-1" style={{ background: gradeColor(overallGrade), color: '#fff' }}>
                                        {overallGrade}
                                    </Badge>
                                </div>
                                <div className="text-sm text-muted-foreground mt-2">
                                    Estimated response time: <strong>4.2 hours</strong> (target: &lt; 24 hours ✅)
                                </div>
                            </div>
                            <div className="text-right text-xs text-muted-foreground">
                                <div>Generated: {new Date().toLocaleDateString()}</div>
                                <div>21 CFR 1.1455 Assessment</div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Dimension Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {DIMENSIONS.map((dim) => {
                        const Icon = dim.icon;
                        const isExpanded = expanded === dim.id;
                        return (
                            <motion.div key={dim.id} layout>
                                <Card
                                    className={`cursor-pointer border transition-all ${isExpanded ? 'border-[var(--re-brand)] col-span-2' : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'}`}
                                    onClick={() => setExpanded(isExpanded ? null : dim.id)}
                                >
                                    <CardContent className="py-4">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <Icon className="h-4 w-4" style={{ color: dim.color }} />
                                                <span className="text-sm font-medium">{dim.name}</span>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-lg font-bold" style={{ color: dim.color }}>{dim.score}</span>
                                                <Badge className="text-xs" style={{ background: gradeColor(dim.grade), color: '#fff' }}>{dim.grade}</Badge>
                                            </div>
                                        </div>
                                        {/* Score bar */}
                                        <div className="w-full bg-[var(--re-surface-elevated)] rounded-full h-2 mb-2">
                                            <motion.div
                                                className="h-full rounded-full"
                                                style={{ background: dim.color }}
                                                initial={{ width: 0 }}
                                                animate={{ width: `${dim.score}%` }}
                                                transition={{ duration: 0.8, delay: 0.1 }}
                                            />
                                        </div>
                                        {isExpanded && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-3 space-y-3">
                                                <div>
                                                    <div className="text-xs font-medium text-muted-foreground mb-1">Findings</div>
                                                    <ul className="text-xs space-y-1">
                                                        {dim.findings.map((f, i) => (
                                                            <li key={i} className="flex items-start gap-1.5">
                                                                <span className="text-muted-foreground">•</span> {f}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                                <div>
                                                    <div className="text-xs font-medium text-muted-foreground mb-1">Recommendations</div>
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
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>

                {/* Action Items */}
                <Card className="border-[var(--re-border-default)]">
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-[var(--re-brand)]" />
                            Prioritized Action Items
                        </CardTitle>
                        <CardDescription>Address these to improve your score</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {ACTION_ITEMS.map((item, i) => (
                                <div key={i} className="flex items-center gap-3 p-3 rounded-xl border border-[var(--re-border-default)]">
                                    <Badge className={`text-[9px] px-2 ${item.priority === 'HIGH' ? 'bg-red-500/10 text-red-500 border-red-500/20' :
                                            item.priority === 'MEDIUM' ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' :
                                                'bg-blue-500/10 text-blue-500 border-blue-500/20'
                                        }`}>
                                        {item.priority}
                                    </Badge>
                                    <div className="flex-1">
                                        <div className="text-sm">{item.action}</div>
                                        <div className="text-[10px] text-muted-foreground">{item.impact} · {item.effort} effort</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* Regulatory Footer */}
                <div className="text-center text-xs text-muted-foreground py-4">
                    Per 21 CFR Part 1, Subpart S · 21 CFR 1.1455 (24-hour mandate) · FSMA Section 204
                </div>
            </div>
        </div>
    );
}
