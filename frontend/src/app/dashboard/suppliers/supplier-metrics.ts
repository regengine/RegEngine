import type { ComplianceState } from '@/components/ui/status-badge';
import type {
    SupplierComplianceGap,
    SupplierComplianceGapsResponse,
    SupplierComplianceScore,
} from '@/types/api';

/* ------------------------------------------------------------------ */
/*  Counts                                                             */
/* ------------------------------------------------------------------ */

/** A finite count, or null when the value is missing / not a number. */
export function countOrNull(value: unknown): number | null {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Sum per-facility counts. Missing counts are treated as 0, but if no
 * facility has a count yet the result is null so the UI can say
 * "No data yet" instead of a misleading 0 (or NaN).
 */
export function sumKnownCounts(counts: Array<number | null | undefined>): number | null {
    let total: number | null = null;
    for (const count of counts) {
        const n = countOrNull(count);
        if (n === null) continue;
        total = (total ?? 0) + n;
    }
    return total;
}

/* ------------------------------------------------------------------ */
/*  Compliance status + gaps (one computation)                         */
/* ------------------------------------------------------------------ */

export interface FacilityCompliance {
    state: ComplianceState;
    label: string;
    /** Backend score, only when it reflects evaluated requirements. */
    score: number | null;
    gaps: SupplierComplianceGap[];
    gapCount: number;
}

export const NO_COMPLIANCE_DATA: FacilityCompliance = {
    state: 'unknown',
    label: 'No data yet',
    score: null,
    gaps: [],
    gapCount: 0,
};

/**
 * Derive the facility status and its gap list from the same inputs so the
 * badge and the gap count can never disagree.
 *
 * The backend returns score 0 for a facility with no FTL categories scoped
 * (nothing was evaluated) alongside a single `ftl_not_scoped` gap. Reading
 * that 0 as a score produced "Non-Compliant (0)" next to "1 gap".
 */
export function deriveFacilityCompliance(
    score: SupplierComplianceScore | null,
    gapsResponse: SupplierComplianceGapsResponse | null,
): FacilityCompliance {
    // Without the gap list we cannot say which requirements are met.
    if (!gapsResponse) return NO_COMPLIANCE_DATA;

    const gaps = Array.isArray(gapsResponse.gaps) ? gapsResponse.gaps : [];
    const gapCount = gaps.length;
    const notScoped =
        gaps.some((gap) => gap.reason === 'ftl_not_scoped') || score?.required_ctes === 0;
    const scoreValue = notScoped ? null : countOrNull(score?.score);

    if (notScoped) {
        return { state: 'unknown', label: 'Not scoped', score: null, gaps, gapCount };
    }
    if (gaps.some((gap) => gap.severity === 'high')) {
        return { state: 'non-compliant', label: 'Non-Compliant', score: scoreValue, gaps, gapCount };
    }
    if (gapCount > 0) {
        return { state: 'at-risk', label: 'Partial', score: scoreValue, gaps, gapCount };
    }
    if (scoreValue === null) return NO_COMPLIANCE_DATA;
    return { state: 'compliant', label: 'Compliant', score: scoreValue, gaps, gapCount };
}

/* ------------------------------------------------------------------ */
/*  Gap -> requirement link                                            */
/* ------------------------------------------------------------------ */

const SUBPART_S_URL = 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S';
const FTL_URL = 'https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list';

/** CTE type (backend spelling + aliases) -> 21 CFR Part 1 Subpart S section. */
const CTE_SECTIONS: Record<string, string> = {
    harvesting: '1.1325',
    cooling: '1.1325',
    initial_packing: '1.1330',
    first_receiver: '1.1335',
    first_land_based_receiving: '1.1335',
    shipping: '1.1340',
    receiving: '1.1345',
    transforming: '1.1350',
    transformation: '1.1350',
};

export interface GapRequirement {
    label: string;
    href: string;
}

export function gapRequirement(gap: SupplierComplianceGap): GapRequirement {
    if (gap.reason === 'ftl_not_scoped') {
        return { label: 'FDA Food Traceability List', href: FTL_URL };
    }
    const section = gap.cte_type ? CTE_SECTIONS[gap.cte_type.trim().toLowerCase()] : undefined;
    if (section) {
        return { label: `21 CFR §${section}`, href: `${SUBPART_S_URL}/section-${section}` };
    }
    return { label: '21 CFR Part 1 Subpart S', href: SUBPART_S_URL };
}
