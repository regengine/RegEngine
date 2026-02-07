/**
 * Dashboard Index API Integration
 * 
 * Aggregates metrics across all 10 industry verticals for unified dashboard view.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';

// ============================================================================
// Types
// ============================================================================

export interface VerticalSummary {
    id: string;
    name: string;
    slug: string;
    icon: string;
    iconColor: string;
    iconBgColor: string;
    complianceScore: number;
    scoreChange: number; // +/- percentage
    status: 'healthy' | 'warning' | 'critical';
    activeAlerts: number;
    lastUpdated: string;
    primaryStandard: string;
    quickStats: {
        label: string;
        value: string;
    }[];
}

export interface SystemOverview {
    overallScore: number;
    totalVerticals: number;
    healthyVerticals: number;
    warningVerticals: number;
    criticalVerticals: number;
    totalAlerts: number;
    lastSystemCheck: string;
}

// ============================================================================
// Hooks
// ============================================================================

export const useVerticalSummaries = (): UseQueryResult<VerticalSummary[]> => {
    return useQuery({
        queryKey: ['dashboard', 'vertical-summaries'],
        queryFn: async () => {
            const summaries: VerticalSummary[] = [
                {
                    id: 'energy',
                    name: 'Energy',
                    slug: 'energy',
                    icon: 'Zap',
                    iconColor: 'text-yellow-600',
                    iconBgColor: 'bg-yellow-100',
                    complianceScore: 94,
                    scoreChange: 2,
                    status: 'healthy',
                    activeAlerts: 3,
                    lastUpdated: new Date(Date.now() - 1800000).toISOString(),
                    primaryStandard: 'NERC CIP-013',
                    quickStats: [
                        { label: 'Controls', value: '847' },
                        { label: 'Facilities', value: '12' },
                    ],
                },
                {
                    id: 'nuclear',
                    name: 'Nuclear',
                    slug: 'nuclear',
                    icon: 'Atom',
                    iconColor: 'text-purple-600',
                    iconBgColor: 'bg-purple-100',
                    complianceScore: 96,
                    scoreChange: 1,
                    status: 'healthy',
                    activeAlerts: 0,
                    lastUpdated: new Date(Date.now() - 600000).toISOString(),
                    primaryStandard: '10 CFR 50 App B',
                    quickStats: [
                        { label: 'Records', value: '18,247' },
                        { label: 'Legal Holds', value: '4' },
                    ],
                },
                {
                    id: 'finance',
                    name: 'Finance',
                    slug: 'finance',
                    icon: 'DollarSign',
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    complianceScore: 98,
                    scoreChange: 3,
                    status: 'healthy',
                    activeAlerts: 1,
                    lastUpdated: new Date(Date.now() - 900000).toISOString(),
                    primaryStandard: 'SOX 404',
                    quickStats: [
                        { label: 'Filings', value: '847' },
                        { label: 'Controls', value: '234' },
                    ],
                },
                {
                    id: 'technology',
                    name: 'Technology',
                    slug: 'technology',
                    icon: 'Server',
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    complianceScore: 94,
                    scoreChange: -1,
                    status: 'healthy',
                    activeAlerts: 7,
                    lastUpdated: new Date(Date.now() - 300000).toISOString(),
                    primaryStandard: 'SOC 2 / ISO 27001',
                    quickStats: [
                        { label: 'Controls', value: '243' },
                        { label: 'Drift Items', value: '7' },
                    ],
                },
                {
                    id: 'healthcare',
                    name: 'Healthcare',
                    slug: 'healthcare',
                    icon: 'Heart',
                    iconColor: 'text-red-600',
                    iconBgColor: 'bg-red-100',
                    complianceScore: 97,
                    scoreChange: 0,
                    status: 'healthy',
                    activeAlerts: 2,
                    lastUpdated: new Date(Date.now() - 1200000).toISOString(),
                    primaryStandard: 'HIPAA',
                    quickStats: [
                        { label: 'PHI Access', value: '1,247' },
                        { label: 'Risk Score', value: '8/100' },
                    ],
                },
                {
                    id: 'manufacturing',
                    name: 'Manufacturing',
                    slug: 'manufacturing',
                    icon: 'Factory',
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    complianceScore: 95,
                    scoreChange: 2,
                    status: 'healthy',
                    activeAlerts: 4,
                    lastUpdated: new Date(Date.now() - 2400000).toISOString(),
                    primaryStandard: 'ISO 9001/14001/45001',
                    quickStats: [
                        { label: 'Certifications', value: '3' },
                        { label: 'NCRs', value: '12' },
                    ],
                },
                {
                    id: 'automotive',
                    name: 'Automotive',
                    slug: 'automotive',
                    icon: 'Car',
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    complianceScore: 98,
                    scoreChange: 3,
                    status: 'healthy',
                    activeAlerts: 1,
                    lastUpdated: new Date(Date.now() - 1800000).toISOString(),
                    primaryStandard: 'IATF 16949',
                    quickStats: [
                        { label: 'PPAP', value: '847' },
                        { label: '8D Reports', value: '5' },
                    ],
                },
                {
                    id: 'aerospace',
                    name: 'Aerospace',
                    slug: 'aerospace',
                    icon: 'Plane',
                    iconColor: 'text-indigo-600',
                    iconBgColor: 'bg-indigo-100',
                    complianceScore: 97,
                    scoreChange: 2,
                    status: 'healthy',
                    activeAlerts: 3,
                    lastUpdated: new Date(Date.now() - 3600000).toISOString(),
                    primaryStandard: 'AS9100',
                    quickStats: [
                        { label: 'FAI Reports', value: '234' },
                        { label: 'Config Items', value: '1,847' },
                    ],
                },
                {
                    id: 'construction',
                    name: 'Construction',
                    slug: 'construction',
                    icon: 'Hammer',
                    iconColor: 'text-cyan-600',
                    iconBgColor: 'bg-cyan-100',
                    complianceScore: 94,
                    scoreChange: 3,
                    status: 'healthy',
                    activeAlerts: 5,
                    lastUpdated: new Date(Date.now() - 4800000).toISOString(),
                    primaryStandard: 'ISO 19650',
                    quickStats: [
                        { label: 'BIM Models', value: '47' },
                        { label: 'Change Orders', value: '18' },
                    ],
                },
                {
                    id: 'gaming',
                    name: 'Gaming',
                    slug: 'gaming',
                    icon: 'Gamepad2',
                    iconColor: 'text-pink-600',
                    iconBgColor: 'bg-pink-100',
                    complianceScore: 92,
                    scoreChange: -2,
                    status: 'warning',
                    activeAlerts: 8,
                    lastUpdated: new Date(Date.now() - 7200000).toISOString(),
                    primaryStandard: 'Responsible Gaming',
                    quickStats: [
                        { label: 'Players Monitored', value: '2.4M' },
                        { label: 'Interventions', value: '34' },
                    ],
                },
            ];

            return summaries;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

export const useSystemOverview = (): UseQueryResult<SystemOverview> => {
    return useQuery({
        queryKey: ['dashboard', 'system-overview'],
        queryFn: async () => {
            return {
                overallScore: 96,
                totalVerticals: 10,
                healthyVerticals: 9,
                warningVerticals: 1,
                criticalVerticals: 0,
                totalAlerts: 34,
                lastSystemCheck: new Date(Date.now() - 60000).toISOString(),
            };
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
