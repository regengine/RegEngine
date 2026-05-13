'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ROI_CALCULATOR_CONFIG, calculateROI } from '@/lib/roi-calculator-data';
import { usePostHog } from '@/lib/posthog-provider';
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
                    <p className="text-sm uppercase tracking-widest text-[var(--re-text-muted)]">Illustrative · not a forecast</p>
                    <h3 className="text-2xl font-semibold text-[var(--re-text-primary)]">
                        Rough sense of where automation could pay back
                    </h3>
                    <p className="text-[var(--re-text-tertiary)] max-w-xl mx-auto">
                        Numbers below are illustrative based on your inputs. Actual savings depend on your
                        contracts, staffing, and existing systems. We don&apos;t publish a guaranteed ROI or payback
                        period.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <ResultCard
                        title="Labor Time, Illustrative"
                        value={`~$${(results.laborSavings / 1000).toFixed(1)}k`}
                        description="Modeled labor-time avoided based on your reported manual hours. Illustrative only."
                        icon={Clock}
                        color="text-re-info bg-blue-400"
                    />
                    <ResultCard
                        title="Risk Concentration, Illustrative"
                        value={`~$${(results.riskReduction / 1000).toFixed(1)}k`}
                        description="A small fraction of revenue used as a placeholder for compliance-event exposure. Illustrative; not a forecast or fine schedule."
                        icon={ShieldAlert}
                        color="text-re-danger bg-re-danger"
                    />
                    <ResultCard
                        title="Operational Time, Illustrative"
                        value={`~$${(results.operationalEfficiency / 1000).toFixed(1)}k`}
                        description="Modeled time saved per record. Illustrative only."
                        icon={Zap}
                        color="text-re-warning bg-yellow-400"
                    />
                    <ResultCard
                        title="Modeled Benefit Minus Platform"
                        value={`~$${(results.netBenefit / 1000).toFixed(1)}k`}
                        description="Modeled annual benefit minus an estimated platform cost. Illustrative only."
                        icon={TrendingUp}
                        color="text-re-brand bg-re-brand"
                    />
                </div>

                <Card className="bg-[var(--re-brand-muted)] border-[var(--re-brand)]/20 overflow-hidden">
                    <div className="p-6 space-y-2">
                        <h4 className="text-base font-semibold flex items-center gap-2">
                            <Target className="h-4 w-4 text-[var(--re-brand)]" />
                            We don&apos;t publish a guaranteed ROI or payback period
                        </h4>
                        <p className="text-sm text-[var(--re-text-secondary)]">
                            Book a 20-minute call and we&apos;ll model it against your actual record volume and current
                            spend. The figures above are an illustrative starting point, not a commitment.
                        </p>
                    </div>
                </Card>

                <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]/30">
                    <h5 className="text-xs font-bold uppercase tracking-widest text-[var(--re-text-muted)] mb-2">Methodology Note</h5>
                    <p className="text-[10px] text-[var(--re-text-tertiary)] leading-relaxed">
                        Estimates use simple multipliers applied to your reported hours, record volume, and revenue.
                        We don&apos;t have verified customer ROI data yet — early-design partner pricing reflects that.
                        FSMA 204 enforcement begins July 20, 2028; no public fine schedule exists, so the
                        risk-concentration tile is illustrative only. Actual results depend on your contracts,
                        existing systems, staffing, and data hygiene.
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
                        Estimate the <span className="text-[var(--re-brand)]">Savings Opportunity</span>
                    </h1>
                    <p className="text-xl text-[var(--re-text-tertiary)] max-w-2xl mx-auto">
                        Get an illustrative sense of where compliance automation could pay back. We don&apos;t
                        publish a guaranteed ROI or payback period.
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
                            title: 'Labor time avoided',
                            desc: 'Teams typically move record retrieval from hours to minutes. We don\'t have verified customer ROI data yet — early-design partner pricing reflects that.',
                            icon: Clock
                        },
                        {
                            title: 'Tamper-evident exports',
                            desc: 'Signed event records (downstream verification rolling out) give auditors verifiable evidence — they don\'t replace audits.',
                            icon: ShieldAlert
                        },
                        {
                            title: '§1.1455(c) ready',
                            desc: 'Designed to support the §1.1455(c) 24-hour records-on-request standard once your data is in the system.',
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
