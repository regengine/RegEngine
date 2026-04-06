/**
 * FSMA 204 Target Market Demo Data
 * Real company data for demos and walkthroughs
 */

// Supply chain roles
export type SupplyChainRole = 'GROWER' | 'PROCESSOR' | 'DISTRIBUTOR' | 'RETAILER' | 'IMPORTER';
export type ProductSegment = 'LEAFY_GREENS' | 'FRESH_CUT' | 'TOMATOES' | 'PEPPERS' | 'FINFISH' | 'SHELLFISH' | 'SMOKED_FISH';

export interface TargetCompany {
    id: string;
    name: string;
    parentCompany?: string;
    headquarters: string;
    scale: 'MAJOR_NATIONAL' | 'REGIONAL_MAJOR' | 'REGIONAL' | 'EMERGING';
    role: SupplyChainRole;
    segment: ProductSegment[];
    products: string[];
    facilities?: number;
    notes?: string;
    website?: string;
}

// ============================================
// SEGMENT 1: LEAFY GREENS & FRESH PRODUCE
// ============================================

export const LEAFY_GREENS_COMPANIES: TargetCompany[] = [
    // Major National Grower-Shippers
    {
        id: 'taylor-farms',
        name: 'Taylor Farms',
        parentCompany: 'Taylor Fresh Foods',
        headquarters: 'Salinas, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['LEAFY_GREENS', 'FRESH_CUT'],
        products: ['Leafy greens', 'Salad kits', 'Fresh-cut vegetables'],
        notes: "World's largest fresh-cut produce processor",
    },
    {
        id: 'fresh-express',
        name: 'Fresh Express',
        parentCompany: 'Chiquita',
        headquarters: 'Salinas, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['LEAFY_GREENS'],
        products: ['Bagged salads', 'Spring mix', 'Salad kits'],
        notes: '~40% market share in bagged salads',
    },
    {
        id: 'dole-fresh-vegetables',
        name: 'Dole Fresh Vegetables',
        parentCompany: 'Arable Capital',
        headquarters: 'Monterey, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['LEAFY_GREENS'],
        products: ['Iceberg', 'Romaine', 'Spinach', 'Salads'],
    },
    {
        id: 'earthbound-farm',
        name: 'Earthbound Farm',
        parentCompany: 'Danone',
        headquarters: 'San Juan Bautista, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Organic baby spinach', 'Spring mix', 'Kale', 'Arugula'],
        notes: 'Largest organic produce company',
    },
    {
        id: 'tanimura-antle',
        name: 'Tanimura & Antle',
        headquarters: 'Salinas, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Iceberg', 'Romaine', 'Leaf lettuce', 'Celery', 'Artisan varieties'],
    },
    {
        id: 'fresh-del-monte',
        name: 'Fresh Del Monte Produce',
        headquarters: 'Coral Gables, FL',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FRESH_CUT'],
        products: ['Fresh-cut fruits', 'Tropical fruits', 'Melons'],
    },
    {
        id: 'lipman-family-farms',
        name: 'Lipman Family Farms',
        headquarters: 'Immokalee, FL',
        scale: 'MAJOR_NATIONAL',
        role: 'GROWER',
        segment: ['TOMATOES', 'PEPPERS'],
        products: ['Field tomatoes', 'Greenhouse tomatoes', 'Peppers', 'Cucumbers'],
        notes: 'Largest field tomato grower in US',
    },

    // Regional Grower-Shippers (Salinas Valley, CA)
    {
        id: 'church-brothers',
        name: 'Church Brothers Farms',
        headquarters: 'Salinas, CA',
        scale: 'REGIONAL_MAJOR',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Romaine', 'Leaf lettuce', 'Spinach', 'Mixed greens'],
    },
    {
        id: 'darrigo-bros',
        name: "D'Arrigo Bros. Co. of California",
        headquarters: 'Salinas, CA',
        scale: 'REGIONAL_MAJOR',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Lettuce varieties', 'Broccoli'],
        notes: 'Andy Boy brand',
    },
    {
        id: 'ocean-mist',
        name: 'Ocean Mist Farms',
        headquarters: 'Castroville, CA',
        scale: 'REGIONAL_MAJOR',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Artichokes', 'Lettuce', 'Romaine', 'Broccoli'],
    },
    {
        id: 'hitchcock-farms',
        name: 'Hitchcock Farms',
        headquarters: 'Salinas, CA',
        scale: 'REGIONAL',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Leafy greens', 'Fresh vegetables'],
    },

    // Greenhouse & Indoor Farming
    {
        id: 'cox-farms',
        name: 'Cox Farms',
        parentCompany: 'BrightFarms + Mucci',
        headquarters: 'Atlanta, GA',
        scale: 'MAJOR_NATIONAL',
        role: 'GROWER',
        segment: ['LEAFY_GREENS', 'TOMATOES', 'PEPPERS'],
        products: ['Leafy greens', 'Tomatoes', 'Cucumbers', 'Peppers'],
        facilities: 650,
        notes: '650+ acres greenhouse',
    },
    {
        id: 'little-leaf-farms',
        name: 'Little Leaf Farms',
        headquarters: 'Devens, MA',
        scale: 'EMERGING',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Baby lettuce', 'Romaine', 'Butter lettuce'],
        facilities: 40,
        notes: '40 acres greenhouse',
    },
    {
        id: 'gotham-greens',
        name: 'Gotham Greens',
        headquarters: 'Brooklyn, NY',
        scale: 'EMERGING',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Leafy greens', 'Lettuce', 'Herbs'],
        facilities: 13,
        notes: 'Hydroponic greenhouse, 13+ facilities',
    },
    {
        id: 'aerofarms',
        name: 'AeroFarms',
        headquarters: 'Newark, NJ',
        scale: 'EMERGING',
        role: 'GROWER',
        segment: ['LEAFY_GREENS'],
        products: ['Microgreens', 'Baby greens', 'Arugula'],
        notes: 'Vertical farm (aeroponic)',
    },

    // Fresh-Cut Processors
    {
        id: 'bonduelle-fresh',
        name: 'Bonduelle Fresh Americas',
        parentCompany: 'Ready Pac',
        headquarters: 'Irwindale, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FRESH_CUT'],
        products: ['Salads', 'Bistro Bowls', 'Meal kits', 'Snacking'],
        notes: '41% bowls market share',
    },
    {
        id: 'grimmway-farms',
        name: 'Grimmway Farms',
        headquarters: 'Bakersfield, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['LEAFY_GREENS', 'FRESH_CUT'],
        products: ['Organic salads', 'Organic carrots', 'Fresh-cut'],
    },

    // Major Produce Distributors
    {
        id: 'sysco-freshpoint',
        name: 'Sysco FreshPoint',
        parentCompany: 'Sysco',
        headquarters: 'Houston, TX',
        scale: 'MAJOR_NATIONAL',
        role: 'DISTRIBUTOR',
        segment: ['LEAFY_GREENS', 'FRESH_CUT'],
        products: ['Fresh produce', 'Fresh-cut', 'Leafy greens'],
        notes: "World's largest specialty produce distributor",
    },
    {
        id: 'us-foods',
        name: 'US Foods',
        headquarters: 'Rosemont, IL',
        scale: 'MAJOR_NATIONAL',
        role: 'DISTRIBUTOR',
        segment: ['LEAFY_GREENS', 'FRESH_CUT'],
        products: ['Fresh produce', 'Fresh-cut vegetables'],
    },
    {
        id: 'gordon-food-service',
        name: 'Gordon Food Service',
        headquarters: 'Grand Rapids, MI',
        scale: 'MAJOR_NATIONAL',
        role: 'DISTRIBUTOR',
        segment: ['LEAFY_GREENS', 'FRESH_CUT'],
        products: ['Fresh produce', 'Fresh-cut'],
        notes: 'Largest family-owned foodservice distributor',
    },
];

// ============================================
// SEGMENT 2: SEAFOOD PROCESSORS & IMPORTERS
// ============================================

export const SEAFOOD_COMPANIES: TargetCompany[] = [
    // Major Finfish Processors
    {
        id: 'trident-seafoods',
        name: 'Trident Seafoods Corporation',
        headquarters: 'Seattle, WA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FINFISH', 'SMOKED_FISH'],
        products: ['Fresh/frozen finfish', 'Smoked salmon'],
        notes: 'Largest US seafood company',
    },
    {
        id: 'pacific-seafood',
        name: 'Pacific Seafood Group',
        headquarters: 'Clackamas, OR',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FINFISH', 'SHELLFISH'],
        products: ['Fresh/frozen finfish', 'Oysters', 'Salmon'],
        facilities: 41,
    },
    {
        id: 'american-seafoods',
        name: 'American Seafoods Group',
        headquarters: 'Seattle, WA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FINFISH'],
        products: ['Frozen Wild Alaska Pollock', 'Pacific Hake'],
        notes: 'At-sea processor',
    },
    {
        id: 'high-liner-foods',
        name: 'High Liner Foods',
        headquarters: 'Portsmouth, NH',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FINFISH'],
        products: ['Frozen finfish', 'Breaded', 'Value-added'],
    },
    {
        id: 'ocean-beauty',
        name: 'Ocean Beauty Seafoods',
        headquarters: 'Seattle, WA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FINFISH', 'SMOKED_FISH'],
        products: ['Fresh/frozen finfish', 'Smoked salmon'],
        notes: 'Echo Falls brand',
    },
    {
        id: 'gortons-seafood',
        name: "Gorton's Seafood",
        headquarters: 'Gloucester, MA',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['FINFISH'],
        products: ['Frozen finfish', 'Breaded products'],
    },

    // Smoked Fish Processors
    {
        id: 'acme-smoked-fish',
        name: 'Acme Smoked Fish Corp.',
        headquarters: 'Brooklyn, NY',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['SMOKED_FISH'],
        products: ['Smoked salmon', 'Lox', 'Smoked trout', 'Whitefish'],
        notes: 'Largest smoked fish processor in North America',
    },
    {
        id: 'ducktrap-river',
        name: 'Ducktrap River of Maine',
        parentCompany: 'Mowi',
        headquarters: 'Belfast, ME',
        scale: 'MAJOR_NATIONAL',
        role: 'PROCESSOR',
        segment: ['SMOKED_FISH'],
        products: ['Cold/hot-smoked salmon', 'Trout', 'Mackerel'],
    },

    // Molluscan Shellfish
    {
        id: 'ipswich-shellfish',
        name: 'Ipswich Shellfish Group',
        headquarters: 'Ipswich, MA',
        scale: 'REGIONAL_MAJOR',
        role: 'PROCESSOR',
        segment: ['SHELLFISH'],
        products: ['Oysters', 'Clams', 'Mussels'],
        facilities: 7,
    },
    {
        id: 'prestige-oysters',
        name: 'Prestige Oysters',
        headquarters: 'Houston, TX',
        scale: 'REGIONAL_MAJOR',
        role: 'PROCESSOR',
        segment: ['SHELLFISH'],
        products: ['Oysters (fresh, shucked, HPP, frozen)'],
        notes: 'Gulf Coast focus',
    },
    {
        id: 'hog-island-oyster',
        name: 'Hog Island Oyster Company',
        headquarters: 'Marshall, CA',
        scale: 'REGIONAL',
        role: 'GROWER',
        segment: ['SHELLFISH'],
        products: ['Oysters', 'Clams'],
        notes: 'West Coast premium oysters',
    },

    // Major Seafood Importers
    {
        id: 'mowi-usa',
        name: 'Mowi USA',
        parentCompany: 'Mowi (formerly Marine Harvest)',
        headquarters: 'Multi-location',
        scale: 'MAJOR_NATIONAL',
        role: 'IMPORTER',
        segment: ['FINFISH', 'SMOKED_FISH'],
        products: ['Atlantic salmon', 'Smoked salmon'],
        notes: '25-30% global salmon market',
    },
    {
        id: 'cooke-seafood',
        name: 'Cooke Seafood USA',
        parentCompany: 'Cooke Aquaculture',
        headquarters: 'US (various)',
        scale: 'MAJOR_NATIONAL',
        role: 'IMPORTER',
        segment: ['FINFISH'],
        products: ['Farmed salmon', 'Wild salmon', 'Whitefish'],
    },
    {
        id: 'chicken-of-the-sea',
        name: 'Chicken of the Sea',
        parentCompany: 'Thai Union',
        headquarters: 'San Diego, CA',
        scale: 'MAJOR_NATIONAL',
        role: 'IMPORTER',
        segment: ['FINFISH'],
        products: ['Frozen finfish', 'Specialty seafood'],
    },
    {
        id: 'beaver-street-fisheries',
        name: 'Beaver Street Fisheries',
        headquarters: 'Jacksonville, FL',
        scale: 'MAJOR_NATIONAL',
        role: 'IMPORTER',
        segment: ['FINFISH'],
        products: ['Tilapia', 'Frozen seafood'],
    },

    // Regional Seafood Distributors
    {
        id: 'inland-seafood',
        name: 'Inland Seafood',
        headquarters: 'Atlanta, GA',
        scale: 'REGIONAL',
        role: 'DISTRIBUTOR',
        segment: ['FINFISH', 'SHELLFISH', 'SMOKED_FISH'],
        products: ['Fresh/frozen/smoked finfish', 'Shellfish'],
        notes: 'Southeast focus',
    },
    {
        id: 'santa-monica-seafood',
        name: 'Santa Monica Seafood',
        headquarters: 'Compton, CA',
        scale: 'REGIONAL',
        role: 'DISTRIBUTOR',
        segment: ['FINFISH', 'SHELLFISH'],
        products: ['Fresh/frozen finfish', 'Shellfish'],
        notes: 'Southwest focus',
    },
    {
        id: 'north-coast-seafoods',
        name: 'North Coast Seafoods',
        headquarters: 'Boston, MA',
        scale: 'REGIONAL',
        role: 'DISTRIBUTOR',
        segment: ['FINFISH', 'SHELLFISH'],
        products: ['Fresh/frozen finfish', 'Shellfish'],
        notes: 'East Coast focus',
    },
];

// ============================================
// DEMO SAMPLE DATA
// ============================================

export interface DemoFacility {
    gln: string;
    name: string;
    company: string;
    type: 'FARM' | 'PROCESSOR' | 'DISTRIBUTOR' | 'RETAILER' | 'IMPORTER';
    location: string;
    products: string[];
}

export interface DemoLot {
    tlc: string;
    product: string;
    quantity: number;
    unit: string;
    harvestDate: string;
    originFacility: string;
    currentFacility: string;
}

export interface DemoTraceEvent {
    id: string;
    tlc: string;
    eventType: 'HARVESTING' | 'COOLING' | 'INITIAL_PACKING' | 'FIRST_LAND_BASED_RECEIVING' | 'SHIPPING' | 'RECEIVING' | 'TRANSFORMATION';
    facilityGln: string;
    timestamp: string;
    kdes: Record<string, string>;
}

// Sample facilities using real company names
export const DEMO_FACILITIES: DemoFacility[] = [
    {
        gln: '0614141000012',
        name: 'Taylor Farms - Salinas Facility',
        company: 'Taylor Farms',
        type: 'PROCESSOR',
        location: 'Salinas, CA',
        products: ['Romaine Hearts', 'Spring Mix', 'Caesar Salad Kit'],
    },
    {
        gln: '0614141000029',
        name: 'Earthbound Farm - San Juan Bautista',
        company: 'Earthbound Farm',
        type: 'FARM',
        location: 'San Juan Bautista, CA',
        products: ['Organic Baby Spinach', 'Organic Spring Mix'],
    },
    {
        gln: '0614141000036',
        name: 'Sysco FreshPoint - Houston DC',
        company: 'Sysco FreshPoint',
        type: 'DISTRIBUTOR',
        location: 'Houston, TX',
        products: ['Mixed Produce', 'Fresh-Cut', 'Leafy Greens'],
    },
    {
        gln: '0614141000043',
        name: 'Trident Seafoods - Seattle Processing',
        company: 'Trident Seafoods',
        type: 'PROCESSOR',
        location: 'Seattle, WA',
        products: ['Wild Alaska Salmon', 'Pollock', 'Smoked Salmon'],
    },
    {
        gln: '0614141000050',
        name: 'Pacific Seafood - Clackamas Plant',
        company: 'Pacific Seafood Group',
        type: 'PROCESSOR',
        location: 'Clackamas, OR',
        products: ['Fresh Salmon', 'Oysters', 'Dungeness Crab'],
    },
    {
        gln: '0614141000067',
        name: 'Acme Smoked Fish - Brooklyn',
        company: 'Acme Smoked Fish Corp.',
        type: 'PROCESSOR',
        location: 'Brooklyn, NY',
        products: ['Nova Scotia Lox', 'Scottish Smoked Salmon', 'Smoked Trout'],
    },
    {
        gln: '0614141000074',
        name: "Hog Island Oyster - Marshall Farm",
        company: 'Hog Island Oyster Company',
        type: 'FARM',
        location: 'Marshall, CA',
        products: ['Sweetwater Oysters', 'Atlantic Oysters', 'Manila Clams'],
    },
    {
        gln: '0614141000081',
        name: 'Fresh Express - Salinas Salad Plant',
        company: 'Fresh Express',
        type: 'PROCESSOR',
        location: 'Salinas, CA',
        products: ['Bagged Salads', 'Chopped Salad Kits', 'Organic Blends'],
    },
];

// Sample lot codes for demo tracing
export const DEMO_LOTS: DemoLot[] = [
    {
        tlc: 'TF-ROM-2026-001',
        product: 'Romaine Hearts',
        quantity: 5000,
        unit: 'cases',
        harvestDate: '2026-01-10',
        originFacility: '0614141000029',
        currentFacility: '0614141000012',
    },
    {
        tlc: 'EB-SPM-2026-042',
        product: 'Organic Baby Spinach',
        quantity: 2500,
        unit: 'cases',
        harvestDate: '2026-01-12',
        originFacility: '0614141000029',
        currentFacility: '0614141000036',
    },
    {
        tlc: 'TS-SAL-2026-015',
        product: 'Wild Alaska Sockeye Salmon',
        quantity: 1200,
        unit: 'lbs',
        harvestDate: '2026-01-08',
        originFacility: '0614141000043',
        currentFacility: '0614141000043',
    },
    {
        tlc: 'AC-LOX-2026-088',
        product: 'Nova Scotia Lox',
        quantity: 500,
        unit: 'lbs',
        harvestDate: '2026-01-14',
        originFacility: '0614141000067',
        currentFacility: '0614141000067',
    },
    {
        tlc: 'HI-OYS-2026-023',
        product: 'Sweetwater Oysters',
        quantity: 3000,
        unit: 'dozen',
        harvestDate: '2026-01-15',
        originFacility: '0614141000074',
        currentFacility: '0614141000074',
    },
];

// All target companies combined
export const ALL_TARGET_COMPANIES = [...LEAFY_GREENS_COMPANIES, ...SEAFOOD_COMPANIES];

// Helper functions
export function getCompanyById(id: string): TargetCompany | undefined {
    return ALL_TARGET_COMPANIES.find(c => c.id === id);
}

export function getCompaniesBySegment(segment: ProductSegment): TargetCompany[] {
    return ALL_TARGET_COMPANIES.filter(c => c.segment.includes(segment));
}

export function getCompaniesByRole(role: SupplyChainRole): TargetCompany[] {
    return ALL_TARGET_COMPANIES.filter(c => c.role === role);
}

export function getCompaniesByScale(scale: TargetCompany['scale']): TargetCompany[] {
    return ALL_TARGET_COMPANIES.filter(c => c.scale === scale);
}
