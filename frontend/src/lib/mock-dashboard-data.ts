import { getTenantById, type Tenant, type IndustrySegment } from './mock-tenants';

export interface DashboardMetrics {
    documentsIngested: number;
    complianceScore: number;
    openAlerts: number;
    pendingReviews: number;
    lastUpdated: string;
}

export interface TenantDashboard {
    tenant: Tenant;
    metrics: DashboardMetrics;
    industryIcon: string;
    industryLabel: string;
    tierBadge?: string;
}

// Seeded random for consistent per-tenant values
function seededRandom(seed: string): () => number {
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
        hash = ((hash << 5) - hash) + seed.charCodeAt(i);
        hash |= 0;
    }
    return () => {
        hash = (hash * 1103515245 + 12345) & 0x7fffffff;
        return hash / 0x7fffffff;
    };
}

// Industry icons and labels
const INDUSTRY_CONFIG: Record<IndustrySegment, { icon: string; label: string }> = {
    administration: { icon: '⚙️', label: 'System Administration' },
    grocery: { icon: '🛒', label: 'Grocery Retail' },
    produce: { icon: '🥬', label: 'Fresh Produce' },
    seafood: { icon: '🐟', label: 'Seafood' },
    meat: { icon: '🥩', label: 'Meat & Poultry' },
    dairy: { icon: '🧀', label: 'Dairy Products' },
    organic: { icon: '🌿', label: 'Organic & Natural' },
    specialty: { icon: '✨', label: 'Specialty Foods' },
};

// Base metrics by tenant type and tier
const BASE_METRICS = {
    retailer: {
        documentsBase: 500,
        complianceBase: 85,
        alertsBase: 2,
        reviewsBase: 5,
    },
    supplier: {
        documentsBase: 150,
        complianceBase: 78,
        alertsBase: 4,
        reviewsBase: 12,
    },
    system: {
        documentsBase: 0,
        complianceBase: 100,
        alertsBase: 0,
        reviewsBase: 0,
    },
};

// Tier multipliers for metrics
const TIER_MULTIPLIERS: Record<string, number> = {
    starter: 0.5,
    growth: 1.0,
    scale: 2.0,
    enterprise: 5.0,
};

const TIER_BADGES: Record<string, string | undefined> = {
    enterprise: '🏢 Enterprise',
    scale: '📈 Scale',
    growth: undefined,
    starter: undefined,
};

export function getTenantDashboard(tenantId: string): TenantDashboard | null {
    const tenant = getTenantById(tenantId);
    if (!tenant) return null;

    const random = seededRandom(tenantId);
    const base = BASE_METRICS[(tenant.type as keyof typeof BASE_METRICS) ?? 'retailer'] || BASE_METRICS.retailer;
    const multiplier = TIER_MULTIPLIERS[tenant.subscriptionTier ?? ''] || 1;
    const industryConfig = INDUSTRY_CONFIG[tenant.industry ?? 'administration'];

    // Generate consistent metrics for this tenant
    const metrics: DashboardMetrics = {
        documentsIngested: Math.floor(base.documentsBase * multiplier * (0.8 + random() * 0.4)),
        complianceScore: Math.min(100, Math.floor(base.complianceBase + (random() * 15) - 5)),
        openAlerts: Math.max(0, Math.floor(base.alertsBase * (0.5 + random()))),
        pendingReviews: Math.max(0, Math.floor(base.reviewsBase * multiplier * (0.5 + random()))),
        lastUpdated: new Date().toISOString(),
    };

    return {
        tenant,
        metrics,
        industryIcon: industryConfig.icon,
        industryLabel: industryConfig.label,
        tierBadge: tenant.subscriptionTier ? TIER_BADGES[tenant.subscriptionTier] : undefined,
    };
}

// Get quick actions based on tenant type
export function getQuickActionsForTenant(tenantId: string) {
    const tenant = getTenantById(tenantId);
    if (!tenant) return [];

    const baseActions = [
        { id: 'fsma', title: 'FSMA Dashboard', icon: 'compliance', href: '/fsma' },
        { id: 'ingest', title: 'Ingest Documents', icon: 'upload', href: '/ingest' },
        { id: 'review', title: 'Compliance Review', icon: 'review', href: '/review' },
    ];

    if (tenant.type === 'retailer') {
        return [
            ...baseActions,
            { id: 'suppliers', title: 'Supplier Network', icon: 'network', href: '/suppliers' },
            { id: 'audits', title: 'Schedule Audits', icon: 'calendar', href: '/audits' },
        ];
    }

    if (tenant.type === 'supplier') {
        return [
            ...baseActions,
            { id: 'trace', title: 'Supply Chain Trace', icon: 'trace', href: '/trace' },
            { id: 'certs', title: 'Certifications', icon: 'cert', href: '/certifications' },
        ];
    }

    // System admin
    return [
        { id: 'tenants', title: 'Manage Tenants', icon: 'users', href: '/admin/tenants' },
        { id: 'api-keys', title: 'API Keys', icon: 'key', href: '/admin/api-keys' },
        { id: 'logs', title: 'System Logs', icon: 'log', href: '/admin/logs' },
    ];
}

// Get FSMA-specific data filtered by tenant
export function getFSMADataForTenant(tenantId: string) {
    const tenant = getTenantById(tenantId);
    if (!tenant) return null;

    const random = seededRandom(tenantId + '-fsma');

    // Retailers focus on inbound traceability
    // Suppliers focus on outbound traceability
    if (tenant.type === 'retailer') {
        return {
            focusArea: 'Inbound Traceability',
            ctesTracked: Math.floor(200 + random() * 800),
            suppliersLinked: Math.floor(50 + random() * 150),
            recallReadiness: Math.floor(80 + random() * 20),
            lastRecallDrill: '2024-12-15',
        };
    }

    if (tenant.type === 'supplier') {
        return {
            focusArea: 'Outbound Traceability',
            ctesTracked: Math.floor(100 + random() * 400),
            retailersServed: Math.floor(10 + random() * 40),
            recallReadiness: Math.floor(70 + random() * 25),
            lastRecallDrill: '2024-11-20',
        };
    }

    return null;
}
