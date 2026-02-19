'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { Badge } from '@/components/ui/badge';
import { Shield, Search, AlertTriangle, CheckCircle2, FlaskConical, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

const TLC_VALIDATOR_CONFIG: ToolConfig = {
    id: 'tlc-validator',
    title: 'TLC Validator',
    description: 'Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDAs requirement for uniqueness and parseability.',
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
            title: 'Download the Lot Coding Standard',
            description: 'Get our guide on "Defensible Lot Coding" to ensure your TLCs survive an FDA audit and maintain GS1 compatibility.',
            cta: 'Download Standard'
        }
    }
};

export default function TLCValidatorPage() {
    const analyzeTLC = (answers: Record<string, any>) => {
        const tlc = (answers.tlc_input || '').trim();
        if (!tlc) return null;

        const findings = [];
        let score = 100;

        // 1. GS1 Compatibility Check
        if (tlc.includes('(10)') || tlc.startsWith('10')) {
            findings.push({ severity: 'LOW', label: 'GS1 AI 10 detected (Standard compatible)', icon: CheckCircle2 });
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

        // 4. Parseability (Ambiguous Chars)
        if (/[0OI1l]/.test(tlc)) {
            findings.push({ severity: 'MEDIUM', label: 'Ambiguous characters detected (0/O, 1/I) - Risks manual entry errors', icon: Search });
            score -= 10;
        }

        // 5. Structure Hint
        if (/[A-Z]/.test(tlc) && /[0-9]/.test(tlc)) {
            findings.push({ severity: 'LOW', label: 'Alphanumeric mix provides better uniqueness', icon: CheckCircle2 });
        } else {
            findings.push({ severity: 'MEDIUM', label: 'Uniform character set (Higher collision risk)', icon: Search });
            score -= 5;
        }

        const getScoreColor = (s: number) => {
            if (s >= 80) return 'var(--re-brand)';
            if (s >= 50) return 'var(--re-warning)';
            return 'var(--re-danger)';
        };

        return (
            <div className="space-y-8">
                <div className="flex flex-col items-center py-6 border-b border-[var(--re-border-default)]">
                    <div
                        className="text-4xl font-black mb-2"
                        style={{ color: getScoreColor(score) }}
                    >
                        {score}/100
                    </div>
                    <Badge variant="outline" className="uppercase tracking-widest text-[10px]">Quality Score</Badge>
                    <div className="mt-4 font-mono bg-[var(--re-surface-elevated)] px-4 py-2 rounded border border-[var(--re-border-default)]">
                        {tlc}
                    </div>
                </div>

                <div className="space-y-4">
                    <h4 className="text-sm font-semibold uppercase tracking-wider text-[var(--re-text-muted)]">Analysis Findings</h4>
                    <div className="space-y-3">
                        {findings.length === 0 ? (
                            <div className="flex items-center gap-3 p-4 rounded-xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)] / 20">
                                <CheckCircle2 className="h-5 w-5 text-[var(--re-brand)]" />
                                <span className="text-sm">Excellent! Your lot code is stable and system-compatible.</span>
                            </div>
                        ) : (
                            findings.map((f, i) => (
                                <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-sm">
                                    <f.icon className={`h-4 w-4 shrink-0 ${f.severity === 'HIGH' ? 'text-[var(--re-danger)]' : 'text-[var(--re-warning)]'}`} />
                                    <span className="text-[var(--re-text-primary)]">{f.label}</span>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                <div className="p-6 rounded-2xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)] / 20 text-center">
                    <h4 className="font-bold mb-2">Automate TLC Integrity</h4>
                    <p className="text-xs text-[var(--re-text-secondary)] mb-4">
                        RegEngine enforces TLC stability across your entire supply chain, preventing re-labeling errors that lead to audit failure.
                    </p>
                    <Button className="bg-[var(--re-brand)] w-full gap-2">
                        Schedule a Demo <ArrowRight className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <FSMAToolShell
                config={TLC_VALIDATOR_CONFIG}
                renderResults={analyzeTLC}
            />
        </div>
    );
}
