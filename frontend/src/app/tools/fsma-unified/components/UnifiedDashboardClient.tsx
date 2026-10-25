'use client';

import React from "react";
import Link from "next/link";
import { Thermometer } from "lucide-react";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";

export function UnifiedDashboardClient() {
    return (
        <FreeToolPageShell
            title="Cold Chain Anomaly Detection"
            subtitle="Review cold-chain temperature and lot-flow records in one place."
            relatedToolIds={['knowledge-graph', 'ftl-checker', 'roi-calculator', 'recall-readiness']}
        >
            <EmptyState
                icon={Thermometer}
                title="No cold-chain data yet"
                titleAs="h2"
                description="No temperature or lot-flow records are loaded for this view yet."
                action={
                    <Button variant="secondary" size="sm" asChild>
                        <Link href="/tools/data-import" className="no-underline">
                            Open the Data Import Hub
                        </Link>
                    </Button>
                }
            />
        </FreeToolPageShell>
    );
}
