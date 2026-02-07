/**
 * Healthcare Dashboard API Integration
 * 
 * Dashboard-specific queries for HIPAA/PHI compliance monitoring.
 * Mock data implementation - ready for backend Healthcare service integration.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent } from '@/components/verticals';

// ============================================================================
// Dashboard Metrics
// ============================================================================

export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['healthcare', 'dashboard', 'metrics'],
        queryFn: async () => {
            const metrics: MetricConfig[] = [
                {
                    label: 'PHI Access Events',
                    value: '1,247',
                    icon: 'Lock' as any,
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    trend: { value: 5, isPositive: true },
                    helpText: 'Protected Health Information access logs',
                },
                {
                    label: 'HIPAA Violations',
                    value: '0',
                    icon: 'ShieldCheck' as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    helpText: 'Zero HIPAA violations this period',
                },
                {
                    label: 'Breach Risk Score',
                    value: '8/100',
                    icon: 'AlertTriangle' as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    helpText: 'Low breach risk (lower is better)',
                },
                {
                    label: 'BAA Compliance',
                    value: '98%',
                    icon: 'FileSignature' as any,
                    iconColor: 'text-purple-600',
                    iconBgColor: 'bg-purple-100',
                    helpText: 'Business Associate Agreement coverage',
                },
            ];
            return metrics;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// PHI Access Monitor
// ============================================================================

interface PHIAccessEvent {
    id: string;
    timestamp: string;
    userId: string;
    userName: string;
    role: string;
    action: 'VIEW' | 'EDIT' | 'EXPORT' | 'DELETE';
    patientId: string;
    riskLevel: 'low' | 'medium' | 'high';
    authorized: boolean;
}

export const usePHIAccessLog = (limit: number = 10): UseQueryResult<PHIAccessEvent[]> => {
    return useQuery({
        queryKey: ['healthcare', 'phi-access', limit],
        queryFn: async () => {
            const events: PHIAccessEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 600000).toISOString(),
                    userId: 'DR001',
                    userName: 'Dr. Sarah Johnson',
                    role: 'Physician',
                    action: 'VIEW',
                    patientId: 'PT-2024-1847',
                    riskLevel: 'low',
                    authorized: true,
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 1800000).toISOString(),
                    userId: 'RN042',
                    userName: 'Nurse Emily Davis',
                    role: 'Registered Nurse',
                    action: 'EDIT',
                    patientId: 'PT-2024-1891',
                    riskLevel: 'low',
                    authorized: true,
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    userId: 'AD  018',
                    userName: 'Admin Lisa Chen',
                    role: 'Administrator',
                    action: 'EXPORT',
                    patientId: 'PT-2024-1456',
                    riskLevel: 'medium',
                    authorized: true,
                },
            ];
            return events.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Audit Timeline
// ============================================================================

export const useAuditTimeline = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['healthcare', 'audit-timeline', limit],
        queryFn: async () => {
            const events: TimelineEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 1800000).toISOString(),
                    title: 'HIPAA audit completed',
                    description: 'Annual compliance audit passed with zero findings',
                    type: 'success',
                    userName: 'Compliance Team',
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    title: 'BAA agreement signed',
                    description: 'New vendor CloudMed added to BAA registry',
                    type: 'info',
                    userName: 'Legal Department',
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 14400000).toISOString(),
                    title: 'Security training completed',
                    description: 'Q1 HIPAA security awareness training - 100% completion',
                    type: 'success',
                    userName: 'HR Department',
                },
            ];
            return events.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// System Health
// ============================================================================

export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['healthcare', 'health'],
        queryFn: async () => {
            return {
                status: 'HEALTHY',
                message: 'All HIPAA compliance systems operational',
                lastCheck: '30 sec ago',
                uptime: '99.99%',
            } as SystemHealth;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Risk Heatmap
// ============================================================================

interface RiskArea {
    department: string;
    accessCount: number;
    violations: number;
    riskScore: number;
}

export const useRiskHeatmap = (): UseQueryResult<RiskArea[]> => {
    return useQuery({
        queryKey: ['healthcare', 'risk-heatmap'],
        queryFn: async () => {
            return [
                { department: 'Emergency', accessCount: 342, violations: 0, riskScore: 12 },
                { department: 'ICU', accessCount: 189, violations: 0, riskScore: 8 },
                { department: 'Cardiology', accessCount: 156, violations: 0, riskScore: 5 },
                { department: 'Radiology', accessCount: 234, violations: 0, riskScore: 9 },
                { department: 'Billing', accessCount: 421, violations: 0, riskScore: 14 },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
