import { describe, expect, it } from 'vitest';
import {
    NO_COMPLIANCE_DATA,
    countOrNull,
    deriveFacilityCompliance,
    gapRequirement,
    sumKnownCounts,
} from './supplier-metrics';
import type {
    SupplierComplianceGap,
    SupplierComplianceGapsResponse,
    SupplierComplianceScore,
} from '@/types/api';

function score(overrides: Partial<SupplierComplianceScore> = {}): SupplierComplianceScore {
    return {
        score: 92,
        coverage_ratio: 1,
        freshness_ratio: 1,
        integrity_ratio: 0.2,
        required_ctes: 2,
        covered_ctes: 2,
        stale_ctes: 0,
        missing_ctes: 0,
        total_events: 4,
        evaluated_at: '2026-10-22T00:00:00Z',
        ...overrides,
    };
}

function gap(overrides: Partial<SupplierComplianceGap> = {}): SupplierComplianceGap {
    return {
        facility_id: 'f1',
        facility_name: 'test',
        cte_type: 'shipping',
        severity: 'high',
        issue: 'Missing required shipping event',
        reason: 'required_cte_missing',
        last_seen: null,
        ...overrides,
    };
}

function gapsResponse(gaps: SupplierComplianceGap[], total = gaps.length): SupplierComplianceGapsResponse {
    return { gaps, total, high: 0, medium: 0, low: 0, evaluated_at: '2026-10-22T00:00:00Z' };
}

describe('missing counts', () => {
    it('treats undefined, null and NaN as missing', () => {
        expect(countOrNull(undefined)).toBeNull();
        expect(countOrNull(null)).toBeNull();
        expect(countOrNull(Number.NaN)).toBeNull();
        expect(countOrNull('3')).toBeNull();
        expect(countOrNull(0)).toBe(0);
    });

    it('returns null (No data yet) when no facility has a count', () => {
        expect(sumKnownCounts([])).toBeNull();
        expect(sumKnownCounts([null, undefined])).toBeNull();
    });

    it('defaults missing per-facility counts to 0 instead of producing NaN', () => {
        const total = sumKnownCounts([3, undefined, null, Number.NaN, 2]);
        expect(total).toBe(5);
        expect(Number.isNaN(total)).toBe(false);
    });

    it('keeps a real zero as 0', () => {
        expect(sumKnownCounts([0, null])).toBe(0);
    });
});

describe('deriveFacilityCompliance', () => {
    it('reports no data when the gaps call failed, even with a score', () => {
        expect(deriveFacilityCompliance(score(), null)).toEqual(NO_COMPLIANCE_DATA);
        expect(deriveFacilityCompliance(null, null)).toEqual(NO_COMPLIANCE_DATA);
    });

    it('does not show "Non-Compliant (0)" for an unscoped facility with 1 gap', () => {
        const result = deriveFacilityCompliance(
            score({ score: 0, required_ctes: 0, covered_ctes: 0, coverage_ratio: 0 }),
            gapsResponse([gap({ cte_type: null, reason: 'ftl_not_scoped', issue: 'No FTL categories scoped for this facility' })]),
        );
        expect(result.state).toBe('unknown');
        expect(result.label).toBe('Not scoped');
        expect(result.score).toBeNull();
        expect(result.gapCount).toBe(1);
    });

    it('takes the gap count from the rendered gap list, not the separate total field', () => {
        const result = deriveFacilityCompliance(score({ score: 56 }), gapsResponse([gap()], 0));
        expect(result.gapCount).toBe(1);
        expect(result.gaps).toHaveLength(result.gapCount);
    });

    it('never reports Compliant while gaps exist', () => {
        const result = deriveFacilityCompliance(
            score({ score: 95 }),
            gapsResponse([gap({ severity: 'medium', reason: 'required_cte_stale', issue: 'shipping event is older than 30 days' })]),
        );
        expect(result.state).toBe('at-risk');
        expect(result.gapCount).toBe(1);
    });

    it('marks high-severity gaps Non-Compliant with a non-zero gap count', () => {
        const result = deriveFacilityCompliance(score({ score: 56 }), gapsResponse([gap()]));
        expect(result.state).toBe('non-compliant');
        expect(result.gapCount).toBeGreaterThan(0);
        expect(result.score).toBe(56);
    });

    it('marks Compliant only with zero gaps and a real score', () => {
        const result = deriveFacilityCompliance(score({ score: 92 }), gapsResponse([]));
        expect(result).toMatchObject({ state: 'compliant', gapCount: 0, score: 92 });
        expect(deriveFacilityCompliance(null, gapsResponse([]))).toEqual(NO_COMPLIANCE_DATA);
    });

    it('status and gap count agree across every combination', () => {
        const cases: Array<[SupplierComplianceScore | null, SupplierComplianceGapsResponse | null]> = [
            [null, null],
            [score(), gapsResponse([])],
            [score({ score: 0 }), gapsResponse([gap()])],
            [score({ score: 100 }), gapsResponse([gap({ severity: 'medium' })])],
            [score({ required_ctes: 0, score: 0 }), gapsResponse([gap({ reason: 'ftl_not_scoped', cte_type: null })])],
        ];
        for (const [s, g] of cases) {
            const result = deriveFacilityCompliance(s, g);
            expect(result.gaps).toHaveLength(result.gapCount);
            if (result.state === 'compliant') expect(result.gapCount).toBe(0);
            if (result.state === 'non-compliant' || result.state === 'at-risk') {
                expect(result.gapCount).toBeGreaterThan(0);
            }
        }
    });
});

describe('gapRequirement', () => {
    it('links missing CTEs to their 21 CFR Subpart S section', () => {
        expect(gapRequirement(gap({ cte_type: 'shipping' }))).toEqual({
            label: '21 CFR §1.1340',
            href: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1340',
        });
        expect(gapRequirement(gap({ cte_type: 'transforming' })).label).toBe('21 CFR §1.1350');
        expect(gapRequirement(gap({ cte_type: 'first_receiver' })).label).toBe('21 CFR §1.1335');
    });

    it('links unscoped facilities to the Food Traceability List', () => {
        expect(gapRequirement(gap({ reason: 'ftl_not_scoped', cte_type: null })).label).toBe('FDA Food Traceability List');
    });

    it('falls back to Subpart S for an unknown CTE', () => {
        expect(gapRequirement(gap({ cte_type: 'mystery' })).label).toBe('21 CFR Part 1 Subpart S');
    });
});
