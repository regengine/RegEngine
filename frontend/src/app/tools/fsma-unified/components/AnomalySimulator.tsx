'use client';

import React, { useMemo, useState } from "react";
import {
    LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
    ScatterChart, Scatter, ZAxis, Legend, BarChart, Bar, Cell, ComposedChart, Area, ReferenceLine,
} from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertTriangle, RefreshCw, Sparkles } from "lucide-react";

// ── Types ──
type RNG = () => number;
function mulberry32(seed: number): RNG {
    let a = seed >>> 0;
    return function () {
        a |= 0; a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
function clamp(n: number, min: number, max: number) { return Math.max(min, Math.min(max, n)); }
function mean(arr: number[]) { return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0; }
function stddev(arr: number[]) {
    if (arr.length < 2) return 0;
    const m = mean(arr);
    return Math.sqrt(arr.reduce((a, b) => a + (b - m) ** 2, 0) / (arr.length - 1));
}
function fmt(n: number, d = 2) { return Number.isFinite(n) ? n.toFixed(d) : "—"; }
function isoHourLabel(ts: number) { return new Date(ts).toISOString().slice(0, 13) + ":00"; }

type TempPoint = { t: number; hour: string; tempF: number; injectedAnomaly: boolean; dayIdx: number; hourOfDay: number };
type LotFlowPoint = { id: string; supplierId: string; supplierName: string; lot: string; dayIdx: number; qty: number; tempExposureHours: number; transitHours: number; tempOnArrival: number; flagged: boolean };
type Supplier = { id: string; name: string; region: string };
type AlgoMode = "ensemble" | "statistical" | "rule" | "pattern";
type DetectionResult = { flaggedHours: Set<string>; explanations: Map<string, string> };
type Confusion = { tp: number; fp: number; tn: number; fn: number; precision: number; recall: number; f1: number };
type DailyAggregate = { day: number; label: string; min: number; max: number; avg: number; anomalyCount: number; maxScore: number };

// ── Synthetic Data Generator ──
function generateSyntheticColdChain(seed = 204, days = 90) {
    const rng = mulberry32(seed);
    const start = Date.UTC(2026, 0, 1);
    const totalHours = days * 24;
    const anomalyDays = new Set<number>();
    while (anomalyDays.size < 6) anomalyDays.add(Math.floor(rng() * days));

    const points: TempPoint[] = [];
    for (let h = 0; h < totalHours; h++) {
        const t = start + h * 3600_000;
        const dayIdx = Math.floor(h / 24);
        const hourOfDay = h % 24;
        const diurnal = Math.sin((2 * Math.PI * hourOfDay) / 24) * 0.7;
        const noise = (rng() - 0.5) * 0.9;
        let tempF = 36.5 + diurnal + noise;
        let injected = false;
        if (anomalyDays.has(dayIdx)) {
            const startExc = 10 + Math.floor(rng() * 6);
            const dur = 5 + Math.floor(rng() * 3);
            if (hourOfDay >= startExc && hourOfDay < startExc + dur) { tempF = 42 + (rng() - 0.5) * 1.2; injected = true; }
        }
        points.push({ t, hour: isoHourLabel(t), tempF: Number(tempF.toFixed(2)), injectedAnomaly: injected, dayIdx, hourOfDay });
    }

    const suppliers: Supplier[] = [
        { id: "sup-a", name: "Arroyo Farms", region: "CA" }, { id: "sup-b", name: "Delta Leaf Co.", region: "AZ" },
        { id: "sup-c", name: "North Basin Produce", region: "NV" }, { id: "sup-d", name: "Canyon Ridge Growers", region: "CA" },
        { id: "sup-e", name: "Mesa Fresh Logistics", region: "AZ" }, { id: "sup-f", name: "Pacific Valley Supply", region: "CA" },
    ];

    const lots: LotFlowPoint[] = [];
    for (let i = 0; i < 200; i++) {
        const s = suppliers[Math.floor(rng() * suppliers.length)];
        const dayIdx = Math.floor(rng() * days);
        const qty = Math.round(80 + rng() * 920);
        const exposure = anomalyDays.has(dayIdx) ? 2 + Math.floor(rng() * 6) : Math.floor(rng() * 2);
        const transitHours = 2 + Math.floor(rng() * 48);
        const isAnomalous = anomalyDays.has(dayIdx) || (transitHours > 36 && rng() > 0.5);
        const tempOnArrival = isAnomalous ? 38 + Math.floor(rng() * 20) : 34 + Math.floor(rng() * 4);
        lots.push({ id: `lf-${i}`, supplierId: s.id, supplierName: s.name, lot: `RML-${String(dayIdx).padStart(3, "0")}-${Math.floor(100 + rng() * 900)}`, dayIdx, qty, tempExposureHours: exposure, transitHours, tempOnArrival, flagged: false });
    }
    return { points, lots, suppliers, anomalyDays, start, days };
}

// ── Detection Algorithms ──
function detectAnomalies(series: TempPoint[], mode: AlgoMode, s01: number): DetectionResult {
    const temps = series.map(p => p.tempF);
    const m = mean(temps), sd = stddev(temps);
    const zThresh = 3.0 - s01 * 1.2;
    const consHours = Math.round(4 - s01 * 2);
    const driftThresh = 1.6 - s01 * 0.8;
    const explain = new Map<string, string>();

    const statFlags = new Set<string>();
    if (sd > 0) series.forEach(p => { const z = Math.abs((p.tempF - m) / sd); if (z >= zThresh) { statFlags.add(p.hour); explain.set(p.hour, `Statistical (Z-score): |(${fmt(p.tempF)} − ${fmt(m)}) / ${fmt(sd)}| = ${fmt(z)} ≥ ${fmt(zThresh)}.`); } });

    const ruleFlags = new Set<string>();
    let run = 0;
    for (let i = 0; i < series.length; i++) {
        if (series[i].tempF > 40) run++; else run = 0;
        if (run >= consHours) for (let k = i - (consHours - 1); k <= i; k++) { ruleFlags.add(series[k].hour); if (!explain.has(series[k].hour)) explain.set(series[k].hour, `Rule-based: ${fmt(series[k].tempF)}°F > 40°F for ≥ ${consHours} consecutive hours.`); }
    }

    const patternFlags = new Set<string>();
    for (let i = 192; i < series.length; i++) {
        const mw = mean(series.slice(i - 24, i).map(p => p.tempF));
        const mb = mean(series.slice(i - 192, i - 24).map(p => p.tempF));
        if (mw - mb >= driftThresh) { patternFlags.add(series[i - 1].hour); if (!explain.has(series[i - 1].hour)) explain.set(series[i - 1].hour, `Pattern drift: 24h mean (${fmt(mw)}°F) − 7d baseline (${fmt(mb)}°F) = ${fmt(mw - mb)}°F ≥ ${fmt(driftThresh)}°F.`); }
    }

    const combine = (a: Set<string>, b: Set<string>) => { const o = new Set(a); b.forEach(x => o.add(x)); return o; };
    let out: Set<string>;
    if (mode === "statistical") out = statFlags;
    else if (mode === "rule") out = ruleFlags;
    else if (mode === "pattern") out = patternFlags;
    else out = combine(combine(statFlags, ruleFlags), patternFlags);

    out.forEach(h => { const p = series.find(x => x.hour === h); if (p && p.tempF > 40) { const prior = explain.get(h) || ""; explain.set(h, `${prior} Regulatory: cold-chain deviations are a hazard-control concern under 21 CFR Part 117.`); } });
    return { flaggedHours: out, explanations: explain };
}

function confusionMatrix(series: TempPoint[], flagged: Set<string>): Confusion {
    let tp = 0, fp = 0, tn = 0, fn = 0;
    for (const p of series) { const pred = flagged.has(p.hour); if (pred && p.injectedAnomaly) tp++; else if (pred) fp++; else if (p.injectedAnomaly) fn++; else tn++; }
    const precision = tp + fp === 0 ? 0 : tp / (tp + fp);
    const recall = tp + fn === 0 ? 0 : tp / (tp + fn);
    const f1 = precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall);
    return { tp, fp, tn, fn, precision, recall, f1 };
}

function costRec(c: Confusion, fpC: number, fnC: number) {
    const eFp = c.fp * fpC, eFn = c.fn * fnC;
    if (eFn > eFp * 2) return { headline: "Bias toward sensitivity", detail: "False negatives dominate cost. Increase sensitivity." };
    if (eFp > eFn * 2) return { headline: "Bias toward specificity", detail: "False positives dominate cost. Reduce sensitivity." };
    return { headline: "Balanced tradeoff", detail: "Costs in same band. Focus on data quality." };
}

function aggregateDaily(points: TempPoint[], flagged: Set<string>): DailyAggregate[] {
    const days: Record<number, { temps: number[]; anomalies: number }> = {};
    points.forEach(p => { if (!days[p.dayIdx]) days[p.dayIdx] = { temps: [], anomalies: 0 }; days[p.dayIdx].temps.push(p.tempF); if (flagged.has(p.hour)) days[p.dayIdx].anomalies++; });
    return Object.entries(days).map(([d, v]) => ({ day: parseInt(d), label: `Day ${parseInt(d) + 1}`, min: Math.round(Math.min(...v.temps) * 10) / 10, max: Math.round(Math.max(...v.temps) * 10) / 10, avg: Math.round(mean(v.temps) * 10) / 10, anomalyCount: v.anomalies, maxScore: v.anomalies > 0 ? Math.min(1, v.anomalies / 8) : 0 }));
}

export function AnomalyDetectionSimulator() {
    const [seed, setSeed] = useState(204);
    const [mode, setMode] = useState<AlgoMode>("ensemble");
    const [sensitivity, setSensitivity] = useState(55);
    const [tab, setTab] = useState<"stream" | "daily" | "lots" | "suppliers" | "eval">("stream");
    const [selectedHour, setSelectedHour] = useState<string | null>(null);
    const [fpCost, setFpCost] = useState(800);
    const [fnCost, setFnCost] = useState(50000);

    const dataset = useMemo(() => generateSyntheticColdChain(seed, 90), [seed]);
    const det = useMemo(() => detectAnomalies(dataset.points, mode, sensitivity / 100), [dataset.points, mode, sensitivity]);
    const conf = useMemo(() => confusionMatrix(dataset.points, det.flaggedHours), [dataset.points, det.flaggedHours]);
    const rec = useMemo(() => costRec(conf, fpCost, fnCost), [conf, fpCost, fnCost]);
    const dailyData = useMemo(() => aggregateDaily(dataset.points, det.flaggedHours), [dataset.points, det.flaggedHours]);

    const streamData = useMemo(() => dataset.points.map((p, idx) => ({ idx, hour: p.hour, tempF: p.tempF, flagged: det.flaggedHours.has(p.hour) ? 1 : 0 })), [dataset.points, det.flaggedHours]);

    const lotsData = useMemo(() => {
        const dayHasFlag = new Set<number>();
        dataset.points.forEach((p, i) => { if (det.flaggedHours.has(p.hour)) dayHasFlag.add(Math.floor(i / 24)); });
        return dataset.lots.map(l => ({ ...l, supplier: l.supplierName, flagged: dayHasFlag.has(l.dayIdx) || l.tempExposureHours >= 4 }));
    }, [dataset, det.flaggedHours]);

    const normalLots = useMemo(() => lotsData.filter(l => !l.flagged), [lotsData]);
    const flaggedLots = useMemo(() => lotsData.filter(l => l.flagged), [lotsData]);

    const supplierMatrix = useMemo(() => {
        const m = new Map<string, { name: string; region: string; lots: number; flagged: number; exp: number; transit: number; temp: number }>();
        dataset.suppliers.forEach(s => m.set(s.id, { name: s.name, region: s.region, lots: 0, flagged: 0, exp: 0, transit: 0, temp: 0 }));
        lotsData.forEach(l => { const e = m.get(l.supplierId); if (!e) return; e.lots++; if (l.flagged) e.flagged++; e.exp += l.tempExposureHours; e.transit += l.transitHours; e.temp += l.tempOnArrival; });
        return Array.from(m.entries()).map(([id, v]) => {
            const rate = v.lots ? v.flagged / v.lots : 0;
            return { id, supplier: v.name, region: v.region, lots: v.lots, flaggedLots: v.flagged, flaggedRate: Number((rate * 100).toFixed(1)), avgTransit: Number((v.lots ? v.transit / v.lots : 0).toFixed(1)), avgTemp: Number((v.lots ? v.temp / v.lots : 0).toFixed(1)), score: Number(clamp(rate * 70 + ((v.lots ? v.exp / v.lots : 0) / 6) * 30, 0, 100).toFixed(1)) };
        }).sort((a, b) => b.score - a.score);
    }, [dataset.suppliers, lotsData]);

    const topFlags = useMemo(() => dataset.points.filter(p => det.flaggedHours.has(p.hour)).slice(-12).reverse(), [dataset.points, det.flaggedHours]);
    const sevColor = (s: number) => s > 0.7 ? "#ef4444" : s > 0.4 ? "#f59e0b" : s > 0.1 ? "#f59e0b88" : "#10b98133";

    return (
        <div className="space-y-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-2">
                    <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-muted"><AlertTriangle className="h-5 w-5" /></div>
                    <div>
                        <div className="text-xl font-semibold">Anomaly Detection Simulator</div>
                        <div className="text-sm text-muted-foreground">Seeded cold-chain + lot-flow simulator.</div>
                    </div>
                </div>
                <div className="flex gap-2 items-center">
                    <Select value={mode} onValueChange={v => setMode(v as AlgoMode)}>
                        <SelectTrigger className="w-[200px] rounded-2xl"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="ensemble">Ensemble (recommended)</SelectItem>
                            <SelectItem value="statistical">Statistical (Z-score)</SelectItem>
                            <SelectItem value="rule">Rule (40°F duration)</SelectItem>
                            <SelectItem value="pattern">Pattern (drift)</SelectItem>
                        </SelectContent>
                    </Select>
                    <Button variant="outline" className="rounded-2xl" onClick={() => { setSeed(s => (s + 1) % 10000); setSelectedHour(null); }}><RefreshCw className="mr-2 h-4 w-4" />Reseed</Button>
                </div>
            </div>

            <Card className="rounded-3xl"><CardContent className="p-4 md:p-6">
                <div className="grid gap-4 md:grid-cols-12 md:items-center">
                    <div className="md:col-span-5">
                        <div className="text-sm font-medium">Sensitivity</div>
                        <div className="text-xs text-muted-foreground">Higher = more flags.</div>
                        <div className="mt-3">
                            <input
                                type="range"
                                className="w-full h-2 bg-[var(--re-border-default)] rounded-lg appearance-none cursor-pointer accent-[var(--re-brand)]"
                                value={sensitivity}
                                onChange={e => setSensitivity(Number(e.target.value))}
                                min={0} max={100} step={1}
                            />
                            <div className="mt-2 text-xs text-muted-foreground">{sensitivity}/100</div>
                        </div>
                    </div>
                    <div className="md:col-span-7">
                        <div className="grid gap-3 sm:grid-cols-3">
                            <div className="rounded-2xl border p-3"><div className="text-xs text-muted-foreground">Precision</div><div className="text-2xl font-semibold">{fmt(conf.precision * 100, 1)}%</div></div>
                            <div className="rounded-2xl border p-3"><div className="text-xs text-muted-foreground">Recall</div><div className="text-2xl font-semibold">{fmt(conf.recall * 100, 1)}%</div></div>
                            <div className="rounded-2xl border p-3"><div className="text-xs text-muted-foreground">F1</div><div className="text-2xl font-semibold">{fmt(conf.f1 * 100, 1)}%</div></div>
                        </div>
                    </div>
                </div>

                <div className="mt-5 grid gap-4 md:grid-cols-12">
                    <div className="md:col-span-9">
                        <Tabs value={tab} onValueChange={v => setTab(v as any)}>
                            <TabsList className="rounded-2xl">
                                <TabsTrigger value="stream" className="rounded-2xl">Temp stream</TabsTrigger>
                                <TabsTrigger value="daily" className="rounded-2xl">Daily overview</TabsTrigger>
                                <TabsTrigger value="lots" className="rounded-2xl">Lot scatter</TabsTrigger>
                                <TabsTrigger value="suppliers" className="rounded-2xl">Supplier risk</TabsTrigger>
                                <TabsTrigger value="eval" className="rounded-2xl">Evaluation</TabsTrigger>
                            </TabsList>

                            <TabsContent value="stream" className="mt-3">
                                <div className="h-[300px] w-full rounded-2xl border p-2"><ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={streamData} margin={{ top: 10, right: 14, bottom: 6, left: 6 }}>
                                        <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="idx" tick={false} label={{ value: "90 days (hourly)", position: "insideBottom", offset: -2 }} /><YAxis domain={[32, 46]} />
                                        <Tooltip formatter={(v: any, n: any) => n === "tempF" ? [`${fmt(Number(v))} °F`, "Temp"] : [v, n]} labelFormatter={(l: any) => streamData[l]?.hour || l} />
                                        <ReferenceLine y={40} stroke="#ef4444" strokeDasharray="6 3" /><Legend /><Line type="monotone" dataKey="tempF" dot={false} strokeWidth={2} stroke="#3b82f6" />
                                    </LineChart>
                                </ResponsiveContainer></div>
                                <div className="mt-3 grid gap-3 md:grid-cols-2">
                                    <div className="rounded-2xl border p-3"><div className="text-sm font-medium">Recent flags</div><div className="mt-2 space-y-1 max-h-[240px] overflow-auto">
                                        {topFlags.length === 0 ? <div className="text-sm text-muted-foreground">No flags.</div> : topFlags.map(p => (
                                            <button key={p.hour} className={`w-full rounded-xl border px-3 py-1.5 text-left text-xs transition hover:bg-muted/40 ${selectedHour === p.hour ? "bg-muted/50" : ""}`} onClick={() => setSelectedHour(p.hour)}>
                                                <span className="font-medium">{p.hour}</span> · {fmt(p.tempF)}°F {p.injectedAnomaly && <Badge className="rounded-xl ml-1" variant="secondary">GT</Badge>}
                                            </button>
                                        ))}
                                    </div></div>
                                    <div className="rounded-2xl border p-3"><div className="text-sm font-medium">Explainability</div><div className="mt-2 text-sm">
                                        {selectedHour ? <div><div className="font-medium text-xs">{selectedHour}</div><div className="mt-2 rounded-2xl bg-muted/40 p-3 text-sm">{det.explanations.get(selectedHour) || "No explanation."}</div></div> : <div className="text-muted-foreground">Click a flag to view explanation.</div>}
                                    </div></div>
                                </div>
                            </TabsContent>

                            <TabsContent value="daily" className="mt-3">
                                <div className="h-[260px] w-full rounded-2xl border p-2"><ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={dailyData} margin={{ top: 10, right: 14, bottom: 6, left: 6 }}>
                                        <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="label" tick={{ fontSize: 10 }} interval={Math.max(1, Math.floor(dailyData.length / 15))} /><YAxis domain={["dataMin - 1", "dataMax + 1"]} tick={{ fontSize: 10 }} />
                                        <Tooltip /><ReferenceLine y={40} stroke="#ef4444" strokeDasharray="6 3" />
                                        <Area type="monotone" dataKey="min" stackId="r" fill="transparent" stroke="transparent" /><Area type="monotone" dataKey="max" stackId="r" fill="rgba(59,130,246,0.08)" stroke="transparent" />
                                        <Line type="monotone" dataKey="avg" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="Avg" />
                                        <Line type="monotone" dataKey="max" stroke="#ef4444" strokeWidth={1} dot={(props: any) => { const { cx, cy, payload } = props; return payload.anomalyCount > 0 ? <circle cx={cx} cy={cy} r={4} fill="#ef4444" opacity={0.8} /> : <React.Fragment key={`d-${payload.day}`} />; }} name="Max" />
                                        <Line type="monotone" dataKey="min" stroke="#10b981" strokeWidth={1} dot={false} name="Min" /><Legend />
                                    </ComposedChart>
                                </ResponsiveContainer></div>
                                <div className="mt-3 h-[90px] rounded-2xl border p-2"><ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={dailyData}><XAxis dataKey="label" tick={{ fontSize: 9 }} interval={Math.max(1, Math.floor(dailyData.length / 15))} /><YAxis domain={[0, 1]} tick={{ fontSize: 9 }} /><Tooltip />
                                        <Bar dataKey="maxScore" radius={[2, 2, 0, 0]} name="Score">{dailyData.map((d, i) => <Cell key={i} fill={sevColor(d.maxScore)} />)}</Bar>
                                    </BarChart>
                                </ResponsiveContainer></div>
                            </TabsContent>

                            <TabsContent value="lots" className="mt-3">
                                <div className="h-[320px] w-full rounded-2xl border p-2"><ResponsiveContainer width="100%" height="100%">
                                    <ScatterChart margin={{ top: 10, right: 14, bottom: 30, left: 10 }}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="transitHours" name="Transit" type="number" label={{ value: "Transit Time (hours)", position: "insideBottom", offset: -15, fontSize: 11 }} />
                                        <YAxis dataKey="tempOnArrival" name="Temp" type="number" label={{ value: "Arrival Temp (°F)", angle: -90, position: "insideLeft", fontSize: 11 }} />
                                        <ZAxis range={[30, 30]} /><ReferenceLine y={40} stroke="#ef4444" strokeDasharray="6 3" /><ReferenceLine x={36} stroke="#f59e0b" strokeDasharray="6 3" />
                                        <Tooltip content={({ payload }: any) => { if (!payload?.[0]) return null; const d = payload[0].payload; return <div className="rounded-xl border bg-background p-2 text-xs shadow-lg"><div className="font-semibold">{d.lot}</div><div className="text-muted-foreground">{d.supplier}</div><div>Transit: {d.transitHours}h · {d.tempOnArrival}°F</div></div>; }} />
                                        <Legend /><Scatter name="Normal" data={normalLots} fill="#10b98166" /><Scatter name="Flagged" data={flaggedLots} fill="#ef4444" />
                                    </ScatterChart>
                                </ResponsiveContainer></div>
                            </TabsContent>

                            <TabsContent value="suppliers" className="mt-3">
                                <div className="grid gap-3 md:grid-cols-12">
                                    <div className="md:col-span-7 h-[300px] rounded-2xl border p-2"><ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={supplierMatrix}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="supplier" tick={false} /><YAxis domain={[0, 100]} /><Tooltip /><Legend />
                                            <Bar dataKey="score" name="Risk score" radius={[3, 3, 0, 0]}>{supplierMatrix.map((s, i) => <Cell key={i} fill={s.score > 40 ? "#ef4444" : s.score > 20 ? "#f59e0b" : "#10b981"} />)}</Bar>
                                        </BarChart>
                                    </ResponsiveContainer></div>
                                    <div className="md:col-span-5 max-h-[300px] overflow-auto rounded-2xl border">
                                        <Table><TableHeader><TableRow><TableHead>Supplier</TableHead><TableHead className="text-right">Flag%</TableHead><TableHead className="text-right">Score</TableHead></TableRow></TableHeader>
                                            <TableBody>{supplierMatrix.map(r => <TableRow key={r.id}><TableCell><div className="font-medium">{r.supplier}</div><div className="text-xs text-muted-foreground">{r.region} · {r.lots} lots · {r.avgTemp}°F avg</div></TableCell><TableCell className="text-right">{r.flaggedRate}%</TableCell><TableCell className="text-right"><Badge variant="secondary" className="rounded-xl">{r.score}</Badge></TableCell></TableRow>)}</TableBody>
                                        </Table></div>
                                </div>
                            </TabsContent>

                            <TabsContent value="eval" className="mt-3">
                                <div className="grid gap-3 md:grid-cols-2">
                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="rounded-2xl bg-emerald-500/10 border border-emerald-500/20 p-3"><div className="text-xs text-muted-foreground">True positives</div><div className="text-2xl font-semibold text-emerald-600">{conf.tp}</div></div>
                                        <div className="rounded-2xl bg-amber-500/10 border border-amber-500/20 p-3"><div className="text-xs text-muted-foreground">False positives</div><div className="text-2xl font-semibold text-amber-600">{conf.fp}</div></div>
                                        <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-3"><div className="text-xs text-muted-foreground">False negatives</div><div className="text-2xl font-semibold text-red-600">{conf.fn}</div></div>
                                        <div className="rounded-2xl bg-muted/40 p-3"><div className="text-xs text-muted-foreground">True negatives</div><div className="text-2xl font-semibold">{conf.tn}</div></div>
                                    </div>
                                </div>
                            </TabsContent>
                        </Tabs>
                    </div>
                    <div className="md:col-span-3 rounded-2xl border p-3">
                        <div className="flex items-center gap-2"><Sparkles className="h-4 w-4" /><div className="text-sm font-medium">What this proves</div></div>
                        <ul className="mt-2 space-y-2 text-sm text-muted-foreground">
                            <li>• Multi-algorithm detection</li><li>• Evaluation harness</li><li>• Explainability per event</li><li>• Cost-based tuning lens</li><li>• Daily aggregation</li>
                        </ul>
                    </div>
                </div>
            </CardContent></Card>
        </div>
    );
}
