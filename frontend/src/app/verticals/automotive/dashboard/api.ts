/**
 * Automotive Dashboard API Integration
 * 
 * Dashboard for IATF 16949 and PPAP compliance monitoring.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent } from '@/components/verticals';

export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['automotive', 'dashboard', 'metrics'],
        queryFn: async () => {
            return [
                { label: 'PPAP Submissions', value: '847', icon: 'FileCheck' as any, iconColor: 'text-blue-600', iconBgColor: 'bg-blue-100', trend: { value: 15, isPositive: true }, helpText: 'Production Part Approval Process' },
                { label: 'Supplier Quality', value: '96.2%', icon: 'TruckCheck' as any, iconColor: 'text-green-600', iconBgColor: 'bg-green-100', helpText: 'Supplier performance rating' },
                { label: '8D Reports Open', value: '5', icon: 'AlertCircle' as any, iconColor: 'text-amber-600', iconBgColor: 'bg-amber-100', helpText: '8-Discipline problem solving' },
                { label: 'IATF Compliance', value: '98%', icon: 'Award' as any, iconColor: 'text-purple-600', iconBgColor: 'bg-purple-100', helpText: 'IATF 16949 audit score' },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['automotive', 'health'],
        queryFn: async () => ({ status: 'HEALTHY', message: 'All systems operational', lastCheck: '30 sec ago', uptime: '99.99%' } as SystemHealth),
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useAuditTimeline = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['automotive', 'timeline', limit],
        queryFn: async () => ([
            { id: '1', timestamp: new Date(Date.now() - 3600000).toISOString(), title: 'PPAP submitted', description: 'Part #A4782 PPAP Level 3 submitted to OEM', type: 'success', userName: 'Quality Engineer' },
            { id: '2', timestamp: new Date(Date.now() - 7200000).toISOString(), title: '8D closed', description: '8D-2024-003 root cause implemented', type: 'success', userName: 'Production Manager' },
        ] as TimelineEvent[]),
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
