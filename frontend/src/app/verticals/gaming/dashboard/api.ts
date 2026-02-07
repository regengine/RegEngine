/**
 * Gaming Dashboard API Integration
 *
 * Mock data for Gaming vertical dashboard.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent, Alert } from '@/components/verticals';
import { Dices, Shield, DollarSign, Users, Activity } from 'lucide-react';

export const useGamingMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['gaming', 'dashboard', 'metrics'],
        queryFn: async () => {
            return [
                {
                    label: 'Daily Handle',
                    value: '$4.2M',
                    icon: DollarSign as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    trend: { value: 12.5, isPositive: true },
                },
                {
                    label: 'Active Players',
                    value: '14,205',
                    icon: Users as any,
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    trend: { value: 4.2, isPositive: true },
                },
                {
                    label: 'Self-Exclusions',
                    value: '3',
                    icon: Shield as any,
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    helpText: 'New exclusions today',
                },
                {
                    label: 'AML Alerts',
                    value: '0',
                    icon: Activity as any,
                    iconColor: 'text-purple-600',
                    iconBgColor: 'bg-purple-100',
                    helpText: 'Suspicious activity reports',
                },
            ];
        },
        staleTime: 30000,
    });
};

export const useGamingTimeline = (): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['gaming', 'dashboard', 'timeline'],
        queryFn: async () => {
            const events: TimelineEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 120000).toISOString(),
                    title: 'High Velocity Bet Detected',
                    description: 'Player 9942 placed 5 max bets in 10s',
                    type: 'warning',
                    userName: 'Risk Engine',
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 900000).toISOString(),
                    title: 'Jackpot Verified',
                    description: 'Progressive Jackpot win at Slot Bank 4',
                    type: 'success',
                    userName: 'System',
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    title: 'Shift Change Logged',
                    description: 'Pit Boss shift change completed',
                    type: 'info',
                    userName: 'Pit Boss',
                },
            ];
            return events;
        },
    });
};

export const useComplianceAlerts = (): UseQueryResult<Alert[]> => {
    return useQuery({
        queryKey: ['gaming', 'dashboard', 'alerts'],
        queryFn: async () => {
            const alerts: Alert[] = [
                {
                    id: '1',
                    severity: 'CRITICAL',
                    title: 'Jurisdiction Mismatch',
                    message: 'Player accessed geo-fenced game from unauthorized IP range',
                    timestamp: new Date().toISOString(),
                    source: 'Geo-comply',
                },
            ];
            return alerts;
        },
    });
};
