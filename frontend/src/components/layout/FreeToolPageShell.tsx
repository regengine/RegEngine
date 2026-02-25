'use client';

import React from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';
import { Zap } from 'lucide-react';

interface FreeToolPageShellProps {
    /** Tool name shown in breadcrumb and title (e.g. "Supply Chain Knowledge Graph") */
    title: string;
    /** Short description below the title */
    subtitle: string;
    /** IDs from FREE_TOOLS to show in the Related Tools section */
    relatedToolIds: string[];
    /** The tool's interactive content */
    children: React.ReactNode;
}

export function FreeToolPageShell({
    title,
    subtitle,
    relatedToolIds,
    children,
}: FreeToolPageShellProps) {
    const relatedTools = FREE_TOOLS.filter((t) =>
        relatedToolIds.includes(t.id)
    );

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                {/* Breadcrumb */}
                <Breadcrumbs
                    items={[
                        { label: 'Free Tools', href: '/tools' },
                        { label: title },
                    ]}
                />

                {/* Title Block */}
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <div className="text-3xl font-semibold tracking-tight">
                            RegEngine • {title}
                        </div>
                        <div className="mt-1 text-sm text-muted-foreground">
                            {subtitle}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge className="bg-[var(--re-brand)] rounded-xl py-1 px-3">
                            <Zap className="mr-2 h-4 w-4 inline" />
                            Free Tool — No Login Required
                        </Badge>
                    </div>
                </div>

                {/* Tool Content */}
                <div className="mt-6">{children}</div>

                {/* Compliance Note */}
                <div className="rounded-3xl border p-4 md:p-6 mt-8">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                            <div className="text-sm font-medium">
                                Compliance Note
                            </div>
                            <div className="text-sm text-muted-foreground">
                                Free compliance tools powered by RegEngine&apos;s
                                high-integrity data engine. Built on the same
                                technology used for production FSMA 204
                                traceability.
                            </div>
                        </div>
                        <Badge variant="secondary" className="rounded-xl">
                            Free Tool
                        </Badge>
                    </div>
                </div>

                {/* Related Tools */}
                {relatedTools.length > 0 && (
                    <RelatedTools tools={relatedTools} />
                )}
            </div>
        </div>
    );
}
