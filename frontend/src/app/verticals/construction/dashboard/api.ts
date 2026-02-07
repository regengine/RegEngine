/**
 * Construction Dashboard API Integration
 * 
 * Dashboard for ISO 19650 BIM and construction compliance monitoring.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent } from '@/components/verticals';

export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['construction', 'dashboard', 'metrics'],
        queryFn: async () => {
            return [
                { label: 'BIM Models', value: '47', icon: 'Box' as any, iconColor: 'text-cyan-600', iconBgColor: 'bg-cyan-100', helpText: 'Active BIM coordination models' },
                { label: 'Change Orders', value: '18', icon: 'FileEdit' as any, iconColor: 'text-amber-600', iconBgColor: 'bg-amber-100', trend: { value: 2, isPositive: false }, helpText: 'Pending change approvals' },
                { label: 'Safety Incidents', value: '0', icon: 'HardHat' as any, iconColor: 'text-green-600', iconBgColor: 'bg-green-100', helpText: 'Zero incidents this month' },
                { label: 'ISO 19650 Score', value: '94%', icon: 'Award' as any, iconColor: 'text-purple-600', iconBgColor: 'bg-purple-100', helpText: 'BIM information management' },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['construction', 'health'],
        queryFn: async () => ({ status: 'HEALTHY', message: 'All systems operational', lastCheck: '30 sec ago', uptime: '99.99%' } as SystemHealth),
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useAuditTimeline = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['construction', 'timeline', limit],
        queryFn: async () => ([
            { id: '1', timestamp: new Date(Date.now() - 3600000).toISOString(), title: 'BIM model updated', description: 'Structural model v2.4 published to CDE', type: 'success', userName: 'BIM Coordinator' },
            { id: '2', timestamp: new Date(Date.now() - 7200000).toISOString(), title: 'Safety inspection passed', description: 'Weekly site safety audit - zero findings', type: 'success', userName: 'Safety Manager' },
        ] as TimelineEvent[]),
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
