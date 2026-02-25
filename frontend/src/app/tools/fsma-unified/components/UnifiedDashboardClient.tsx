'use client';

import React from "react";
import { motion } from "framer-motion";
import { AnomalyDetectionSimulator } from "./AnomalySimulator";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";

export function UnifiedDashboardClient() {
    return (
        <FreeToolPageShell
            title="AI-Powered Cold Chain Monitor"
            subtitle="Detect temperature excursions and supply chain anomalies before they become recalls."
            relatedToolIds={['knowledge-graph', 'ftl-checker', 'roi-calculator', 'recall-readiness']}
        >
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
            >
                <AnomalyDetectionSimulator />
            </motion.div>
        </FreeToolPageShell>
    );
}
