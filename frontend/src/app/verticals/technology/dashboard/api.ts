/**
 * Technology Dashboard API Integration
 * 
 * Dashboard-specific queries for SOC 2/ISO 27001 security compliance monitoring.
 * Mock data implementation - ready for backend Technology service integration.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent, Alert } from '@/components/verticals';

// ============================================================================
// Dashboard Metrics Aggregation
// ============================================================================

/**
 * Fetch aggregated dashboard metrics for Technology compliance.
 */
export const useDashboardMetrics = (): UseQueryResult<MetricConfig[]> => {
    return useQuery({
        queryKey: ['technology', 'dashboard', 'metrics'],
        queryFn: async () => {
            const metrics: MetricConfig[] = [
                {
                    label: 'Security Controls',
                    value: '243',
                    icon: 'Shield' as any,
                    iconColor: 'text-purple-600',
                    iconBgColor: 'bg-purple-100',
                    trend: { value: 8, isPositive: true },
                    helpText: 'Active SOC 2/ISO 27001 controls',
                },
                {
                    label: 'Config Drift Items',
                    value: '7',
                    icon: 'AlertTriangle' as any,
                    iconColor: 'text-amber-600',
                    iconBgColor: 'bg-amber-100',
                    trend: { value: 2, isPositive: false },
                    helpText: 'Configuration deviations',
                },
                {
                    label: 'Vulnerability Score',
                    value: '92/100',
                    icon: 'Bug' as any,
                    iconColor: 'text-green-600',
                    iconBgColor: 'bg-green-100',
                    helpText: 'Vulnerability management rating',
                },
                {
                    label: 'Access Reviews',
                    value: '18',
                    icon: 'Users' as any,
                    iconColor: 'text-blue-600',
                    iconBgColor: 'bg-blue-100',
                    helpText: 'Pending access certifications',
                },
            ];

            return metrics;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Security Control Matrix
// ============================================================================

interface SecurityControl {
    id: string;
    controlId: string;
    framework: 'SOC 2' | 'ISO 27001' | 'NIST CSF' | 'CIS Controls';
    domain: string;
    description: string;
    status: 'implemented' | 'in_progress' | 'not_implemented';
    lastAudited: string;
    owner: string;
}

/**
 * Fetch security control implementation status.
 */
export const useSecurityControls = (): UseQueryResult<SecurityControl[]> => {
    return useQuery({
        queryKey: ['technology', 'security-controls'],
        queryFn: async () => {
            const controls: SecurityControl[] = [
                {
                    id: 'sec_001',
                    controlId: 'CC6.1',
                    framework: 'SOC 2',
                    domain: 'Change Management',
                    description: 'Logical and physical access controls',
                    status: 'implemented',
                    lastAudited: '12 days ago',
                    owner: 'InfoSec Team',
                },
                {
                    id: 'sec_002',
                    controlId: 'A.9.2.1',
                    framework: 'ISO 27001',
                    domain: 'Access Control',
                    description: 'User registration and de-registration',
                    status: 'implemented',
                    lastAudited: '8 days ago',
                    owner: 'IT Operations',
                },
                {
                    id: 'sec_003',
                    controlId: 'PR.AC-4',
                    framework: 'NIST CSF',
                    domain: 'Identity Management',
                    description: 'Access permissions managed',
                    status: 'implemented',
                    lastAudited: '15 days ago',
                    owner: 'IAM Team',
                },
                {
                    id: 'sec_004',
                    controlId: 'CIS-5.1',
                    framework: 'CIS Controls',
                    domain: 'Account Management',
                    description: 'Centralized account management',
                    status: 'in_progress',
                    lastAudited: '20 days ago',
                    owner: 'Platform Engineering',
                },
            ];

            return controls;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Configuration Drift Monitor
// ============================================================================

interface DriftItem {
    id: string;
    resource: string;
    resourceType: 'EC2' | 'S3' | 'RDS' | 'IAM' | 'Security Group';
    baseline: string;
    currentState: string;
    driftType: 'security' | 'compliance' | 'operational';
    severity: 'critical' | 'high' | 'medium' | 'low';
    detectedAt: string;
}

/**
 * Fetch configuration drift items detected across infrastructure.
 */
export const useConfigurationDrift = (limit: number = 5): UseQueryResult<DriftItem[]> => {
    return useQuery({
        queryKey: ['technology', 'config-drift', limit],
        queryFn: async () => {
            const drifts: DriftItem[] = [
                {
                    id: 'drift_001',
                    resource: 'prod-web-server-01',
                    resourceType: 'EC2',
                    baseline: 'Ubuntu 22.04 LTS with security hardening',
                    currentState: 'SSH enabled on port 22 (should be disabled)',
                    driftType: 'security',
                    severity: 'high',
                    detectedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
                },
                {
                    id: 'drift_002',
                    resource: 'prod-db-backup',
                    resourceType: 'S3',
                    baseline: 'Versioning enabled with 30-day lifecycle',
                    currentState: 'Lifecycle policy changed to 7 days',
                    driftType: 'compliance',
                    severity: 'medium',
                    detectedAt: new Date(Date.now() - 3600000 * 6).toISOString(),
                },
                {
                    id: 'drift_003',
                    resource: 'prod-database-rds',
                    resourceType: 'RDS',
                    baseline: 'Automated backups with 7-day retention',
                    currentState: 'Backup window modified',
                    driftType: 'operational',
                    severity: 'low',
                    detectedAt: new Date(Date.now() - 3600000 * 12).toISOString(),
                },
            ];

            return drifts.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Access Review Dashboard
// ============================================================================

interface AccessReview {
    id: string;
    userName: string;
    userEmail: string;
    accessLevel: 'Admin' | 'Developer' | 'Read-Only';
    resources: string[];
    lastReviewDate: string;
    reviewStatus: 'pending' | 'approved' | 'revoked';
    certifier: string;
}

/**
 * Fetch pending access reviews for certification.
 */
export const useAccessReviews = (limit: number = 5): UseQueryResult<AccessReview[]> => {
    return useQuery({
        queryKey: ['technology', 'access-reviews', limit],
        queryFn: async () => {
            const reviews: AccessReview[] = [
                {
                    id: 'review_001',
                    userName: 'John Smith',
                    userEmail: 'john.smith@company.com',
                    accessLevel: 'Admin',
                    resources: ['Production Database', 'AWS Console'],
                    lastReviewDate: '90 days ago',
                    reviewStatus: 'pending',
                    certifier: 'InfoSec Team',
                },
                {
                    id: 'review_002',
                    userName: 'Jane Doe',
                    userEmail: 'jane.doe@company.com',
                    accessLevel: 'Developer',
                    resources: ['GitHub Org', 'CI/CD Pipeline'],
                    lastReviewDate: '85 days ago',
                    reviewStatus: 'pending',
                    certifier: 'Engineering Manager',
                },
                {
                    id: 'review_003',
                    userName: 'Bob Johnson',
                    userEmail: 'bob.johnson@company.com',
                    accessLevel: 'Admin',
                    resources: ['Kubernetes Cluster'],
                    lastReviewDate: '60 days ago',
                    reviewStatus: 'approved',
                    certifier: 'Platform Lead',
                },
            ];

            return reviews.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// ISO 27001 Gap Analysis
// ============================================================================

interface ISOGap {
    controlId: string;
    controlName: string;
    annexReference: string;
    status: 'compliant' | 'partial' | 'non_compliant';
    gapDescription?: string;
    remediation?: string;
}

/**
 * Fetch ISO 27001 gap analysis results.
 */
export const useISOGapAnalysis = (): UseQueryResult<ISOGap[]> => {
    return useQuery({
        queryKey: ['technology', 'iso-gaps'],
        queryFn: async () => {
            const gaps: ISOGap[] = [
                {
                    controlId: 'A.8.1.3',
                    controlName: 'Acceptable use of assets',
                    annexReference: 'Annex A.8 Asset Management',
                    status: 'compliant',
                },
                {
                    controlId: 'A.12.1.2',
                    controlName: 'Change management',
                    annexReference: 'Annex A.12 Operations Security',
                    status: 'partial',
                    gapDescription: 'Change approval workflow not automated',
                    remediation: 'Implement ServiceNow change management integration',
                },
                {
                    controlId: 'A.18.1.1',
                    controlName: 'Identification of applicable legislation',
                    annexReference: 'Annex A.18 Compliance',
                    status: 'compliant',
                },
            ];

            return gaps;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Continuous Monitoring Feed
// ============================================================================

/**
 * Fetch recent continuous monitoring events.
 */
export const useMonitoringFeed = (limit: number = 5): UseQueryResult<TimelineEvent[]> => {
    return useQuery({
        queryKey: ['technology', 'monitoring-feed', limit],
        queryFn: async () => {
            const events: TimelineEvent[] = [
                {
                    id: '1',
                    timestamp: new Date(Date.now() - 1800000).toISOString(),
                    title: 'Configuration drift detected',
                    description: 'SSH enabled on prod-web-server-01 (policy violation)',
                    type: 'warning',
                    userName: 'Security Scanner',
                    metadata: { severity: 'High', resource: 'EC2' },
                },
                {
                    id: '2',
                    timestamp: new Date(Date.now() - 3600000).toISOString(),
                    title: 'Access review completed',
                    description: 'Admin access certified for Bob Johnson',
                    type: 'success',
                    userName: 'Platform Lead',
                    metadata: { user: 'bob.johnson@company.com' },
                },
                {
                    id: '3',
                    timestamp: new Date(Date.now() - 7200000).toISOString(),
                    title: 'Vulnerability scan completed',
                    description: 'No critical vulnerabilities found',
                    type: 'success',
                    userName: 'Vulnerability Scanner',
                    metadata: { score: '92/100' },
                },
                {
                    id: '4',
                    timestamp: new Date(Date.now() - 10800000).toISOString(),
                    title: 'SOC 2 control tested',
                    description: 'Change management control CC6.1 passed',
                    type: 'success',
                    userName: 'InfoSec Team',
                    metadata: { framework: 'SOC 2' },
                },
            ];

            return events.slice(0, limit);
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// System Health Monitor
// ============================================================================

/**
 * Fetch overall Technology compliance system health.
 */
export const useSystemHealth = (): UseQueryResult<SystemHealth> => {
    return useQuery({
        queryKey: ['technology', 'health'],
        queryFn: async () => {
            const health: SystemHealth = {
                status: 'HEALTHY',
                message: 'All security systems operational',
                lastCheck: '1 min ago',
                uptime: '99.97%',
            };

            return health;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};

// ============================================================================
// Compliance Automation Status
// ============================================================================

interface AutomationStatus {
    category: string;
    automationLevel: number;
    automatedControls: number;
    totalControls: number;
}

/**
 * Fetch compliance automation status across security domains.
 */
export const useAutomationStatus = (): UseQueryResult<AutomationStatus[]> => {
    return useQuery({
        queryKey: ['technology', 'automation-status'],
        queryFn: async () => {
            const status: AutomationStatus[] = [
                {
                    category: 'Access Management',
                    automationLevel: 85,
                    automatedControls: 34,
                    totalControls: 40,
                },
                {
                    category: 'Vulnerability Management',
                    automationLevel: 92,
                    automatedControls: 23,
                    totalControls: 25,
                },
                {
                    category: 'Configuration Management',
                    automationLevel: 78,
                    automatedControls: 28,
                    totalControls: 36,
                },
                {
                    category: 'Log Management',
                    automationLevel: 95,
                    automatedControls: 19,
                    totalControls: 20,
                },
            ];

            return status;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
};
