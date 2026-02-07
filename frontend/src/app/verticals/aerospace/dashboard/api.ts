/**
 * Aerospace Dashboard API Integration
 * 
 * Dashboard for AS9100 and FAI compliance monitoring.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent } from '@/components/verticals';

export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['aerospace', 'dashboard', 'metrics'],
        queryFn: async () => {
            return [
                { label: 'FAI Reports', value: '234', icon: 'ClipboardCheck' as any, iconColor: 'text-indigo-600', iconBgColor: 'bg-indigo-100', trend: { value: 8, isPositive: true }, helpText: 'First Article Inspections (AS9102)' },
                { label: 'Config Items', value: '1,847', icon: 'Settings' as any, iconColor: 'text-cyan-600', iconBgColor: 'bg-cyan-100', helpText: 'Configuration-controlled items' },
                { label: 'Supplier Audits', value: '12', icon: 'Building2' as any, iconColor: 'text-purple-600', iconBgColor: 'bg-purple-100', helpText: 'Completed this quarter' },
                { label: 'AS9100 Score', value: '97%', icon: 'Award' as any, iconColor: 'text-green-600', iconBgColor: 'bg-green-100', helpText: 'Aerospace quality certification' },
            ];
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['aerospace', 'health'],
        queryFn: async () => ({ status: 'HEALTHY', message: 'All aerospace compliance systems operational', lastCheck: '30 sec ago', uptime: '99.99%' } as SystemHealth),
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useAuditTimeline = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['aerospace', 'timeline', limit],
        queryFn: async () => [
            { id: '1', timestamp: new Date(Date.now() - 3600000).toISOString(), title: 'FAI approved', description: 'FAI-2024-089 for wing bracket assembly approved', type: 'success', userName: 'Quality Inspector' },
            { id: '2', timestamp: new Date(Date.now() - 7200000).toISOString(), title: 'Config change', description: 'ECN-4723 baseline updated', type: 'info', userName: 'Configuration Manager' },
        ] as TimelineEvent[],
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
