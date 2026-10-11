'use client';

import Link from 'next/link';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { usePostHog } from '@/lib/posthog-provider';
import { FSMA_FTL_CATEGORIES, FSMA_CTES } from '@/lib/fsma-tools-data';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Download, Printer, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const KDE_CHECKER_CONFIG: ToolConfig = {
    id: 'kde-checker',
    title: 'KDE Field Checklist',
    description: 'Tell us your product and your role in the supply chain and we\'ll draft a starting KDE checklist mapped to the relevant CTE under 21 CFR Part 1 Subpart S. Educational; review with your compliance team before relying on it.',
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
                text: 'Which events do you perform for this food? (Select all that apply. For seafood received from a fishing vessel, use First Land-Based Receiving — non-seafood importers should use Receiving instead.)',
                type: 'multi-select',
                options: Object.entries(FSMA_CTES).map(([id, data]) => ({ label: data.name, value: id }))
            }
        ],
        leadGate: {
            title: 'Download Your Draft Checklist',
            description: 'You can print or save your checklist as a PDF and download an importable CSV template for your team. This is a draft starting checklist — review against the rule and your operation\'s actual obligations before adoption.',
            cta: 'Download Draft Checklist'
        }
    }
};

export function KDECheckerClient() {
    const posthog = usePostHog();

    const renderResults = (answers: Record<string, any>) => {
        const { category, ctes } = answers;
        const categoryName = FSMA_FTL_CATEGORIES.find(c => c.id === category)?.name || 'Selected Category';
        const selectedCtes = ctes || [];

        const downloadCsvTemplate = () => {
            const rows: string[][] = [['CTE', 'KDE', 'Value', 'Notes']];
            selectedCtes.forEach((cteId: string) => {
                const cte = FSMA_CTES[cteId as keyof typeof FSMA_CTES];
                if (!cte) return;
                cte.kdes.forEach((kde) => rows.push([cte.name, kde.name, '', '']));
            });
            const csv = rows.map(row => row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(',')).join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'kde-checklist-template.csv';
            a.click();
            URL.revokeObjectURL(url);
        };

        return (
            <div className="space-y-8">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                        <h3 className="text-heading text-re-text-primary">Your Draft KDE Checklist</h3>
                        <p className="mt-1 text-ui text-re-text-secondary">For {categoryName} · Mapped to 21 CFR Part 1 Subpart S</p>
                        <p className="mt-2 max-w-[70ch] text-small text-re-text-tertiary">
                            Starting checklist — not a regulatory determination. Verify against the rule for your specific operation, surface any §1.1305 exemptions that apply, and review with counsel before relying on it.
                        </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                        <Button
                            variant="secondary"
                            size="sm"
                            leadingIcon={<Printer strokeWidth={1.75} aria-hidden="true" />}
                            onClick={() => window.print()}
                        >
                            Print
                        </Button>
                        <Button
                            variant="secondary"
                            size="sm"
                            leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
                            onClick={downloadCsvTemplate}
                        >
                            CSV Template
                        </Button>
                    </div>
                </div>

                <div className="space-y-6">
                    {selectedCtes.map((cteId: string) => {
                        const cte = FSMA_CTES[cteId as keyof typeof FSMA_CTES];
                        if (!cte) return null;

                        return (
                            <Card key={cteId} className="overflow-hidden">
                                <div className="flex items-center justify-between gap-3 border-b border-re-border-subtle bg-re-surface-inset px-4 py-2">
                                    <span className="font-mono uppercase text-label text-re-text-tertiary">{cte.name}</span>
                                    <Badge tone="neutral" size="sm" mono>{cte.cfr ?? 'Subpart S'}</Badge>
                                </div>
                                <CardContent className="space-y-3 p-4">
                                    {cte.kdes.map((kde, idx) => (
                                        <div key={idx} className="flex items-start gap-3">
                                            <span
                                                className="mt-0.5 h-4 w-4 shrink-0 rounded-sm border border-re-border-strong"
                                                aria-hidden="true"
                                            />
                                            <span className="text-ui text-re-text-secondary">{kde.name}</span>
                                        </div>
                                    ))}
                                </CardContent>
                            </Card>
                        );
                    })}
                </div>

                <Card variant="inset" padding="spacious" className="flex flex-col items-center text-center">
                    <h4 className="mb-2 text-subheading text-re-text-primary">Want help capturing these KDEs?</h4>
                    <p className="mb-4 max-w-[60ch] text-small text-re-text-secondary">
                        RegEngine helps teams ingest, validate, and structure KDEs by CTE so a §1.1455(c) sortable spreadsheet can be assembled when FDA asks. Compliance remains your operation&apos;s responsibility.
                    </p>
                    <Button asChild>
                        <Link href="/walkthrough">
                            Explore RegEngine <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        </Link>
                    </Button>
                </Card>
            </div>
        );
    };

    return (
        <div className="space-y-8">
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

            <div className="mx-auto max-w-3xl">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['tlc-validator', 'cte-mapper', 'drill-simulator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
