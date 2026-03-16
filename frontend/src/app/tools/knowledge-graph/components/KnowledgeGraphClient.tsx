'use client';

import React from "react";
import dynamic from "next/dynamic";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { KnowledgeGraphErrorBoundary } from "./KnowledgeGraphErrorBoundary";
import { LeadGate } from "@/components/lead-gate/LeadGate";

const SupplyChainKnowledgeGraphBuilder = dynamic(
    () => import("./KnowledgeGraph").then(mod => mod.SupplyChainKnowledgeGraphBuilder),
    { ssr: false }
);

export function KnowledgeGraphClient() {
    return (
        <FreeToolPageShell
            title="Supply Chain Knowledge Graph"
            subtitle="Map and trace your FSMA 204 supply chain with our interactive visual builder."
            relatedToolIds={['fsma-unified', 'ftl-checker', 'cte-mapper']}
        >
            <LeadGate
                source="knowledge-graph"
                headline="Unlock the Interactive Knowledge Graph Builder"
                subheadline="Visually map your supply chain nodes, trace product flows, and identify FSMA 204 coverage gaps."
                ctaText="Open Graph Builder"
                teaser={
                    <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 text-center">
                        <div className="text-4xl mb-3">🔗</div>
                        <p className="text-lg font-semibold text-[var(--re-text-primary)]">Interactive Supply Chain Graph</p>
                        <p className="text-sm text-[var(--re-text-muted)] mt-2">Add facilities, suppliers, and distribution centers. Drag to connect. See your FSMA 204 traceability network come to life.</p>
                    </div>
                }
            >
                <KnowledgeGraphErrorBoundary>
                    <SupplyChainKnowledgeGraphBuilder />
                </KnowledgeGraphErrorBoundary>
            </LeadGate>
        </FreeToolPageShell>
    );
}
