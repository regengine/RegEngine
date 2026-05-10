/**
 * FSMA 204 Key Dates
 * Based on FDA Final Rule and Congressional enforcement directives
 * Original compliance date was January 20, 2026. Congress directed
 * FDA not to enforce before July 20, 2028.
 */
export const FSMA_204_ORIGINAL_DATE = 'January 20, 2026';
export const FSMA_204_COMPLIANCE_DATE = 'July 20, 2028';
export const FSMA_204_ENFORCEMENT_FLOOR = 'July 20, 2028';
export const FSMA_204_DEADLINE_ISO = '2028-07-20';
export const FSMA_204_CITATION = '21 CFR Part 1, Subpart S';

/** Days remaining until the compliance deadline */
export function daysUntilFSMA204(): number {
    const now = new Date();
    const deadline = new Date(FSMA_204_DEADLINE_ISO);
    return Math.max(0, Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

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
 * FSMA 204 Critical Tracking Events (CTEs) and KDE checklists.
 *
 * IMPORTANT: This is a STARTING CHECKLIST. The authoritative source is
 * 21 CFR Part 1 Subpart S (§§1.1325–1.1350). Do not present these lists
 * as "the" required KDEs without verifying against the rule for your
 * specific operation.
 *
 * The `provide` flag previously indicated "must be provided to FDA on
 * request" vs "maintain only" — that split does not match the rule
 * (§1.1455(c) requires production of a sortable spreadsheet of required
 * records). It is preserved here for layout compatibility but should be
 * treated as informational; renderers should not present it as an
 * authoritative obligation.
 *
 * §1.1325 covers Harvesting AND Cooling in a single section (no
 * subparts). For seafood received from a fishing vessel, see
 * `first_land_based_receiving` (§1.1335) — non-seafood importers
 * perform §1.1345 Receiving, not FLBR.
 */
export const FSMA_CTES = {
    harvesting: {
        name: 'Harvesting',
        cfr: '21 CFR §1.1325',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Commodity and variety', provide: true },
            { name: 'Quantity / Unit of Measure', provide: true },
            { name: 'Date of harvesting', provide: true },
            { name: 'Location description for the immediate subsequent recipient', provide: true },
            { name: 'Location of the field or growing area', provide: true },
            { name: 'Business name of the harvester', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
        ]
    },
    cooling: {
        name: 'Cooling',
        cfr: '21 CFR §1.1325 (combined with Harvesting)',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Commodity and variety', provide: true },
            { name: 'Quantity / Unit of Measure', provide: true },
            { name: 'Date of cooling', provide: true },
            { name: 'Location description for where the food was cooled', provide: true },
            { name: 'Location description for the immediate subsequent recipient', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
        ]
    },
    initial_packing: {
        name: 'Initial Packing (RAC, other than from a fishing vessel)',
        cfr: '21 CFR §1.1330',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Commodity and variety', provide: true },
            { name: 'Quantity / Unit of Measure', provide: true },
            { name: 'Date of initial packing', provide: true },
            { name: 'Location description of the initial packer', provide: true },
            { name: 'Location description for the TLC source (farm, growing area, or container)', provide: true },
            { name: 'TLC source reference', provide: true },
            { name: 'Harvest date range of the lot', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
        ]
    },
    first_land_based_receiving: {
        name: 'First Land-Based Receiving (food obtained from a fishing vessel)',
        cfr: '21 CFR §1.1335',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Species / commodity', provide: true },
            { name: 'Harvest date range', provide: true },
            { name: 'Location description for the harvest area (NMFS area or equivalent)', provide: true },
            { name: 'Quantity / Unit of Measure', provide: true },
            { name: 'Name and address of the harvest vessel', provide: true },
            { name: 'Date of landing', provide: true },
            { name: 'Location description of the first land-based receiver', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
        ]
    },
    shipping: {
        name: 'Shipping',
        cfr: '21 CFR §1.1340',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Quantity / Unit of Measure', provide: true },
            { name: 'Product description', provide: true },
            { name: 'Location description for the immediate subsequent recipient (other than a transporter)', provide: true },
            { name: 'Location description for where the food was shipped from', provide: true },
            { name: 'Date of shipment', provide: true },
            { name: 'Location description for the TLC source', provide: true },
            { name: 'TLC source reference', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
        ]
    },
    receiving: {
        name: 'Receiving (subject to §1.1305(j) restaurant/RFE exemption)',
        cfr: '21 CFR §1.1345',
        kdes: [
            { name: 'Traceability Lot Code', provide: true },
            { name: 'Quantity / Unit of Measure', provide: true },
            { name: 'Product description', provide: true },
            { name: 'Location description for the immediate previous source (other than a transporter)', provide: true },
            { name: 'Location description for where the food was received', provide: true },
            { name: 'Date of receipt', provide: true },
            { name: 'Location description for the TLC source', provide: true },
            { name: 'TLC source reference', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
        ]
    },
    transformation: {
        name: 'Transformation',
        cfr: '21 CFR §1.1350',
        kdes: [
            { name: 'New Traceability Lot Code (output)', provide: true },
            { name: 'Input TLCs and TLC sources', provide: true },
            { name: 'New product description', provide: true },
            { name: 'Quantity / Unit of Measure of the new product', provide: true },
            { name: 'Location description where transformation occurred', provide: true },
            { name: 'Date of transformation', provide: true },
            { name: 'Reference Document Type and Number', provide: true }
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
    Network,
    CheckCircle2,
    ScanBarcode,
    MessageSquareText,
    FileOutput,
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
        title: 'Automated Cold Chain Monitor',
        description: 'Detect temperature excursions and supply chain anomalies.',
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
        id: 'readiness-assessment',
        title: 'FSMA 204 Readiness Assessment',
        description: 'Score your compliance readiness across products, CTEs, KDEs, and systems.',
        icon: CheckCircle2,
        href: '/tools/readiness-assessment'
    },
    {
        id: 'roi-calculator',
        title: 'Regulatory ROI Calculator',
        description: 'Quantify your savings from compliance automation.',
        icon: TrendingUp,
        href: '/tools/roi-calculator'
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
    },
    {
        id: 'recall-readiness',
        title: 'Recall Readiness Score',
        description: 'Get an A-F grade on your 24-hour records retrieval mandate.',
        icon: ShieldCheck,
        href: '/tools/recall-readiness'
    },
    {
        id: 'scan',
        title: 'GS1 Barcode Scanner',
        description: 'Scan a GS1 barcode with your camera. Auto-fill CTE fields. Ingest in one tap.',
        icon: ScanBarcode,
        href: '/tools/scan'
    },
    {
        id: 'ask',
        title: 'Traceability Query Engine',
        description: 'Ask questions about your supply chain in plain English. No SQL required.',
        icon: MessageSquareText,
        href: '/tools/ask'
    },
    {
        id: 'export',
        title: 'FDA Export Package Generator',
        description: 'Generate a verifiable 21 CFR 1.1455 compliance package with SHA-256 chain verification.',
        icon: FileOutput,
        href: '/tools/export'
    }
];
