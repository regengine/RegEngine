/**
 * Finance Dashboard API Integration
 * 
 * Dashboard-specific queries for SEC/SOX compliance monitoring.
 * Mock data implementation - ready for backend Finance service integration.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent, Alert } from '@/components/verticals';

// ============================================================================
// Dashboard Metrics Aggregation
// ============================================================================

/**
 * Fetch aggregated dashboard metrics for Finance compliance.
 */
export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['finance', 'dashboard', 'metrics'],
        queryFn: async () => {
            const metrics: MetricConfig[] = [
                {
                    label: 'Active Entities',
                    value: '12',
                    icon: 'Building2' as any,
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    trend: { value: 2, isPositive: true },
                    helpText: 'Registered SEC reporting entities',
                },
                {
                    label: 'Filed Documents',
                    value: '847',
                    icon: 'FileText' as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    trend: { value: 12, isPositive: true },
                    helpText: 'SEC filings (10-K, 10-Q, 8-K)',
                },
                {
                    label: 'SOX Controls',
                    value: '156',
                    icon: 'Shield' as any,
                    iconColor: 'text-purple-600',
                    iconBgColor: 'bg-purple-100',
                    helpText: 'Active SOX 404 controls',
                },
                {
                    label: 'Control Deficiencies',
                    value: '3',
                    icon: 'AlertTriangle' as any,
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    helpText: 'Material weaknesses identified',
                },
            ];

            return metrics;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// SEC Filing Status
// ============================================================================

interface SECFiling {
    id: string;
    filingType: '10-K' | '10-Q' | '8-K' | 'DEF 14A';
    entity: string;
    periodEnding: string;
    status: 'filed' | 'pending' | 'verified' | 'deficient';
    filedDate: string;
    accessionNumber?: string;
}

/**
 * Fetch recent SEC filing status.
 */
export const useSECFilings = (limit: number = 5): UseQueryResult<SECFiling[]> => {
    return useQuery({
        queryKey: ['finance', 'sec-filings', limit],
        queryFn: async () => {
            const filings: SECFiling[] = [
                {
                    id: 'filing_001',
                    filingType: '10-K',
                    entity: 'ABC Corporation',
                    periodEnding: 'FY 2024',
                    status: 'verified',
                    filedDate: new Date(Date.now() - 86400000 * 30).toISOString(),
                    accessionNumber: '0001234567-24-000123',
                },
                {
                    id: 'filing_002',
                    filingType: '10-Q',
                    entity: 'DEF Industries',
                    periodEnding: 'Q4 2024',
                    status: 'filed',
                    filedDate: new Date(Date.now() - 86400000 * 15).toISOString(),
                    accessionNumber: '0001234568-24-000456',
                },
                {
                    id: 'filing_003',
                    filingType: '8-K',
                    entity: 'GHI Enterprises',
                    periodEnding: 'Current Event',
                    status: 'verified',
                    filedDate: new Date(Date.now() - 86400000 * 5).toISOString(),
                    accessionNumber: '0001234569-24-000789',
                },
                {
                    id: 'filing_004',
                    filingType: '10-Q',
                    entity: 'JKL Holdings',
                    periodEnding: 'Q3 2024',
                    status: 'pending',
                    filedDate: new Date(Date.now() - 86400000 * 2).toISOString(),
                },
            ];

            return filings.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// SOX 404 Control Health
// ============================================================================

interface SOXControl {
    id: string;
    controlId: string;
    category: 'ITGC' | 'Financial Close' | 'Revenue' | 'Payroll' | 'Access Controls';
    description: string;
    effectiveness: 'effective' | 'deficient' | 'material_weakness';
    lastTested: string;
    owner: string;
}

/**
 * Fetch SOX 404 internal control health status.
 */
export const useSOXControls = (): UseQueryResult<SOXControl[]> => {
    return useQuery({
        queryKey: ['finance', 'sox-controls'],
        queryFn: async () => {
            const controls: SOXControl[] = [
                {
                    id: 'sox_001',
                    controlId: 'ITGC-001',
                    category: 'ITGC',
                    description: 'User access provisioning and deprovisioning',
                    effectiveness: 'effective',
                    lastTested: '14 days ago',
                    owner: 'IT Security',
                },
                {
                    id: 'sox_002',
                    controlId: 'FC-025',
                    category: 'Financial Close',
                    description: 'Monthly account reconciliation review',
                    effectiveness: 'effective',
                    lastTested: '7 days ago',
                    owner: 'Accounting',
                },
                {
                    id: 'sox_003',
                    controlId: 'REV-012',
                    category: 'Revenue',
                    description: 'Revenue recognition completeness check',
                    effectiveness: 'deficient',
                    lastTested: '21 days ago',
                    owner: 'Revenue Operations',
                },
                {
                    id: 'sox_004',
                    controlId: 'AC-008',
                    category: 'Access Controls',
                    description: 'Segregation of duties matrix validation',
                    effectiveness: 'effective',
                    lastTested: '10 days ago',
                    owner: 'Internal Audit',
                },
            ];

            return controls;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Regulation Change Feed
// ============================================================================

interface RegulationChange {
    id: string;
    source: 'SEC' | 'FASB' | 'PCAOB' | 'FINRA';
    title: string;
    description: string;
    effectiveDate: string;
    impact: 'high' | 'medium' | 'low';
    publishedDate: string;
}

/**
 * Fetch recent regulatory changes and updates.
 */
export const useRegulationChanges = (limit: number = 5): UseQueryResult<RegulationChange[]> => {
    return useQuery({
        queryKey: ['finance', 'regulation-changes', limit],
        queryFn: async () => {
            const changes: RegulationChange[] = [
                {
                    id: 'reg_001',
                    source: 'SEC',
                    title: 'Cybersecurity Disclosure Requirements',
                    description: 'New Form 8-K Item 1.05 requires disclosure of material cybersecurity incidents within 4 business days',
                    effectiveDate: '2024-12-18',
                    impact: 'high',
                    publishedDate: new Date(Date.now() - 86400000 * 45).toISOString(),
                },
                {
                    id: 'reg_002',
                    source: 'FASB',
                    title: 'ASC 326 - Current Expected Credit Losses',
                    description: 'Updated guidance on credit loss methodology for financial instruments',
                    effectiveDate: '2024-01-01',
                    impact: 'medium',
                    publishedDate: new Date(Date.now() - 86400000 * 90).toISOString(),
                },
                {
                    id: 'reg_003',
                    source: 'SEC',
                    title: 'Climate-Related Disclosures',
                    description: 'Enhanced disclosure requirements for climate-related risks in annual reports',
                    effectiveDate: '2025-01-01',
                    impact: 'high',
                    publishedDate: new Date(Date.now() - 86400000 * 30).toISOString(),
                },
            ];

            return changes.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Audit Trail Activity
// ============================================================================

/**
 * Fetch recent audit trail and compliance events.
 */
export const useAuditTrail = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['finance', 'audit-trail', limit],
        queryFn: async () => {
            const events: TimelineEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    title: '10-K filing verified',
                    description: 'Annual report for FY 2024 passed all compliance checks',
                    type: 'success',
                    userName: 'CFO Office',
                    metadata: { entity: 'ABC Corp', accession: '0001234567-24-000123' },
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    title: 'SOX control deficiency identified',
                    description: 'Revenue recognition control REV-012 marked as deficient',
                    type: 'warning',
                    userName: 'Internal Audit',
                    metadata: { control: 'REV-012', severity: 'Deficient' },
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 10800000).toISOString(),
                    title: '8-K filed with SEC',
                    description: 'Material event disclosure submitted via EDGAR',
                    type: 'success',
                    userName: 'Corporate Secretary',
                    metadata: { entity: 'GHI Enterprises' },
                },
                {
                    id: '4',
                    timestamp: new Date(Date.now() - 14400000).toISOString(),
                    title: 'New SEC rule published',
                    description: 'Cybersecurity disclosure requirements updated',
                    type: 'info',
                    userName: 'Compliance Monitor',
                    metadata: { source: 'SEC', impact: 'High' },
                },
            ];

            return events.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Risk Assessment
// ============================================================================

interface RiskArea {
    category: string;
    riskLevel: 'low' | 'medium' | 'high' | 'critical';
    controlCount: number;
    deficiencyCount: number;
}

/**
 * Fetch risk heat map data across control categories.
 */
export const useRiskHeatMap = (): UseQueryResult<RiskArea[]> => {
    return useQuery({
        queryKey: ['finance', 'risk-heatmap'],
        queryFn: async () => {
            const risks: RiskArea[] = [
                {
                    category: 'Financial Reporting',
                    riskLevel: 'low',
                    controlCount: 45,
                    deficiencyCount: 0,
                },
                {
                    category: 'IT General Controls',
                    riskLevel: 'low',
                    controlCount: 38,
                    deficiencyCount: 0,
                },
                {
                    category: 'Revenue Recognition',
                    riskLevel: 'medium',
                    controlCount: 22,
                    deficiencyCount: 1,
                },
                {
                    category: 'Access Controls',
                    riskLevel: 'low',
                    controlCount: 31,
                    deficiencyCount: 0,
                },
                {
                    category: 'Payroll & Benefits',
                    riskLevel: 'low',
                    controlCount: 20,
                    deficiencyCount: 0,
                },
            ];

            return risks;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// System Health Monitor
// ============================================================================

/**
 * Fetch overall Finance compliance system health.
 */
export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['finance', 'health'],
        queryFn: async () => {
            const health: SystemHealth = {
                status: 'HEALTHY',
                message: 'All compliance systems operational',
                lastCheck: '2 min ago',
                uptime: '99.95%',
            };

            return health;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Compliance Score Trend
// ============================================================================

interface ComplianceScoreTrend {
    period: string;
    score: number;
    filingCount: number;
}

/**
 * Fetch historical compliance score trends.
 */
export const useComplianceTrend = (): UseQueryResult<ComplianceScoreTrend[]> => {
    return useQuery({
        queryKey: ['finance', 'compliance-trend'],
        queryFn: async () => {
            const trend: ComplianceScoreTrend[] = [
                { period: 'Q1 2024', score: 92, filingCount: 48 },
                { period: 'Q2 2024', score: 94, filingCount: 52 },
                { period: 'Q3 2024', score: 96, filingCount: 47 },
                { period: 'Q4 2024', score: 98, filingCount: 51 },
            ];

            return trend;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
