'use client';

import { motion } from 'framer-motion';
import { BarChart3, TrendingUp, Calendar, Sparkles, CreditCard } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

// ── Mock Analytics Data ──────────────────────────────────────────
const docsByDay = [
    { day: 'Mon', count: 342 }, { day: 'Tue', count: 487 },
    { day: 'Wed', count: 523 }, { day: 'Thu', count: 411 },
    { day: 'Fri', count: 689 }, { day: 'Sat', count: 156 },
    { day: 'Sun', count: 98 },
];

const apiByCategory = [
    { category: 'Ingestion', calls: 12400, pct: 42 },
    { category: 'Graph Query', calls: 8200, pct: 28 },
    { category: 'Verification', calls: 4100, pct: 14 },
    { category: 'Export', calls: 2900, pct: 10 },
    { category: 'Admin', calls: 1800, pct: 6 },
];

const mrrMonthly = [
    { month: 'Sep', mrr: 94972 }, { month: 'Oct', mrr: 107319 },
    { month: 'Nov', mrr: 119124 }, { month: 'Dec', mrr: 138184 },
    { month: 'Jan', mrr: 154766 }, { month: 'Feb', mrr: 174886 },
];

// ── Chart Components ─────────────────────────────────────────────

function BarChartSimple({ data, valueKey, labelKey }: {
    data: Record<string, number | string>[];
    valueKey: string;
    labelKey: string;
}) {
    const maxVal = Math.max(...data.map(d => Number(d[valueKey])));
    const barColors = [
        'bg-amber-500/60', 'bg-amber-500/50', 'bg-amber-400/50',
        'bg-orange-500/50', 'bg-amber-600/50', 'bg-amber-500/40', 'bg-amber-400/40',
    ];

    return (
        <div className="flex items-end gap-2 h-48 px-2">
            {data.map((d, i) => {
                const heightPct = (Number(d[valueKey]) / maxVal) * 100;
                return (
                    <div key={String(d[labelKey])} className="flex-1 flex flex-col items-center gap-1">
                        <span className="text-[10px] text-white/60 font-medium">
                            {Number(d[valueKey]).toLocaleString()}
                        </span>
                        <motion.div
                            initial={{ height: 0 }}
                            animate={{ height: `${heightPct}%` }}
                            transition={{ delay: i * 0.05, duration: 0.5 }}
                            className={`w-full rounded-t-md ${barColors[i % barColors.length]} min-h-[4px]`}
                        />
                        <span className="text-[10px] text-white/40">{String(d[labelKey])}</span>
                    </div>
                );
            })}
        </div>
    );
}

function HorizontalBarChart({ data }: { data: typeof apiByCategory }) {
    const colors = [
        'from-amber-500/60 to-amber-600/40',
        'from-blue-500/50 to-blue-600/30',
        'from-emerald-500/50 to-emerald-600/30',
        'from-purple-500/50 to-purple-600/30',
        'from-pink-500/50 to-pink-600/30',
    ];

    return (
        <div className="space-y-3">
            {data.map((d, i) => (
                <div key={d.category} className="space-y-1">
                    <div className="flex justify-between text-xs">
                        <span className="text-white/70 font-medium">{d.category}</span>
                        <span className="text-white/50">{d.calls.toLocaleString()} calls ({d.pct}%)</span>
                    </div>
                    <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${d.pct}%` }}
                            transition={{ delay: i * 0.08, duration: 0.6 }}
                            className={`h-full rounded-full bg-gradient-to-r ${colors[i]}`}
                        />
                    </div>
                </div>
            ))}
        </div>
    );
}

function MRRLineChart({ data }: { data: typeof mrrMonthly }) {
    const maxMRR = Math.max(...data.map(d => d.mrr));
    const width = 100;
    const height = 40;
    const points = data.map((d, i) => ({
        x: (i / (data.length - 1)) * width,
        y: height - (d.mrr / maxMRR) * height * 0.85,
    }));
    const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const areaD = `${pathD} L ${width} ${height} L 0 ${height} Z`;

    return (
        <div>
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-36" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="mrrGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.3" />
                        <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.02" />
                    </linearGradient>
                </defs>
                <path d={areaD} fill="url(#mrrGrad)" />
                <path d={pathD} fill="none" stroke="#f59e0b" strokeWidth="1.2" strokeLinecap="round" />
                {points.map((p, i) => (
                    <circle key={i} cx={p.x} cy={p.y} r="1.5" fill="#f59e0b" />
                ))}
            </svg>
            <div className="flex justify-between mt-2 px-1">
                {data.map(d => (
                    <div key={d.month} className="text-center">
                        <p className="text-[10px] text-white/40">{d.month}</p>
                        <p className="text-xs font-semibold text-white">${(d.mrr / 1000).toFixed(0)}K</p>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Main Page ────────────────────────────────────────────────────

export default function AnalyticsPage() {
    return (
        <div className="p-8">
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white">Analytics</h1>
                    <p className="text-white/60 mt-1">Usage trends and business insights</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" className="bg-white/5 border-white/10 text-white hover:bg-white/10">
                        <Calendar className="h-4 w-4 mr-2" />
                        Last 30 days
                    </Button>
                </div>
            </motion.div>

            {/* Demo Mode Banner */}
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className="mb-6 p-3 rounded-xl bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-amber-500/10 border border-amber-500/20 flex items-center justify-between"
            >
                <div className="flex items-center gap-3">
                    <div className="p-1.5 rounded-lg bg-amber-500/20">
                        <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                    </div>
                    <p className="text-xs text-amber-300">Demo Mode — Connect analytics provider for live data</p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    className="bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20 hover:text-amber-200 text-xs h-7"
                >
                    <CreditCard className="h-3 w-3 mr-1.5" />
                    Connect
                </Button>
            </motion.div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="grid grid-cols-1 lg:grid-cols-2 gap-6"
            >
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <CardTitle className="text-white flex items-center gap-2">
                            <BarChart3 className="h-4 w-4 text-amber-400" />
                            Documents Processed
                        </CardTitle>
                        <CardDescription className="text-white/60">Daily document ingestion this week</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <BarChartSimple data={docsByDay} valueKey="count" labelKey="day" />
                        <div className="mt-4 flex items-center justify-between text-xs">
                            <span className="text-white/40">Total: 2,706 documents</span>
                            <span className="text-emerald-400 font-medium">↑ 18% vs last week</span>
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <CardTitle className="text-white flex items-center gap-2">
                            <TrendingUp className="h-4 w-4 text-blue-400" />
                            API Usage
                        </CardTitle>
                        <CardDescription className="text-white/60">API calls by endpoint category (last 30 days)</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <HorizontalBarChart data={apiByCategory} />
                        <div className="mt-4 flex items-center justify-between text-xs">
                            <span className="text-white/40">Total: 29,400 API calls</span>
                            <span className="text-emerald-400 font-medium">99.7% success rate</span>
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-white/5 backdrop-blur-xl border-white/10 lg:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-white flex items-center gap-2">
                            <BarChart3 className="h-4 w-4 text-amber-400" />
                            Revenue Trends
                        </CardTitle>
                        <CardDescription className="text-white/60">Monthly recurring revenue (6-month view)</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <MRRLineChart data={mrrMonthly} />
                        <div className="mt-4 flex items-center justify-between text-xs">
                            <span className="text-white/40">Current MRR: $174,886</span>
                            <span className="text-emerald-400 font-medium">↑ 84% growth over 6 months</span>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
