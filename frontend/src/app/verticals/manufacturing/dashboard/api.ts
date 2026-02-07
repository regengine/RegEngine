/**
 * Manufacturing Dashboard API Integration
 * 
 * Dashboard for ISO 9001/14001/45001 triple-certification monitoring.
 * Mock data implementation - ready for backend Manufacturing service integration.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent } from '@/components/verticals';

export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['manufacturing', 'dashboard', 'metrics'],
        queryFn: async () => {
            return [
                {
                    label: 'ISO Certifications',
                    value: '3',
                    icon: 'Award' as any,
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    helpText: 'ISO 9001/14001/45001 active',
                },
                {
                    label: 'NCRs Open',
                    value: '12',
                    icon: 'AlertCircle' as any,
                    iconColor: 'text-orange-600',
                    iconBgColor: 'bg-orange-100',
                    trend: { value: 3, isPositive: false },
                    helpText: 'Non-Conformance Reports',
                },
                {
                    label: 'Quality Score',
                    value: '95.3%',
                    icon: 'Target' as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    trend: { value: 1.2, isPositive: true },
                    helpText: 'Overall quality rating',
                },
                {
                    label: 'Safety Incidents',
                    value: '0',
                    icon: 'ShieldCheck' as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    helpText: 'Zero incidents this month',
                },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

interface ISOCertification {
    standard: string;
    status: 'certified' | 'in_audit' | 'expired';
    certBody: string;
    expiryDate: string;
    lastAudit: string;
    nextAudit: string;
}

export const useISOCertifications = (): UseQueryResult<ISOCertification[]> => {
    return useQuery({
        queryKey: ['manufacturing', 'iso-certs'],
        queryFn: async (): Promise<ISOCertification[]> => {
            return [
                {
                    standard: 'ISO 9001:2015',
                    status: 'certified' as const,
                    certBody: 'BSI',
                    expiryDate: '2026-08-15',
                    lastAudit: '2024-02-10',
                    nextAudit: '2025-02-01',
                },
                {
                    standard: 'ISO 14001:2015',
                    status: 'certified' as const,
                    certBody: 'BSI',
                    expiryDate: '2026-08-15',
                    lastAudit: '2024-02-10',
                    nextAudit: '2025-02-01',
                },
                {
                    standard: 'ISO 45001:2018',
                    status: 'certified' as const,
                    certBody: 'BSI',
                    expiryDate: '2026-08-15',
                    lastAudit: '2024-02-10',
                    nextAudit: '2025-02-01',
                },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

interface NCR {
    id: string;
    title: string;
    severity: 'critical' | 'major' | 'minor';
    standard: string;
    raisedDate: string;
    dueDate: string;
    status: 'open' | 'in_progress' | 'closed';
    assignee: string;
}

export const useNCRs = (limit: number = 10): UseQueryResult<NCR[]> => {
    return useQuery({
        queryKey: ['manufacturing', 'ncrs', limit],
        queryFn: async () => {
            const ncrs: NCR[] = [
                {
                    id: 'NCR-2024-047',
                    title: 'Calibration records incomplete for CMM-01',
                    severity: 'major',
                    standard: 'ISO 9001',
                    raisedDate: '2024-01-20',
                    dueDate: '2024-02-05',
                    status: 'in_progress',
                    assignee: 'Quality Team',
                },
                {
                    id: 'NCR-2024-048',
                    title: 'Waste segregation non-compliance in Area 3',
                    severity: 'minor',
                    standard: 'ISO 14001',
                    raisedDate: '2024-01-22',
                    dueDate: '2024-02-10',
                    status: 'open',
                    assignee: 'EHS Team',
                },
            ];
            return ncrs.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useAuditTimeline = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['manufacturing', 'audit-timeline', limit],
        queryFn: async (): Promise<TimelineEvent[]> => {
            return [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    title: 'Internal audit completed',
                    description: 'Q1 ISO 9001 internal audit - 2 minor findings',
                    type: 'info' as const,
                    userName: 'Quality Manager',
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    title: 'NCR closed',
                    description: 'NCR-2024-042 resolved and verified',
                    type: 'success' as const,
                    userName: 'Production Team',
                },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['manufacturing', 'health'],
        queryFn: async (): Promise<SystemHealth> => {
            return {
                status: 'HEALTHY' as const,
                message: 'All manufacturing compliance systems operational',
                lastCheck: '1 min ago',
                uptime: '99.96%',
            };
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
