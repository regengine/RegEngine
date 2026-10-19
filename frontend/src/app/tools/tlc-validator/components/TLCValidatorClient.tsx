'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { usePostHog } from '@/lib/posthog-provider';
import { trackBookCallClick } from '@/lib/conversion-events';
import { Badge } from '@/components/ui/badge';
import { Search, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const TLC_VALIDATOR_CONFIG: ToolConfig = {
    id: 'tlc-validator',
    title: 'TLC Format Check',
    description: 'Stress-test your Traceability Lot Code (TLC) format against GS1 conventions and common entropy/parseability pitfalls. FDA does not specify a TLC format; uniqueness must be enforced by your assignment system.',
    icon: 'FlaskConical',
    stages: {
        questions: [
            {
                id: 'tlc_input',
                text: 'Paste an example Traceability Lot Code (TLC) used by your company:',
                type: 'text',
                placeholder: 'e.g. (10)ABC12345 or 2024-FAC1-LOT001',
                hint: 'We analyze the structure for GS1 compatibility and entropy risks.'
            }
        ],
        leadGate: {
            title: 'Unlock Your Validation Results',
            description: 'See the full in-browser analysis of your TLC structure, including GS1 compatibility, entropy, and parseability checks, with guidance on making your lot codes defensible.',
            cta: 'Show Results'
        }
    }
};

export function TLCValidatorClient() {
    const posthog = usePostHog();

    const analyzeTLC = (answers: Record<string, any>) => {
        const tlc = (answers.tlc_input || '').trim();
        if (!tlc) return null;

        const findings = [];
        let score = 100;

        // 1. GS1 Compatibility Check
        if (tlc.includes('(10)') || tlc.startsWith('10')) {
            findings.push({ severity: 'LOW', label: "Starts with '10'. This may be a GS1 AI (10) batch/lot prefix; verify against your GS1 spec.", icon: CheckCircle2 });
            score += 5; // Bonus for standard alignment
        } else if (!/^[A-Z0-9]+$/.test(tlc)) {
            findings.push({ severity: 'MEDIUM', label: 'Non-alphanumeric chars detected (GS1 preference is clean alphanumeric)', icon: Search });
            score -= 10;
        }

        // 2. Uniqueness / Entropy
        if (tlc.length < 6) {
            findings.push({ severity: 'HIGH', label: 'Code too short (High risk of duplication/collision)', icon: AlertTriangle });
            score -= 40;
        }

        // 3. Sequential / Predictable
        if (/^\d+$/.test(tlc) && tlc.length < 10) {
            findings.push({ severity: 'MEDIUM', label: 'Sequential numeric code (Low entropy; difficult to distinguish from order IDs)', icon: AlertTriangle });
            score -= 20;
        }

        // 4. Parseability (easily-confused letters O/I/l, which read like 0/1)
        if (/[OIl]/.test(tlc)) {
            findings.push({ severity: 'MEDIUM', label: 'Consider avoiding easily-confused characters (O/0, I/1, l/1) to reduce manual entry errors', icon: Search });
            score -= 10;
        }

        // 5. Structure Hint
        if (/[A-Z]/.test(tlc) && /[0-9]/.test(tlc)) {
            findings.push({ severity: 'LOW', label: 'Alphanumeric mix provides better uniqueness', icon: CheckCircle2 });
        } else {
            findings.push({ severity: 'MEDIUM', label: 'Uniform character set (Higher collision risk)', icon: Search });
            score -= 5;
        }

        // The heuristic total stays internal — it tunes the summary tone only.
        // It is deliberately never rendered as a grade or a score out of 100.
        const summaryTone: 'neutral' | 'warning' | 'danger' =
            score >= 80 ? 'neutral' : score >= 50 ? 'warning' : 'danger';

        return (
            <div className="space-y-8">
                <div className="flex flex-col items-center gap-4 border-b border-re-border-subtle py-6">
                    <Badge tone={summaryTone} mono>
                        {findings.length === 0 ? 'No structural concerns detected' : `${findings.length} heuristic finding${findings.length === 1 ? '' : 's'}`}
                    </Badge>
                    <div className="max-w-full break-all rounded-md border border-re-border bg-re-surface-inset px-4 py-2 font-mono text-[0.8125rem] text-re-text-primary">
                        {tlc}
                    </div>
                </div>

                <div className="space-y-4">
                    <h4 className="text-label text-re-text-muted">Analysis Findings</h4>
                    <div className="space-y-3">
                        {findings.length === 0 ? (
                            <Callout tone="success" icon={CheckCircle2}>
                                No structural concerns detected by the heuristic checks. This is not a uniqueness promise. Uniqueness must be enforced by your assignment system.
                            </Callout>
                        ) : (
                            findings.map((f, i) => (
                                <Callout key={i} tone={f.severity === 'HIGH' ? 'danger' : 'warning'} icon={f.icon}>
                                    {f.label}
                                </Callout>
                            ))
                        )}
                    </div>
                </div>

                <Card>
                    <CardContent className="space-y-3 text-center">
                        <h4 className="text-subheading text-re-text-primary">Automate TLC Integrity</h4>
                        <p className="text-small text-re-text-secondary">
                            RegEngine enforces TLC stability across your entire supply chain, preventing re-labeling errors that lead to audit failure.
                        </p>
                        <Button asChild variant="secondary" size="lg" className="w-full gap-2">
                            <a
                                href="https://calendly.com/regengine/fsma-strategy-session"
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={() => trackBookCallClick('tlc_validator', 'tlc-validator')}
                            >
                                Schedule a Demo <ArrowRight aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
                            </a>
                        </Button>
                    </CardContent>
                </Card>
            </div>
        );
    };

    return (
        <>
            <FSMAToolShell
                config={TLC_VALIDATOR_CONFIG}
                renderResults={analyzeTLC}
                onLeadCapture={() => {
                    posthog?.capture('tlc_validated', {
                        tool_id: TLC_VALIDATOR_CONFIG.id,
                        lead_captured: true
                    });
                }}
            />

            <RelatedTools
                tools={FREE_TOOLS.filter(t => ['kde-checker', 'cte-mapper', 'ftl-checker'].includes(t.id))}
            />
        </>
    );
}
