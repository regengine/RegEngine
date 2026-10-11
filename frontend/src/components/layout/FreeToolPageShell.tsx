'use client';

import React from 'react';
import { Zap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';
import { filterExperimentalToolLinks } from '@/lib/experimental-features';

interface FreeToolPageShellProps {
    /** Tool name shown in the breadcrumb (e.g. "Supply Chain Knowledge Graph") */
    title: string;
    /** H1 text. When omitted, the H1 is "RegEngine • {title}". */
    heading?: string;
    /** Short description below the title */
    subtitle: string;
    /** IDs from FREE_TOOLS to show in the Related Tools section */
    relatedToolIds: string[];
    /** The tool's interactive content */
    children: React.ReactNode;
}

/**
 * Shell for every free tool page — SPEC §6 "Free tool" template.
 *
 * The grey hero band and the separately boxed title block collapse into one
 * `PageHeader`: breadcrumb, H1, lede, and the "Free Tool — No Login Required"
 * badge in the meta slot. The header is never boxed and carries no shadow; the
 * hairline under it is the only rule.
 *
 * Prop API and every string are unchanged — "RegEngine • {title}",
 * "Free Tool — No Login Required", "Educational Tool" and the disclaimer are
 * all asserted copy.
 */
export function FreeToolPageShell({
    title,
    heading,
    subtitle,
    relatedToolIds,
    children,
}: FreeToolPageShellProps) {
    const relatedTools = filterExperimentalToolLinks(
        FREE_TOOLS.filter((t) => relatedToolIds.includes(t.id))
    );

    return (
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            <Container width="tool">
                <PageHeader
                    breadcrumbs={
                        <Breadcrumbs
                            className="mb-0"
                            items={[
                                { label: 'Free Tools', href: '/tools' },
                                { label: title },
                            ]}
                        />
                    }
                    title={heading ?? `RegEngine • ${title}`}
                    description={subtitle}
                    meta={
                        <Badge tone="brand" className="whitespace-nowrap">
                            <Zap aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={1.75} />
                            Free Tool — No Login Required
                        </Badge>
                    }
                />

                <div className="space-y-6">{children}</div>

                <Callout
                    tone="neutral"
                    role="note"
                    title="Educational Tool"
                    className="mt-8"
                    action={<Badge tone="neutral">Free Tool</Badge>}
                >
                    Free self-check tool. Not a compliance certification or regulatory determination.
                </Callout>

                {relatedTools.length > 0 && <RelatedTools tools={relatedTools} />}
            </Container>
        </div>
    );
}
