'use client';

import React from "react";
import { FreeToolPageShell } from "@/components/layout/FreeToolPageShell";
import { FSMA204Assessment } from "@/components/fsma/readiness-assessment";

export function ReadinessAssessmentClient() {
    return (
        <FreeToolPageShell
            title="FSMA 204 Readiness Assessment"
            subtitle="Score your compliance readiness across product coverage, CTEs, KDEs, and system capabilities."
            relatedToolIds={['ftl-checker', 'kde-checker', 'cte-mapper', 'drill-simulator']}
        >
            <FSMA204Assessment />
        </FreeToolPageShell>
    );
}
