'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ROI_CALCULATOR_CONFIG, calculateROI } from '@/lib/roi-calculator-data';
import { usePostHog } from '@/lib/posthog-provider';
import { trackBookCallClick } from '@/lib/conversion-events';
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

/** Hours per year, rounded. The public site shows no dollar amounts. */
function formatHours(hours: number): string {
    return `~${Math.round(hours).toLocaleString('en-US')} hrs/yr`;
}

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

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <StatTile
                        label="Labor Time, Illustrative"
                        value={formatHours(results.laborHours)}
                    >
                        <p className="text-small text-re-text-tertiary">Modeled labor time avoided per year based on your reported manual hours. Illustrative only.</p>
                    </StatTile>
                    <StatTile
                        label="Operational Time, Illustrative"
                        value={formatHours(results.operationalHours)}
                    >
                        <p className="text-small text-re-text-tertiary">Modeled time saved per record, per year. Illustrative only.</p>
                    </StatTile>
                    <StatTile
                        label="Total Modeled Time, Illustrative"
                        value={formatHours(results.totalHours)}
                    >
                        <p className="text-small text-re-text-tertiary">Sum of the two tiles. Illustrative only, not a forecast.</p>
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
                            onClick={() => trackBookCallClick('roi_calculator', 'roi-calculator')}
                            className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand"
                        >
                            Book a call
                        </a>{' '}
                        and we&apos;ll model it against your actual record volume and current
                        workload. The figures above are an illustrative starting point, not a commitment.
                    </p>
                </Callout>

                <Card variant="inset">
                    <CardContent className="p-4">
                        <h5 className="mb-2 text-label text-re-text-muted">Methodology Note</h5>
                        <p className="text-small leading-relaxed text-re-text-tertiary">
                            Estimates use simple multipliers applied to your reported hours and record volume, and are shown
                            in hours per year, not dollars.
                            We don&apos;t have verified customer ROI data yet, and the founding design partner price reflects that.
                            FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.
                            Actual results depend on your contracts,
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
                    <p className="text-title text-re-text-primary">
                        Estimate the Savings Opportunity
                    </p>
                    <p className="max-w-[70ch] text-ui text-re-text-secondary">
                        Get an illustrative sense of where traceability workflow automation could pay back. We don&apos;t
                        publish a promised ROI or payback period.
                    </p>
                </div>

                <FSMAToolShell
                    config={ROI_CALCULATOR_CONFIG}
                    renderResults={renderResults}
                    onLeadCapture={() => {
                        posthog?.capture('roi_calculated', {
                            tool_id: ROI_CALCULATOR_CONFIG.id,
                            lead_captured: true
                        });
                    }}
                />

                <div className="mt-12 grid grid-cols-1 gap-8 border-t border-re-border-subtle pt-8 md:grid-cols-3">
                    {[
                        {
                            title: 'Labor time avoided',
                            desc: 'Teams typically move record retrieval from hours to minutes. We don\'t have verified customer ROI data yet, and the founding design partner price reflects that.',
                            icon: Clock
                        },
                        {
                            title: 'Tamper-evident exports',
                            desc: 'Signed event records (downstream verification rolling out) give auditors verifiable evidence. They don\'t replace audits.',
                            icon: ShieldAlert
                        },
                        {
                            title: '§1.1455(c) ready',
                            desc: 'Designed to support the §1.1455(c) 24 hour records-on-request standard once your data is in the system.',
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
