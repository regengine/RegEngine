'use client';

import React from "react";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { FSMA204Assessment } from "@/components/fsma/readiness-assessment";
import { LeadGate } from "@/components/lead-gate/LeadGate";

export function SelfReportedChecklistClient() {
    return (
        <FreeToolPageShell
            title="Self Reported Checklist"
            heading="Self Reported Checklist"
            subtitle="You answer. It echoes what you reported. Topics include Critical Tracking Event (CTE) and Key Data Element (KDE) fields. We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455. The federal Food Traceability Rule compliance date is July 20, 2028."
            relatedToolIds={['ftl-checker', 'kde-checker', 'cte-mapper']}
        >
            <LeadGate
                source="self-reported-checklist"
                headline="Self Reported Checklist"
                subheadline="Answer questions about product list overlap, CTE fields, KDE fields, and export file capability. Output is a summary of what you reported. Not a readiness score, not a certified gap analysis, not a regulatory determination."
                ctaText="Begin Checklist"
                teaser={
                    <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 text-center">
                        <div className="text-4xl mb-3">📋</div>
                        <p className="text-lg font-semibold text-[var(--re-text-primary)]">Self Reported Checklist</p>
                        <p className="text-sm text-[var(--re-text-muted)] mt-2">
                            You answer. It echoes what you reported. Sections: Product list overlap; Critical Tracking Event (CTE) fields; Key Data Element (KDE) fields; Export file.
                            We do NOT ask "within 24 hours" and we do NOT claim you can meet §1.1455.
                        </p>
                        <p className="text-xs text-[var(--re-text-muted)] mt-4">
                            The federal Food Traceability Rule compliance date is July 20, 2028.
                        </p>
                    </div>
                }
            >
                <FSMA204Assessment />
            </LeadGate>
        </FreeToolPageShell>
    );
}
