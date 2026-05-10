'use client';

import React from "react";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { FSMA204Assessment } from "@/components/fsma/readiness-assessment";
import { LeadGate } from "@/components/lead-gate/LeadGate";

export function ReadinessAssessmentClient() {
    return (
        <FreeToolPageShell
            title="FSMA 204 Readiness Self-Check"
            subtitle="Self-check your readiness across product coverage, CTEs, KDEs, and system capabilities. Educational; not an FDA audit, certification, or compliance determination."
            relatedToolIds={['ftl-checker', 'kde-checker', 'cte-mapper', 'drill-simulator']}
        >
            <LeadGate
                source="readiness-assessment"
                headline="Start Your FSMA 204 Readiness Self-Check"
                subheadline="Answer a few questions about your products, CTEs, KDEs, and systems to get a self-reported readiness summary. Reflects what you reported, not verified records."
                ctaText="Begin Self-Check"
                teaser={
                    <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 text-center">
                        <div className="text-4xl mb-3">📊</div>
                        <p className="text-lg font-semibold text-[var(--re-text-primary)]">6-Step Readiness Self-Check</p>
                        <p className="text-sm text-[var(--re-text-muted)] mt-2">Covers FTL products, supply chain role, CTEs, KDEs, and system capabilities. Surfaces a self-reported readiness summary based on your answers — not a regulatory determination.</p>
                    </div>
                }
            >
                <FSMA204Assessment />
            </LeadGate>
        </FreeToolPageShell>
    );
}
