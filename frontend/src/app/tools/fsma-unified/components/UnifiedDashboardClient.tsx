'use client';

import React from "react";
import { motion } from "framer-motion";
import { AnomalyDetectionSimulator } from "./AnomalySimulator";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { LeadGate } from "@/components/lead-gate/LeadGate";

export function UnifiedDashboardClient() {
    return (
        <FreeToolPageShell
            title="AI-Powered Cold Chain Monitor"
            subtitle="Detect temperature excursions and supply chain anomalies before they become recalls."
            relatedToolIds={['knowledge-graph', 'ftl-checker', 'roi-calculator', 'recall-readiness']}
        >
            <LeadGate
                source="fsma-unified"
                headline="Unlock the Anomaly Detection Simulator"
                subheadline="Run multi-algorithm detection on 90 days of cold-chain data with precision/recall tuning and supplier risk scoring."
                ctaText="Launch Simulator"
                teaser={
                    <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 text-center">
                        <div className="text-4xl mb-3">🌡️</div>
                        <p className="text-lg font-semibold text-[var(--re-text-primary)]">Cold Chain Anomaly Detection</p>
                        <p className="text-sm text-[var(--re-text-muted)] mt-2">Ensemble, statistical, rule-based, and pattern-drift algorithms with a full evaluation harness, lot scatter, and supplier risk matrix.</p>
                    </div>
                }
            >
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    <AnomalyDetectionSimulator />
                </motion.div>
            </LeadGate>
        </FreeToolPageShell>
    );
}
