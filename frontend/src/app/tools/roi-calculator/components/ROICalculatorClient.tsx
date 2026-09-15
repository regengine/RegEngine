'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ROI_CALCULATOR_CONFIG, calculateROI } from '@/lib/roi-calculator-data';
import { usePostHog } from '@/lib/posthog-provider';
import { Card, CardContent } from '@/components/ui/card';
import { Callout } from '@/components/ui/callout';
import { Container } from '@/components/layout/container';
import { StatTile } from '@/components/ui/stat-tile';
import {
    Clock,
    ShieldAlert,
    Zap,
    Target,
} from 'lucide-react';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

export function ROICalculatorClient() {
    const posthog = usePostHog();

    const renderResults = (answers: Record<string, any>) => {
        const results = calculateROI(answers);

        return (
            <div className="space-y-8">
                <div className="space-y-2 text-center">
                    <p className="text-label text-re-text-muted">Illustrative · not a forecast</p>
                    <h3 className="text-heading text-re-text-primary">
                        Rough sense of where automation could pay back
                    </h3>
                    <p className="mx-auto max-w-[60ch] text-ui text-re-text-tertiary">
                        Numbers below are illustrative based on your inputs. Actual savings depend on your
                        contracts, staffing, and existing systems. We don&apos;t publish a promised ROI or payback
                        period.
                    </p>
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <StatTile
                        label="Labor Time, Illustrative"
                        value={`~$${(results.laborSavings / 1000).toFixed(1)}k`}
                    >
                        <p className="text-small text-re-text-tertiary">Modeled labor-time avoided based on your reported manual hours. Illustrative only.</p>
                    </StatTile>
                    <StatTile
                        label="Risk Concentration, Illustrative"
                        value={`~$${(results.riskReduction / 1000).toFixed(1)}k`}
                    >
                        <p className="text-small text-re-text-tertiary">A small fraction of revenue used as a placeholder for compliance-event exposure. Illustrative; not a forecast or fine schedule.</p>
                    </StatTile>
                    <StatTile
                        label="Operational Time, Illustrative"
                        value={`~$${(results.operationalEfficiency / 1000).toFixed(1)}k`}
                    >
                        <p className="text-small text-re-text-tertiary">Modeled time saved per record. Illustrative only.</p>
                    </StatTile>
                    <StatTile
                        label="Modeled Benefit Minus Platform"
                        value={`~$${(results.netBenefit / 1000).toFixed(1)}k`}
                    >
                        <p className="text-small text-re-text-tertiary">Modeled annual benefit minus an estimated platform cost. Illustrative only.</p>
                    </StatTile>
                </div>

                <Callout
                    tone="info"
                    icon={Target}
                    title="We don't publish a promised ROI or payback period"
                >
                    <p className="text-ui text-re-text-secondary">
                        <a
                            href="https://calendly.com/regengine/fsma-strategy-session"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand"
                        >
                            Book a call
                        </a>{' '}
                        and we&apos;ll model it against your actual record volume and current
                        spend. The figures above are an illustrative starting point, not a commitment.
                    </p>
                </Callout>

                <Card variant="inset">
                    <CardContent className="p-4">
                        <h5 className="mb-2 text-label text-re-text-muted">Methodology Note</h5>
                        <p className="text-small leading-relaxed text-re-text-tertiary">
                            Estimates use simple multipliers applied to your reported hours, record volume, and revenue.
                            We don&apos;t have verified customer ROI data yet — early-design partner pricing reflects that.
                            Current public FDA posture points to July 20, 2028 as the earliest enforcement date; no public fine schedule exists, so the
                            risk-concentration tile is illustrative only. Actual results depend on your contracts,
                            existing systems, staffing, and data hygiene.
                        </p>
                    </CardContent>
                </Card>
            </div>
        );
    };

    return (
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            <Container width="tool">
                <div className="mb-10 space-y-3 border-b border-re-border-subtle pb-5">
                    <p className="text-label text-re-text-muted">ROI Engine</p>
                    <h1 className="text-title text-re-text-primary">
                        Estimate the Savings Opportunity
                    </h1>
                    <p className="max-w-[70ch] text-ui text-re-text-secondary">
                        Get an illustrative sense of where traceability workflow automation could pay back. We don&apos;t
                        publish a promised ROI or payback period.
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

                <div className="mt-12 grid grid-cols-1 gap-8 border-t border-re-border-subtle pt-8 md:grid-cols-3">
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
                        <div key={i} className="space-y-2">
                            <item.icon aria-hidden="true" className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} />
                            <h4 className="text-subheading text-re-text-primary">{item.title}</h4>
                            <p className="text-small leading-relaxed text-re-text-tertiary">{item.desc}</p>
                        </div>
                    ))}
                </div>

                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['fsma-unified', 'recall-readiness', 'drill-simulator'].includes(t.id))}
                />
            </Container>
        </div>
    );
}
