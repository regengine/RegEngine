'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { usePostHog } from 'posthog-js/react';
import { FSMA_FTL_CATEGORIES, FSMA_CTES } from '@/lib/fsma-tools-data';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { ClipboardList, Download, Printer, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const KDE_CHECKER_CONFIG: ToolConfig = {
    id: 'kde-checker',
    title: 'KDE Completeness Checker',
    description: 'Tell us your product and your role in the supply chain, and we will generate your exact required KDE checklist.',
    icon: 'ClipboardList',
    stages: {
        questions: [
            {
                id: 'category',
                text: 'Which FTL food category do you handle?',
                type: 'select',
                options: FSMA_FTL_CATEGORIES.map(cat => ({ label: cat.name, value: cat.id }))
            },
            {
                id: 'ctes',
                text: 'Which events do you perform for this food? (Select all that apply)',
                type: 'multi-select',
                options: Object.entries(FSMA_CTES).map(([id, data]) => ({ label: data.name, value: id }))
            }
        ],
        leadGate: {
            title: 'Download Your Custom Checklist',
            description: 'We will generate a high-resolution PDF and an importable CSV template for your team.',
            cta: 'Download Checklist Pack'
        }
    }
};

export function KDECheckerClient() {
    const posthog = usePostHog();

    const renderResults = (answers: Record<string, any>) => {
        const { category, ctes } = answers;
        const categoryName = FSMA_FTL_CATEGORIES.find(c => c.id === category)?.name || 'Selected Category';
        const selectedCtes = ctes || [];

        return (
            <div className="space-y-8">
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <h3 className="text-2xl font-bold">Your KDE Checklist</h3>
                        <p className="text-[var(--re-text-tertiary)] mt-1">For {categoryName}</p>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" className="h-8 gap-2 text-xs">
                            <Printer className="h-3 w-3" /> Print
                        </Button>
                        <Button variant="outline" size="sm" className="h-8 gap-2 text-xs">
                            <Download className="h-3 w-3" /> CSV Template
                        </Button>
                    </div>
                </div>

                <div className="space-y-6">
                    {selectedCtes.map((cteId: string) => {
                        const cte = FSMA_CTES[cteId as keyof typeof FSMA_CTES];
                        if (!cte) return null;

                        return (
                            <Card key={cteId} className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] overflow-hidden">
                                <div className="bg-[var(--re-brand-muted)] px-4 py-2 border-b border-[var(--re-border-default)] flex items-center justify-between">
                                    <span className="text-xs font-bold uppercase tracking-wider text-[var(--re-brand)]">{cte.name}</span>
                                    <Badge variant="outline" className="bg-white/5 text-[10px]">REQUIRED</Badge>
                                </div>
                                <CardContent className="p-4 space-y-3">
                                    {cte.kdes.map((kde, idx) => (
                                        <div key={idx} className="flex items-start justify-between gap-3 group">
                                            <div className="flex items-start gap-3">
                                                <div className="mt-0.5 w-4 h-4 rounded border border-[var(--re-border-subtle)] flex items-center justify-center shrink-0 group-hover:border-[var(--re-brand)] transition-colors">
                                                    <div className="w-2 h-2 rounded-sm bg-[var(--re-brand)] opacity-0 group-hover:opacity-20" />
                                                </div>
                                                <span className="text-sm text-[var(--re-text-secondary)]">{kde.name}</span>
                                            </div>
                                            <Badge
                                                variant="outline"
                                                className={`text-[9px] px-1.5 h-4 shrink-0 border-none ${kde.provide
                                                    ? 'bg-[var(--re-brand-muted)] text-[var(--re-brand)]'
                                                    : 'bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)]'
                                                    }`}
                                            >
                                                {kde.provide ? 'MAINTAIN & PROVIDE' : 'MAINTAIN ONLY'}
                                            </Badge>
                                        </div>
                                    ))}
                                </CardContent>
                            </Card>
                        );
                    })}
                </div>

                <div className="p-6 rounded-2xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)] / 20 flex flex-col items-center text-center">
                    <h4 className="font-bold mb-2">Want to automate this capture?</h4>
                    <p className="text-xs text-[var(--re-text-secondary)] mb-4 max-w-md">
                        RegEngine automatically maps these KDEs based on your FTL list and provides one-click compliance validation.
                    </p>
                    <Button className="bg-[var(--re-brand)] gap-2">
                        Explore FSMA Automation <ArrowRight className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <FSMAToolShell
                config={KDE_CHECKER_CONFIG}
                renderResults={renderResults}
                onLeadCapture={(lead) => {
                    if (lead.email) {
                        posthog?.capture('kde_checked', {
                            email: lead.email,
                            answers: lead.answers
                        });
                        posthog?.identify(lead.email, { email: lead.email });
                    }
                }}
            />

            <div className="max-w-3xl mx-auto">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['tlc-validator', 'cte-mapper', 'drill-simulator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
