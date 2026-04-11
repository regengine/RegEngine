'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ROI_CALCULATOR_CONFIG, calculateROI } from '@/lib/roi-calculator-data';
import { usePostHog } from 'posthog-js/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Calculator,
    TrendingUp,
    Clock,
    ShieldAlert,
    Zap,
    ArrowRight,
    LucideIcon,
    DollarSign,
    Target,
    BarChart3
} from 'lucide-react';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

export function ROICalculatorClient() {
    const posthog = usePostHog();

    const renderResults = (answers: Record<string, any>) => {
        const results = calculateROI(answers);

        const ResultCard = ({
            title,
            value,
            description,
            icon: Icon,
            color
        }: {
            title: string;
            value: string;
            description: string;
            icon: LucideIcon;
            color: string
        }) => (
            <div className="p-6 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] space-y-3">
                <div className="flex justify-between items-start">
                    <div className={`p-2 rounded-lg ${color} bg-opacity-10`}>
                        <Icon className={`h-5 w-5 ${color.replace('bg-', 'text-')}`} />
                    </div>
                    <div className="text-2xl font-bold text-[var(--re-text-primary)]">{value}</div>
                </div>
                <div>
                    <div className="text-sm font-semibold text-[var(--re-text-secondary)]">{title}</div>
                    <div className="text-xs text-[var(--re-text-tertiary)] mt-1">{description}</div>
                </div>
            </div>
        );

        return (
            <div className="space-y-8">
                <div className="text-center space-y-2">
                    <h3 className="text-3xl font-bold text-[var(--re-brand)]">
                        ${(results.netBenefit / 1000).toFixed(1)}k Total Annual ROI
                    </h3>
                    <p className="text-[var(--re-text-tertiary)]">
                        Based on your profile, here is your estimated compliance cost-savings breakdown.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <ResultCard
                        title="Labor Cost Savings"
                        value={`$${(results.laborSavings / 1000).toFixed(1)}k`}
                        description="Savings from automated data entry and 24hr record retrieval."
                        icon={Clock}
                        color="text-re-info bg-blue-400"
                    />
                    <ResultCard
                        title="Risk Mitigation"
                        value={`$${(results.riskReduction / 1000).toFixed(1)}k`}
                        description="Reduction in potential violation fines and recall impacts."
                        icon={ShieldAlert}
                        color="text-re-danger bg-red-400"
                    />
                    <ResultCard
                        title="Operational Gains"
                        value={`$${(results.operationalEfficiency / 1000).toFixed(1)}k`}
                        description="Efficiency impact of real-time supply chain visibility."
                        icon={Zap}
                        color="text-re-warning bg-yellow-400"
                    />
                    <ResultCard
                        title="Net Platform Benefit"
                        value={`$${(results.netBenefit / 1000).toFixed(1)}k`}
                        description="Total benefit minus estimated platform investment."
                        icon={TrendingUp}
                        color="text-re-brand bg-emerald-400"
                    />
                </div>

                <Card className="bg-[var(--re-brand-muted)] border-[var(--re-brand)]/20 overflow-hidden">
                    <div className="p-6 flex flex-col md:flex-row items-center justify-between gap-6">
                        <div className="space-y-1">
                            <h4 className="text-xl font-bold flex items-center gap-2">
                                <Target className="h-5 w-5 text-[var(--re-brand)]" />
                                {results.paybackMonths.toFixed(1)} Month Payback
                            </h4>
                            <p className="text-sm text-[var(--re-text-secondary)]">
                                Your investment pays for itself in just a few months of operational use.
                            </p>
                        </div>
                        <div className="text-4xl font-black text-[var(--re-brand)]">
                            {results.roi.toFixed(0)}% <span className="text-sm font-medium">ROI</span>
                        </div>
                    </div>
                </Card>

                <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]/30">
                    <h5 className="text-xs font-bold uppercase tracking-widest text-[var(--re-text-muted)] mb-2">Methodology Note</h5>
                    <p className="text-[10px] text-[var(--re-text-tertiary)] leading-relaxed">
                        ROI estimates are based on industry benchmarks for FSMA 204 compliance labor reduction (85%) and risk mitigation.
                        Operational efficiency gains are conservatively capped at 35% of total benefit to account for variance in supply chain complexity.
                        Actual results may vary based on existing ERP integrations and internal data hygiene.
                    </p>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <div className="max-w-7xl mx-auto">
                <div className="text-center mb-16 space-y-4">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-xs font-bold uppercase tracking-widest">
                        <BarChart3 className="h-3 w-3" /> ROI Engine
                    </div>
                    <h1 className="text-4xl md:text-5xl font-black">
                        The Cost of <span className="text-[var(--re-brand)]">Doing Nothing</span>
                    </h1>
                    <p className="text-xl text-[var(--re-text-tertiary)] max-w-2xl mx-auto">
                        Quantify the financial impact of manual compliance vs. the RegEngine platform.
                    </p>
                </div>

                <FSMAToolShell
                    config={ROI_CALCULATOR_CONFIG}
                    renderResults={renderResults}
                    onLeadCapture={(lead) => {
                        if (lead.email) {
                            posthog?.capture('roi_calculated', {
                                email: lead.email,
                                answers: lead.answers
                            });
                            posthog?.identify(lead.email, { email: lead.email });
                        }
                    }}
                />

                <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-8">
                    {[
                        {
                            title: 'Labor Reduction',
                            desc: 'Average 85% drop in time spent on data entry and record matching.',
                            icon: Clock
                        },
                        {
                            title: 'Math Trust™',
                            desc: 'Cryptographic proof eliminates the need for expensive secondary audits.',
                            icon: ShieldAlert
                        },
                        {
                            title: '24hr Response',
                            desc: 'Meet the FDA 24hr mandate instantly without emergency manual extraction.',
                            icon: Zap
                        }
                    ].map((item, i) => (
                        <div key={i} className="space-y-4 text-center md:text-left">
                            <div className="inline-flex p-3 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                <item.icon className="h-6 w-6 text-[var(--re-brand)]" />
                            </div>
                            <h4 className="font-bold text-lg">{item.title}</h4>
                            <p className="text-sm text-[var(--re-text-tertiary)] leading-relaxed">{item.desc}</p>
                        </div>
                    ))}
                </div>

                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['fsma-unified', 'recall-readiness', 'drill-simulator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
