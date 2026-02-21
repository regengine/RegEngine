/**
 * FSMA 204 Key Dates
 * Based on FDA Final Rule and Congressional enforcement directives
 */
export const FSMA_204_COMPLIANCE_DATE = 'January 20, 2026';
export const FSMA_204_ENFORCEMENT_FLOOR = 'July 20, 2028';
export const FSMA_204_CITATION = '21 CFR Part 1, Subpart S';

/**
 * FSMA 204 Food Traceability List (FTL)
 * Source: FDA Food Traceability List
 */
export const FSMA_FTL_CATEGORIES = [
    { id: 'cheeses', name: 'Cheeses (other than hard cheeses)' },
    { id: 'shell_eggs', name: 'Shell Eggs' },
    { id: 'nut_butters', name: 'Nut Butters' },
    { id: 'cucumbers', name: 'Cucumbers (fresh)' },
    { id: 'herbs', name: 'Herbs (fresh)' },
    { id: 'leafy_greens', name: 'Leafy Greens (fresh)' },
    { id: 'leafy_greens_salads', name: 'Leafy Greens (fresh-cut)' },
    { id: 'melons', name: 'Melons (fresh)' },
    { id: 'peppers', name: 'Peppers (fresh)' },
    { id: 'sprouts', name: 'Sprouts (fresh)' },
    { id: 'tomatoes', name: 'Tomatoes (fresh)' },
    { id: 'tropical_fruits', name: 'Tropical Fruits (fresh-cut)' },
    { id: 'fruits_veg_other', name: 'Other Fruits and Vegetables (fresh-cut)' },
    { id: 'finfish_histamine', name: 'Finfish (histamine-producing species)' },
    { id: 'finfish_others', name: 'Finfish (other than histamine-producing species)' },
    { id: 'crustaceans', name: 'Crustaceans' },
    { id: 'molluscan_shellfish', name: 'Molluscan Shellfish' },
    { id: 'ready_to_eat_deli', name: 'Ready-to-Eat Deli Salads (refrigerated)' },
].sort((a, b) => a.name.localeCompare(b.name));

/**
 * FSMA 204 Critical Tracking Events (CTEs) and required KDEs
 * Source: FDA CTE/KDE requirements
 */
export const FSMA_CTES = {
    harvesting: {
        name: 'Harvesting',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Product Description', provide: true },
            { name: 'Quantity/UOM', provide: true },
            { name: 'Harvest Date', provide: true },
            { name: 'Location Description (Farms)', provide: true },
            { name: 'Business Name of Harvester', provide: true }
        ]
    },
    cooling: {
        name: 'Cooling',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Product Description', provide: true },
            { name: 'Quantity/UOM', provide: true },
            { name: 'Cooling Date', provide: true },
            { name: 'Location Description (Cooler)', provide: true }
        ]
    },
    initial_packing: {
        name: 'Initial Packing',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Product Description', provide: true },
            { name: 'Quantity/UOM', provide: true },
            { name: 'Date of Initial Packing', provide: true },
            { name: 'Location Description (Packer)', provide: true },
            { name: 'TLC Source Reference', provide: true }
        ]
    },
    shipping: {
        name: 'Shipping',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Product Description', provide: true },
            { name: 'Quantity/UOM', provide: true },
            { name: 'Next Recipient Location', provide: true },
            { name: 'Ship-from Location', provide: true },
            { name: 'Shipping Date', provide: true },
            { name: 'TLC Source Information', provide: true }
        ]
    },
    receiving: {
        name: 'Receiving',
        kdes: [
            { name: 'Traceability Lot Code', provide: false },
            { name: 'Product Description', provide: false },
            { name: 'Quantity/UOM', provide: false },
            { name: 'Immediate Previous Source', provide: false },
            { name: 'Receiving Location', provide: false },
            { name: 'Date of Receipt', provide: false },
            { name: 'TLC Source Information', provide: false }
        ]
    },
    transformation: {
        name: 'Transformation',
        kdes: [
            { name: 'Input Lot Codes', provide: false },
            { name: 'New Traceability Lot Code', provide: true },
            { name: 'Product Description (New)', provide: true },
            { name: 'Quantity/UOM (New)', provide: true },
            { name: 'Transformation Date', provide: false },
            { name: 'Location Description', provide: false }
        ]
    }
};
import {
    Leaf,
    ShieldCheck,
    TrendingUp,
    Shield,
    ClipboardList,
    FlaskConical,
    Truck,
    Timer,
    AlertTriangle,
    Network
} from 'lucide-react';

export const FREE_TOOLS = [
    {
        id: 'ftl-checker',
        title: 'FTL Coverage Checker',
        description: 'Verify if your food products are on the FDA Food Traceability List.',
        icon: Leaf,
        href: '/tools/ftl-checker'
    },
    {
        id: 'fsma-unified',
        title: 'Anomaly Detection Simulator',
        description: 'Test cold-chain anomaly detection and alerting.',
        icon: AlertTriangle,
        href: '/tools/fsma-unified'
    },
    {
        id: 'knowledge-graph',
        title: 'Supply Chain Knowledge Graph',
        description: 'Interactive tracing graph for FSMA networks.',
        icon: Network,
        href: '/tools/knowledge-graph'
    },
    {
        id: 'roi-calculator',
        title: 'Regulatory ROI Calculator',
        description: 'Quantify your savings from compliance automation.',
        icon: TrendingUp,
        href: '/tools/roi-calculator'
    },
    {
        id: 'exemption-qualifier',
        title: 'Exemption Qualifier',
        description: 'Check your eligibility for FSMA 204 exemptions.',
        icon: Shield,
        href: '/tools/exemption-qualifier'
    },
    {
        id: 'kde-checker',
        title: 'KDE Completeness Checker',
        description: 'Build your customized KDE checklist.',
        icon: ClipboardList,
        href: '/tools/kde-checker'
    },
    {
        id: 'tlc-validator',
        title: 'TLC Validator',
        description: 'Validate your Traceability Lot Code uniqueness.',
        icon: FlaskConical,
        href: '/tools/tlc-validator'
    },
    {
        id: 'cte-mapper',
        title: 'CTE Coverage Mapper',
        description: 'Map your supply chain data exchange nodes.',
        icon: Truck,
        href: '/tools/cte-mapper'
    },
    {
        id: 'drill-simulator',
        title: '24-Hour Drill Simulator',
        description: 'Test your record retrieval speed.',
        icon: Timer,
        href: '/tools/drill-simulator'
    }
];
