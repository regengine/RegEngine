/**
 * Mock compliance data for demo/development mode.
 * Used when backend API is unavailable.
 */

import { MOCK_TENANTS } from './mock-tenants';

// Calculate countdown seconds from hours
const hoursToSeconds = (hours: number) => hours * 3600;

// Mock alerts that vary by tenant
const MOCK_ALERTS_BY_TENANT: Record<string, any[]> = {
    // Taylor Farms - Supplier with leafy greens
    '00000000-0000-0000-0000-000000000002': [
        {
            id: 'alert-001',
            title: 'FDA Class I Recall: Romaine Lettuce - E. coli O157:H7',
            summary: 'Multi-state outbreak linked to romaine lettuce from Salinas Valley. 47 cases reported across 16 states.',
            severity: 'CRITICAL',
            severity_emoji: '🚨',
            countdown_seconds: hoursToSeconds(18),
            countdown_display: '18h 0m',
            is_expired: false,
            status: 'ACTIVE',
            required_actions: [
                { action: 'Review affected lot codes (LOT-2026-A through LOT-2026-F)', completed: false },
                { action: 'Run trace-forward analysis to identify distribution', completed: false },
                { action: 'Prepare FDA Form 3177 response', completed: false },
            ],
            created_at: new Date().toISOString(),
        },
    ],
    // Wholesale Club - Retailer
    '00000000-0000-0000-0000-000000000003': [
        {
            id: 'alert-002',
            title: 'Supplier Alert: Fresh Express Voluntary Recall',
            summary: 'Fresh Express announced voluntary recall of bagged salad products. Verify store inventory.',
            severity: 'HIGH',
            severity_emoji: '⚠️',
            countdown_seconds: hoursToSeconds(22),
            countdown_display: '22h 0m',
            is_expired: false,
            status: 'ACTIVE',
            required_actions: [
                { action: 'Check store inventory for affected SKUs', completed: true },
                { action: 'Issue customer notification', completed: false },
                { action: 'Document recall response for compliance', completed: false },
            ],
            created_at: new Date().toISOString(),
        },
    ],
    // Driscoll's - Berries supplier
    '00000000-0000-0000-0000-000000000004': [],
    // Default / System
    '00000000-0000-0000-0000-000000000001': [],
};

// Generate mock status based on alerts
function getMockStatus(tenantId: string) {
    const tenant = MOCK_TENANTS.find(t => t.id === tenantId) || MOCK_TENANTS[0];
    const alerts = MOCK_ALERTS_BY_TENANT[tenantId] || [];

    const criticalCount = alerts.filter(a => a.severity === 'CRITICAL').length;
    const highCount = alerts.filter(a => a.severity === 'HIGH').length;
    const totalActive = alerts.length;

    let status: 'COMPLIANT' | 'AT_RISK' | 'NON_COMPLIANT';
    let statusEmoji: string;
    let statusLabel: string;

    if (criticalCount > 0) {
        status = 'NON_COMPLIANT';
        statusEmoji = '🚨';
        statusLabel = 'Non-Compliant';
    } else if (highCount > 0 || totalActive > 0) {
        status = 'AT_RISK';
        statusEmoji = '⚠️';
        statusLabel = 'At Risk';
    } else {
        status = 'COMPLIANT';
        statusEmoji = '✅';
        statusLabel = 'Compliant';
    }

    // Find next deadline
    const nextAlert = alerts[0];

    return {
        tenant_id: tenantId,
        status,
        status_emoji: statusEmoji,
        status_label: statusLabel,
        last_status_change: new Date().toISOString(),
        active_alert_count: totalActive,
        critical_alert_count: criticalCount,
        completeness_score: 0.85,
        countdown_seconds: nextAlert?.countdown_seconds || null,
        countdown_display: nextAlert?.countdown_display || null,
        next_deadline_description: nextAlert?.title || null,
        active_alerts: alerts,
    };
}

// Mock product profiles by tenant
const MOCK_PROFILES: Record<string, any> = {
    '00000000-0000-0000-0000-000000000002': {
        tenant_id: '00000000-0000-0000-0000-000000000002',
        product_categories: ['leafy_greens', 'tomatoes', 'peppers'],
        supply_regions: ['CA', 'AZ', 'FL'],
        supplier_identifiers: ['Fresh Valley Farms', 'Green Acres'],
        fda_product_codes: ['54C21', '54E20'],
        retailer_relationships: ['Wholesale Club', 'National Retailer', 'Regional Grocer'],
    },
    '00000000-0000-0000-0000-000000000003': {
        tenant_id: '00000000-0000-0000-0000-000000000003',
        product_categories: ['leafy_greens', 'finfish', 'cheese'],
        supply_regions: ['CA', 'WA', 'TX', 'NY'],
        supplier_identifiers: ['Taylor Farms', 'Driscoll\'s', 'Fresh Express'],
        fda_product_codes: [],
        retailer_relationships: [],
    },
};

export const mockComplianceApi = {
    getStatus: async (tenantId: string) => {
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 300));
        return getMockStatus(tenantId);
    },

    getAlerts: async (tenantId: string) => {
        await new Promise(resolve => setTimeout(resolve, 200));
        return MOCK_ALERTS_BY_TENANT[tenantId] || [];
    },

    acknowledgeAlert: async (alertId: string, userId: string) => {
        await new Promise(resolve => setTimeout(resolve, 200));
        return { success: true, acknowledged_at: new Date().toISOString() };
    },

    resolveAlert: async (alertId: string, userId: string, notes: string) => {
        await new Promise(resolve => setTimeout(resolve, 200));
        return { success: true, resolved_at: new Date().toISOString() };
    },

    getProfile: async (tenantId: string) => {
        await new Promise(resolve => setTimeout(resolve, 200));
        return MOCK_PROFILES[tenantId] || {
            tenant_id: tenantId,
            product_categories: [],
            supply_regions: [],
            supplier_identifiers: [],
            fda_product_codes: [],
            retailer_relationships: [],
        };
    },

    updateProfile: async (tenantId: string, profile: any) => {
        await new Promise(resolve => setTimeout(resolve, 300));
        MOCK_PROFILES[tenantId] = { ...profile, tenant_id: tenantId };
        return MOCK_PROFILES[tenantId];
    },
};

// Helper to determine if we should use mock data
export const shouldUseMockData = () => {
    // Use mock if explicitly enabled or if running in development without backend
    if (typeof window !== 'undefined') {
        return localStorage.getItem('regengine_use_mock') === 'true' ||
            process.env.NEXT_PUBLIC_USE_MOCK === 'true';
    }
    return false;
};
