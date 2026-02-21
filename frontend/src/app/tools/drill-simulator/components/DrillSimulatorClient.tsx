'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { usePostHog } from 'posthog-js/react';
import { motion } from 'framer-motion';
import { Timer, AlertTriangle, ShieldCheck, Zap, Ghost, AlertCircle, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const DRILL_TOOL_CONFIG: ToolConfig = {
    id: 'drill-simulator',
    title: '24-Hour Drill Simulator',
    description: 'Simulate a real-time FDA request for FSMA 204 records. Can your team beat the clock?',
    icon: 'Timer',
    stages: {
        questions: [
            {
                id: 'scenario',
                text: 'Scenario: FDA reports a potential Salmonella link in Cantaloupes. They need records for Lot #CT-2024-X1. Where do you start?',
                type: 'select',
                options: [
                    { label: 'Search the digital ERP/WMS', value: 'digital', weight: 0.5 },
                    { label: 'Locate the paper Bill of Lading folder', value: 'paper', weight: 4 },
                    { label: 'Wait for the shift manager to arrive', value: 'wait', weight: 8 },
                ]
            },
            {
                id: 'tlc_source',
                text: 'You found the receiving record, but the Traceability Lot Code Source is missing. How do you find it?',
                type: 'select',
                options: [
                    { label: 'Email the supplier and wait', value: 'email', weight: 12 },
                    { label: 'Check the incoming GS1-128 barcode log', value: 'barcode', weight: 1 },
                    { label: 'Call the driver who delivered it', value: 'call', weight: 6 },
                ]
            },
            {
                id: 'compilation',
                text: 'FDA wants the "Sortable Spreadsheet" format. How do you compile the 14 required KDEs?',
                type: 'select',
                options: [
                    { label: 'Manual data entry into Excel', value: 'manual', weight: 10 },
                    { label: 'Run a pre-configured report', value: 'report', weight: 0.5 },
                    { label: 'Copy-paste from PDF invoices', value: 'copy_paste', weight: 6 },
                ]
            },
            {
                id: 'verification',
                text: 'One shipment was split into two transformations. How do you link the new TLC to the old one?',
                type: 'select',
                options: [
                    { label: 'Check the production log book', value: 'log', weight: 4 },
                    { label: 'Digital lineage lookup', value: 'digital', weight: 0.1 },
                    { label: 'Ask the production lead to remember', value: 'memory', weight: 24 },
                ]
            }
        ],
        leadGate: {
            title: 'Get Your Drill Results & Playbook',
            description: 'We will send you a breakdown of your "Simulated Response Cost" and a 24-hour drill playbook for your team.',
            cta: 'Send My Playbook'
        }
    }
};

export function DrillSimulatorClient() {
    const posthog = usePostHog();

    const calculateResult = (answers: Record<string, any>) => {
        let totalHours = 0;
        DRILL_TOOL_CONFIG.stages.questions.forEach(q => {
            const selected = answers[q.id];
            const opt = q.options?.find(o => o.value === selected);
            if (opt?.weight) totalHours += opt.weight;
        });

        const isFail = totalHours > 24;
        const color = isFail ? 'var(--re-danger)' : 'var(--re-brand)';

        return (
            <div className="space-y-8">
                <div className="text-center py-6">
                    <motion.div
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        className="inline-flex items-center justify-center w-32 h-32 rounded-full border-4 mb-4 relative overflow-hidden"
                        style={{ borderColor: color }}
                    >
                        <div
                            className="absolute bottom-0 left-0 right-0 bg-red-500/20 transition-all duration-1000"
                            style={{ height: `${Math.min(100, (totalHours / 24) * 100)}%` }}
                        />
                        <div className="relative flex flex-col items-center">
                            <span className="text-4xl font-black" style={{ color }}>{totalHours.toFixed(1)}h</span>
                            <span className="text-[10px] uppercase font-bold tracking-widest opacity-60">Total Time</span>
                        </div>
                    </motion.div>
                    <h3 className="text-2xl font-bold">
                        {isFail ? '24-Hour Deadline Missed' : 'Compliance Target Met'}
                    </h3>
                    <p className="text-[var(--re-text-tertiary)] mt-1">
                        {isFail
                            ? 'You exceeded the FDA-mandated response window.'
                            : 'You successfully Beat the Clock.'}
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] text-center">
                        <Zap className="h-5 w-5 mx-auto mb-2 text-[var(--re-warning)]" />
                        <div className="text-lg font-bold">{(totalHours * 125).toLocaleString('en-US', { style: 'currency', currency: 'USD' })}</div>
                        <div className="text-[10px] uppercase text-[var(--re-text-muted)]">Estimated Labor Cost</div>
                    </div>
                    <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] text-center">
                        <Ghost className="h-5 w-5 mx-auto mb-2 text-[var(--re-danger)]" />
                        <div className="text-lg font-bold">{isFail ? 'CRITICAL' : 'LOW'}</div>
                        <div className="text-[10px] uppercase text-[var(--re-text-muted)]">Inventory Spoilage Risk</div>
                    </div>
                    <div className="p-4 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] text-center">
                        <ShieldCheck className="h-5 w-5 mx-auto mb-2 text-[var(--re-brand)]" />
                        <div className="text-lg font-bold">{isFail ? 'P0 SITUATION' : 'READY'}</div>
                        <div className="text-[10px] uppercase text-[var(--re-text-muted)]">Audit Readiness</div>
                    </div>
                </div>

                {isFail && (
                    <div className="p-4 rounded-xl border border-[var(--re-danger)]/20 bg-[var(--re-danger-muted)] flex items-start gap-4">
                        <AlertCircle className="h-6 w-6 text-[var(--re-danger)] shrink-0" />
                        <div>
                            <h4 className="font-bold text-[var(--re-danger)]">Critical Failure Point</h4>
                            <p className="text-xs leading-relaxed text-[var(--re-text-primary)]">
                                FDA 21 CFR §1.1455 requires an electronic sortable spreadsheet within 24 hours of request.
                                Your manual processes are causing a "bottleneck" that puts your entire operation at risk.
                            </p>
                        </div>
                    </div>
                )}

                <div className="p-6 rounded-2xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex flex-col items-center text-center">
                    <h4 className="font-bold mb-2">Cut your response time to 1 minute</h4>
                    <p className="text-xs text-[var(--re-text-secondary)] mb-6 max-w-sm">
                        RegEngine users respond to FDA requests in seconds, not days. Prevent administrative chaos and inventory loss.
                    </p>
                    <div className="flex gap-4 w-full justify-center">
                        <Button className="bg-[var(--re-brand)] px-8 h-10">
                            Get Demo <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <FSMAToolShell
                config={DRILL_TOOL_CONFIG}
                renderResults={calculateResult}
                onLeadCapture={(lead) => {
                    if (lead.email) {
                        posthog?.capture('drill_simulated', {
                            email: lead.email,
                            answers: lead.answers
                        });
                        posthog?.identify(lead.email, { email: lead.email });
                    }
                }}
            />

            <div className="max-w-3xl mx-auto">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['recall-readiness', 'kde-checker', 'roi-calculator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
