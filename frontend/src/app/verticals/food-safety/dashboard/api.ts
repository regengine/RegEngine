/**
 * Food Safety Dashboard API Integration
 *
 * Dashboard-specific queries that aggregate data from FSMA service endpoints.
 * Built on top of existing React Query infrastructure.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent, Alert } from '@/components/verticals';
import { AlertTriangle, Shield, Search, Database, Layers } from 'lucide-react';

// ============================================================================
// Dashboard Metrics Aggregation
// ============================================================================

/**
 * Fetch aggregated dashboard metrics.
 * Combines data from multiple endpoints to show high-level KPIs.
 */
export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'metrics'],
        queryFn: async () => {
            // Mock metrics for FSMA Dashboard
            const metrics: MetricConfig[] = [
                {
                    label: 'Active Recalls',
                    value: '0',
                    icon: AlertTriangle as any,
                    iconColor: 'text-red-600',
                    iconBgColor: 'bg-red-100',
                    helpText: 'Recalls requiring immediate action',
                },
                {
                    label: 'Traceability Gaps',
                    value: '12',
                    icon: Search as any,
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    trend: { value: 3, isPositive: false },
                    helpText: 'Lots with missing KDEs',
                },
                {
                    label: 'Mock Drill Sla',
                    value: '12m',
                    icon: Shield as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    helpText: 'Average time to 100% trace',
                },
                {
                    label: 'Data Completeness',
                    value: '98.5%',
                    icon: Database as any,
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    trend: { value: 0.5, isPositive: true },
                },
            ];

            return metrics;
        },
        staleTime: 30000,
    });
};

// ============================================================================
// High Risk Lots
// ============================================================================

interface HighRiskLot {
    tlc: string;
    product_description: string;
    risk_score: number;
    gap_count: number;
    last_event: string;
}

export const useHighRiskLots = (): UseQueryResult<HighRiskLot[]> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'risks'],
        queryFn: async () => {
            return [
                {
                    tlc: 'LOT-2024-001-A',
                    product_description: 'Organic Romaine Lettuce',
                    risk_score: 85,
                    gap_count: 2,
                    last_event: 'Harvest',
                },
                {
                    tlc: 'LOT-2024-003-C',
                    product_description: 'Baby Spinach',
                    risk_score: 60,
                    gap_count: 1,
                    last_event: 'Cooling',
                },
                {
                    tlc: 'LOT-2024-012-F',
                    product_description: 'Fresh Basil',
                    risk_score: 45,
                    gap_count: 0,
                    last_event: 'Packing',
                },
            ];
        },
    });
};

// ============================================================================
// Activity Timeline
// ============================================================================

export const useActivityTimeline = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'timeline', limit],
        queryFn: async () => {
            const events: TimelineEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 300000).toISOString(),
                    title: 'Mock Recall Initiated',
                    description: 'Drill started for LOT-2024-001',
                    type: 'info',
                    userName: 'QA Manager',
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    title: 'Traceability Gap Detected',
                    description: 'Missing COOLING event for LOT-2024-003',
                    type: 'warning',
                    userName: 'System',
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    title: 'Audit Report Generated',
                    description: 'Weekly FSMA 204 compliance report ready',
                    type: 'success',
                    userName: 'System',
                },
            ];

            return events.slice(0, limit);
        },
    });
};

// ============================================================================
// CTE Coverage Analysis
// ============================================================================

interface CTECoverage {
    event_type: string;
    total_lots: number;
    covered_lots: number;
    coverage_pct: number;
    status: 'excellent' | 'good' | 'warning' | 'critical';
}

export const useCTECoverage = (): UseQueryResult<CTECoverage[]> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'cte-coverage'],
        queryFn: async () => {
            return [
                { event_type: 'Harvest (Growing)', total_lots: 430, covered_lots: 428, coverage_pct: 99.5, status: 'excellent' as const },
                { event_type: 'Cooling', total_lots: 430, covered_lots: 418, coverage_pct: 97.2, status: 'excellent' as const },
                { event_type: 'Packing (Initial)', total_lots: 430, covered_lots: 425, coverage_pct: 98.8, status: 'excellent' as const },
                { event_type: 'Transformation', total_lots: 312, covered_lots: 298, coverage_pct: 95.5, status: 'good' as const },
                { event_type: 'Shipping', total_lots: 430, covered_lots: 422, coverage_pct: 98.1, status: 'excellent' as const },
                { event_type: 'Receiving', total_lots: 430, covered_lots: 410, coverage_pct: 95.3, status: 'good' as const },
            ];
        },
        staleTime: 60000,
    });
};

// ============================================================================
// Traceability Trend (Weekly)
// ============================================================================

interface TrendPoint {
    week: string;
    score: number;
    gaps: number;
    events_processed: number;
}

export const useTraceabilityTrend = (): UseQueryResult<TrendPoint[]> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'trend'],
        queryFn: async () => {
            return [
                { week: 'Jan 6', score: 91, gaps: 28, events_processed: 1240 },
                { week: 'Jan 13', score: 93, gaps: 22, events_processed: 1380 },
                { week: 'Jan 20', score: 94, gaps: 19, events_processed: 1510 },
                { week: 'Jan 27', score: 95, gaps: 16, events_processed: 1620 },
                { week: 'Feb 3', score: 97, gaps: 14, events_processed: 1780 },
                { week: 'Feb 10', score: 98, gaps: 12, events_processed: 1890 },
            ];
        },
        staleTime: 60000,
    });
};

// ============================================================================
// Gap Analysis Breakdown
// ============================================================================

interface GapCategory {
    category: string;
    count: number;
    severity: 'high' | 'medium' | 'low';
    description: string;
    regulation: string;
}

export const useGapAnalysis = (): UseQueryResult<GapCategory[]> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'gap-analysis'],
        queryFn: async () => {
            return [
                { category: 'Missing KDEs', count: 5, severity: 'medium' as const, description: 'Key Data Elements not captured at one or more CTEs', regulation: '21 CFR § 1.1315' },
                { category: 'Broken TLC Links', count: 3, severity: 'high' as const, description: 'Traceability Lot Codes not linked across consecutive events', regulation: '21 CFR § 1.1320' },
                { category: 'Late CTE Capture', count: 2, severity: 'low' as const, description: 'Events recorded more than 24h after occurrence', regulation: '21 CFR § 1.1455' },
                { category: 'Incomplete Receiving', count: 2, severity: 'medium' as const, description: 'Receiving events missing supplier verification data', regulation: '21 CFR § 1.1345(b)' },
            ];
        },
        staleTime: 60000,
    });
};

// ============================================================================
// System Health
// ============================================================================

export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['fsma', 'dashboard', 'health'],
        queryFn: async () => {
            const health: SystemHealth = {
                status: 'HEALTHY',
                message: 'All traceability systems operational',
                lastCheck: '1 min ago',
                uptime: '99.99%',
            };
            return health;
        },
    });
};
