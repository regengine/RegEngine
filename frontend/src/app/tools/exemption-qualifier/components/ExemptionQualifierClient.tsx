'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, AlertTriangle, Info, ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const EXEMPTION_TOOL_CONFIG: ToolConfig = {
    id: 'exemption-qualifier',
    title: 'Exemption Qualifier',
    description: 'Determine if your operation is exempt, partially exempt, or fully covered under FSMA 204.',
    icon: 'Shield',
    stages: {
        questions: [
            {
                id: 'op_type',
                text: 'What type of operation are you?',
                type: 'select',
                options: [
                    { label: 'Farm / Farm Mixed-Type', value: 'farm' },
                    { label: 'Processor / Manufacturer', value: 'processor' },
                    { label: 'Distributor / Warehouse', value: 'distributor' },
                    { label: 'Retail Food Establishment / Restaurant', value: 'rfe' },
                ]
            },
            {
                id: 'rcr_produce',
                text: 'Is the food you handle on the "Rarely Consumed Raw" list?',
                type: 'select',
                hint: 'e.g., Asparagus, beans, cocoa beans, coffee beans, potatoes, etc. (Ref: §1.1305(e))',
                options: [
                    { label: 'Yes, it is RCR', value: true },
                    { label: 'No / Not Sure', value: false },
                ]
            },
            {
                id: 'turnover',
                text: 'What is your 3-year rolling average for annual food sales?',
                type: 'select',
                options: [
                    { label: 'Under $250,000', value: 'under_250k' },
                    { label: '$250,000 - $500,000', value: 'under_500k' },
                    { label: 'Over $500,000', value: 'over_500k' },
                ]
            },
            {
                id: 'farm_purchase',
                text: 'Do you purchase FTL foods directly from a farm?',
                type: 'select',
                hint: 'Applies to restaurants and retail establishments.',
                options: [
                    { label: 'Yes', value: true },
                    { label: 'No', value: false },
                ],
                dependency: { questionId: 'op_type', value: 'rfe' }
            },
            {
                id: 'kill_step',
                text: 'Is the food subjected to a "Kill Step" (e.g., commercial processing to reduce pathogens)?',
                type: 'select',
                hint: 'Ref: 21 CFR §1.1305(d)',
                options: [
                    { label: 'Yes, we apply it', value: 'we_apply' },
                    { label: 'Yes, a customer/partner applies it', value: 'partner_applies' },
                    { label: 'No kill step', value: 'none' },
                ],
                dependency: { questionId: 'op_type', value: 'processor' }
            }
        ],
        leadGate: {
            title: 'Download Your Official Exemption Blueprint',
            description: 'Get a customized PDF guide including the specific 21 CFR Subpart S citations for your facility type and volume.',
            cta: 'Send My Guide'
        }
    }
};

export function ExemptionQualifierClient() {
    const evaluateResults = (answers: Record<string, any>) => {
        const { op_type, turnover, farm_purchase, kill_step, rcr_produce } = answers;

        let status: 'EXEMPT' | 'PARTIAL' | 'COVERED' = 'COVERED';
        let title = 'Likely Covered';
        let alertColor = 'var(--re-danger)';
        let reason = 'Based on your inputs, you are likely subject to full FSMA 204 recordkeeping requirements.';

        if (rcr_produce === true) {
            status = 'EXEMPT';
            title = 'Likely Exempt (RCR)';
            alertColor = 'var(--re-brand)';
            reason = 'Foods on the "Rarely Consumed Raw" list (e.g., potatoes, coffee beans, asparagus) are exempt under 21 CFR §1.1305(e).';
        } else if (op_type === 'rfe' && turnover === 'under_250k') {
            status = 'EXEMPT';
            title = 'Small Establishment Exemption';
            alertColor = 'var(--re-brand)';
            reason = 'Retail Food Establishments with ≤ $250k in annual food sales are exempt under 21 CFR §1.1305(h).';
        } else if (op_type === 'rfe' && farm_purchase === true) {
            status = 'PARTIAL';
            title = 'Partial Exemption (RFE/Farm)';
            alertColor = 'var(--re-warning)';
            reason = 'Purchasing directly from a farm grants a partial exemption, but you must maintain the farm\'s name and address for 180 days (21 CFR §1.1305(j)).';
        } else if (kill_step === 'we_apply') {
            status = 'PARTIAL';
            title = 'Partial Exemption (Kill Step)';
            alertColor = 'var(--re-warning)';
            reason = 'Applying a "Kill Step" exempts you from recordkeeping AFTER transformation, but you must still keep records for the received inputs (21 CFR §1.1305(d)).';
        } else if (kill_step === 'partner_applies') {
            status = 'COVERED';
            title = 'Likely Covered (Kill Step Prep)';
            alertColor = 'var(--re-danger)';
            reason = 'If a customer applies the kill step, you remain covered for all CTEs but must provide specific documentation to your customer per 21 CFR §1.1305(d)(3).';
        }

        return (
            <div className="space-y-6">
                <div
                    className="p-6 rounded-2xl border flex items-start gap-4"
                    style={{ borderColor: `${alertColor}40`, background: `${alertColor}10` }}
                >
                    {status === 'EXEMPT' ? (
                        <CheckCircle2 className="h-6 w-6 shrink-0" style={{ color: alertColor }} />
                    ) : status === 'PARTIAL' ? (
                        <Info className="h-6 w-6 shrink-0" style={{ color: alertColor }} />
                    ) : (
                        <AlertTriangle className="h-6 w-6 shrink-0" style={{ color: alertColor }} />
                    )}
                    <div>
                        <h4 className="text-xl font-bold mb-1" style={{ color: alertColor }}>{title}</h4>
                        <p className="text-sm opacity-90">{reason}</p>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                        <h5 className="font-semibold mb-2">What this means</h5>
                        <ul className="text-xs space-y-2 text-[var(--re-text-tertiary)]">
                            <li>• Use RegEngine to verify supplier compliance</li>
                            <li>• Keep digital records of all FTL transactions</li>
                            <li>• Ensure 24-hour retrieval capability</li>
                        </ul>
                    </div>
                    <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                        <h5 className="font-semibold mb-2">Next Steps</h5>
                        <Link href="/ftl-checker" className="text-xs text-[var(--re-brand)] flex items-center gap-1 hover:underline">
                            Check your product list <ArrowRight className="h-3 w-3" />
                        </Link>
                        <Link href="/fsma/dashboard" className="text-xs text-[var(--re-brand)] flex items-center gap-1 mt-2 hover:underline">
                            View your compliance score <ArrowRight className="h-3 w-3" />
                        </Link>
                    </div>
                </div>

                <div className="pt-4">
                    <Badge variant="outline" className="text-[10px] uppercase tracking-wider opacity-60">
                        Reference: 21 CFR § 1.1305
                    </Badge>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <FSMAToolShell
                config={EXEMPTION_TOOL_CONFIG}
                renderResults={evaluateResults}
            />

            <div className="max-w-3xl mx-auto">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['ftl-checker', 'roi-calculator', 'recall-readiness'].includes(t.id))}
                />
            </div>
        </div>
    );
}
