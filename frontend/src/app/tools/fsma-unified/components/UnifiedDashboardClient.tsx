'use client';

import React from "react";
import { Thermometer } from "lucide-react";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { EmptyState } from "@/components/ui/empty-state";

export function UnifiedDashboardClient() {
    return (
        <FreeToolPageShell
            title="Cold Chain Anomaly Detection"
            subtitle="Ensemble, statistical, rule-based, and pattern-drift detection over your own cold-chain temperature and lot-flow records."
            relatedToolIds={['knowledge-graph', 'ftl-checker', 'roi-calculator', 'recall-readiness']}
        >
            <EmptyState
                icon={Thermometer}
                title="No cold-chain data connected"
                titleAs="h2"
                description="Connect or upload your temperature stream and lot-flow records to run anomaly detection here. Charts, flagged lots, and supplier risk scoring appear once your data is loaded."
            />
        </FreeToolPageShell>
    );
}
