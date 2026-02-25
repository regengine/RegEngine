'use client';

import React from "react";
import dynamic from "next/dynamic";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { KnowledgeGraphErrorBoundary } from "./KnowledgeGraphErrorBoundary";

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
            <KnowledgeGraphErrorBoundary>
                <SupplyChainKnowledgeGraphBuilder />
            </KnowledgeGraphErrorBoundary>
        </FreeToolPageShell>
    );
}
