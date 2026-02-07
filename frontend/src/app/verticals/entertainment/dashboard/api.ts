/**
 * Entertainment Dashboard API Integration
 *
 * Mock data for Entertainment (PCOS) vertical dashboard.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, TimelineEvent, Alert } from '@/components/verticals';
import { Film, Users, DollarSign, Clock, AlertCircle } from 'lucide-react';

export const useEntertainmentMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['entertainment', 'dashboard', 'metrics'],
        queryFn: async () => {
            return [
                {
                    label: 'Active Productions',
                    value: '8',
                    icon: Film as any,
                    iconColor: 'text-purple-600',
                    iconBgColor: 'bg-purple-100',
                },
                {
                    label: 'Crew Verified',
                    value: '423',
                    icon: Users as any,
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    helpText: '100% eligibility confirmed',
                },
                {
                    label: 'Meal Penalties',
                    value: '$1,250',
                    icon: DollarSign as any,
                    iconColor: 'text-red-600',
                    iconBgColor: 'bg-red-100',
                    helpText: 'Accumulated this week',
                    trend: { value: 15, isPositive: false },
                },
                {
                    label: 'OT Hours',
                    value: '142',
                    icon: Clock as any,
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    trend: { value: 5, isPositive: true },
                },
            ];
        },
        staleTime: 30000,
    });
};

export const useEntertainmentTimeline = (): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['entertainment', 'dashboard', 'timeline'],
        queryFn: async () => {
            const events: TimelineEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 300000).toISOString(),
                    title: 'Meal Penalty Warning',
                    description: 'Production A approaching 6th hour without meal break',
                    type: 'warning',
                    userName: 'Timekeeper',
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 1800000).toISOString(),
                    title: 'Crew Member Added',
                    description: 'John Doe (Camera Op) verified via IATSE Local 600',
                    type: 'success',
                    userName: 'Onboarding',
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    title: 'Call Sheet Approved',
                    description: 'Day 12 Call Sheet distributed for Production B',
                    type: 'info',
                    userName: 'AD Team',
                },
            ];
            return events;
        },
    });
};

export const useSafetyAlerts = (): UseQueryResult<Alert[]> => {
    return useQuery({
        queryKey: ['entertainment', 'dashboard', 'alerts'],
        queryFn: async () => {
            const alerts: Alert[] = [
                {
                    id: '1',
                    severity: 'INFO',
                    title: 'Safety Meeting Required',
                    message: 'Pyrotechnics scheduled for Scene 42. Safety meeting mandatory.',
                    timestamp: new Date().toISOString(),
                    source: 'Safety Officer',
                },
            ];
            return alerts;
        },
    });
};
