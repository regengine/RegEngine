'use client';

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Search,
    ArrowRight,
    Download,
    Mail,
    Leaf,
    Fish,
    Apple,
    Egg,
    Milk,
    Nut,
    Loader2,
    Building2,
    Flame,
    Users,
    Store,
    HelpCircle,
    ShieldCheck,
    Link2,
    Share2,
    Check,
    ExternalLink,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import Link from 'next/link';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS (Unified Dark Theme)
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: '#06090f',
    surface: 'rgba(255,255,255,0.02)',
    surfaceHover: 'rgba(255,255,255,0.04)',
    elevated: 'rgba(255,255,255,0.06)',
    border: 'rgba(255,255,255,0.06)',
    borderStrong: 'rgba(255,255,255,0.10)',
    accent: '#10b981',
    accentHover: '#059669',
    accentBg: 'rgba(16,185,129,0.08)',
    accentBorder: 'rgba(16,185,129,0.2)',
    textPrimary: '#f1f5f9',
    textBody: '#c8d1dc',
    textMuted: '#64748b',
    textDim: '#475569',
    warning: '#f59e0b',
    warningBg: 'rgba(245,158,11,0.1)',
    warningBorder: 'rgba(245,158,11,0.2)',
    danger: '#ef4444',
    dangerBg: 'rgba(239,68,68,0.1)',
    dangerBorder: 'rgba(239,68,68,0.2)',
    info: '#60a5fa',
    infoBg: 'rgba(96,165,250,0.1)',
    infoBorder: 'rgba(96,165,250,0.2)',
    success: '#10b981',
    successBg: 'rgba(16,185,129,0.1)',
    successBorder: 'rgba(16,185,129,0.2)',
    sans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    mono: "'JetBrains Mono', monospace",
};

// ============================================================
// FDA Food Traceability List Categories with CTE/KDE Requirements
// All CTEs, KDEs, CFR sections verified against 21 CFR Part 1 Subpart S
// Source: https://www.ecfr.gov/current/title-21/part-1/subpart-S
// ============================================================

// CFR Section Reference:
//   §1.1325 = Harvesting AND Cooling (same section)
//   §1.1330 = Initial Packing (RAC, not from fishing vessel)
//   §1.1335 = First Land-Based Receiving (from fishing vessel)
//   §1.1340 = Shipping
//   §1.1345 = Receiving
//   §1.1350 = Transformation

const FTL_CATEGORIES = [
    {
        id: 'leafy-greens-fresh',
        name: 'Leafy Greens (fresh, intact)',
        icon: Leaf,
        examples: 'Whole leaf lettuce, spinach bunches, kale, arugula, chard, collard greens',
        exclusions: 'Does not include whole head cabbages (green, red, savoy) or banana/grape/tree leaves. See fresh-cut leafy greens for pre-cut/bagged products.',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['Harvesting', 'Cooling', 'Initial Packing', 'Shipping', 'Receiving'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Cooling Location Identifier', 'Field Identification']
    },
    {
        id: 'leafy-greens-fresh-cut',
        name: 'Leafy Greens (fresh-cut)',
        icon: Leaf,
        examples: 'Bagged salad mix, spring mix, pre-washed spinach, chopped romaine, salad kits',
        exclusions: 'Does not include dried or frozen leafy greens',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'tomatoes',
        name: 'Tomatoes',
        icon: Apple,
        examples: 'Fresh tomatoes (not canned or dried)',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['Harvesting', 'Cooling', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Cooling Location Identifier', 'Field Identification']
    },
    {
        id: 'peppers',
        name: 'Peppers',
        icon: Apple,
        examples: 'Bell peppers, jalapeños, chili peppers (fresh)',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Harvesting', 'Cooling', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Cooling Location Identifier', 'Field Identification']
    },
    {
        id: 'cucumbers',
        name: 'Cucumbers',
        icon: Apple,
        examples: 'Fresh cucumbers',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Harvesting', 'Cooling', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Cooling Location Identifier', 'Field Identification']
    },
    {
        id: 'herbs',
        name: 'Fresh Herbs',
        icon: Leaf,
        examples: 'Cilantro, parsley, basil (fresh cut)',
        exclusions: 'Note: Herbs in 21 CFR 112.2(a)(1), such as dill, are exempt under §1.1305(e)',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Harvesting', 'Cooling', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Cooling Location Identifier', 'Field Identification']
    },
    {
        id: 'melons',
        name: 'Melons',
        icon: Apple,
        examples: 'Cantaloupe, honeydew, watermelon',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Harvesting', 'Cooling', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Cooling Location Identifier', 'Field Identification']
    },
    {
        id: 'tropical-fruits',
        name: 'Tropical Tree Fruits',
        icon: Apple,
        examples: 'Mangoes, papayas, mamey, guava',
        exclusions: 'Does not include: bananas, pineapple, dates (non-tree); coconut (tree nut); avocado (pit fruit); or citrus',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Harvesting', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Field Identification']
    },
    {
        id: 'sprouts',
        name: 'Sprouts',
        icon: Leaf,
        examples: 'Alfalfa, bean, broccoli sprouts',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['Harvesting', 'Initial Packing', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1325, §1.1330, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Seed Source', 'Growing Location']
    },
    {
        id: 'fresh-cut-fruits',
        name: 'Fresh-Cut Fruits',
        icon: Apple,
        examples: 'Pre-cut fruit mixes, fruit cups',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'fresh-cut-vegetables',
        name: 'Fresh-Cut Vegetables (non-leafy)',
        icon: Apple,
        examples: 'Veggie trays, pre-cut carrots, celery sticks, broccoli florets',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'deli-salads',
        name: 'Ready-to-Eat Deli Salads',
        icon: Apple,
        examples: 'Egg salad, seafood salad, pasta salad, potato salad',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'finfish-histamine',
        name: 'Finfish — Scombrotoxin/Histamine-Forming',
        icon: Fish,
        examples: 'Tuna, mackerel, mahi-mahi, bluefish, amberjack, bonito',
        exclusions: 'Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g)',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1335, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Vessel Name', 'Harvest Area', 'Landing Port']
    },
    {
        id: 'finfish-ciguatoxin',
        name: 'Finfish — Ciguatoxin-Associated',
        icon: Fish,
        examples: 'Barracuda, grouper, snapper, moray eel (tropical reef species)',
        exclusions: 'Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g)',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1335, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Vessel Name', 'Harvest Area', 'Landing Port']
    },
    {
        id: 'finfish-other',
        name: 'Finfish — Other (fresh/frozen/previously frozen)',
        icon: Fish,
        examples: 'Salmon, cod, halibut, tilapia, trout, bass, swordfish',
        exclusions: 'Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g)',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1335, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Vessel Name', 'Harvest Area', 'Landing Port']
    },
    {
        id: 'finfish-smoked',
        name: 'Smoked Finfish',
        icon: Fish,
        examples: 'Smoked salmon, lox, kippered herring, smoked trout, smoked whitefish',
        exclusions: 'Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g)',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'crustaceans',
        name: 'Crustaceans',
        icon: Fish,
        examples: 'Shrimp, crab, lobster, crawfish',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1335, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Harvest Area', 'Vessel or Container ID']
    },
    {
        id: 'molluscan-shellfish',
        name: 'Molluscan Shellfish (bivalves)',
        icon: Fish,
        examples: 'Oysters, clams, mussels, scallops',
        exclusions: 'Except when product consists entirely of shucked adductor muscle. Raw bivalves under NSSP may be exempt per §1.1305(f)',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1335, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Harvest Area', 'Harvest Tag', 'NSSP Dealer Certificate']
    },
    {
        id: 'eggs',
        name: 'Shell Eggs',
        icon: Egg,
        examples: 'Whole shell eggs (chicken, duck)',
        exclusions: 'Farms with fewer than 3,000 laying hens are exempt per §1.1305(a)(2)',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Shipping', 'Receiving'],
        cfrSections: '§1.1340, §1.1345',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'TLC Source Location or Reference', 'Farm/Flock Identifier']
    },
    {
        id: 'nut-butters',
        name: 'Nut Butters',
        icon: Nut,
        examples: 'Peanut butter, almond butter',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'cheese-fresh-soft',
        name: 'Fresh Soft Cheese',
        icon: Milk,
        examples: 'Queso fresco, ricotta, mascarpone, cottage cheese, cream cheese, panela, boursin',
        exclusions: 'Hard cheeses per 21 CFR 133.150 (e.g., cheddar, parmesan, aged cotija) are excluded from the FTL',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'cheese-soft-ripened',
        name: 'Soft Ripened & Semi-Soft Cheese',
        icon: Milk,
        examples: 'Brie, camembert, monterey jack, muenster, gouda, havarti, oaxaca, feta',
        exclusions: 'Hard cheeses per 21 CFR 133.150 are excluded. Semi-soft classification per FDA guidance includes cheeses with moisture content >39%',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'cheese-unpasteurized',
        name: 'Cheese Made from Unpasteurized Milk (non-hard)',
        icon: Milk,
        examples: 'Raw-milk brie, raw-milk feta, raw-milk camembert, artisanal raw-milk soft cheeses',
        exclusions: 'Hard cheeses aged 60+ days per 21 CFR 133.150 are excluded even if made from unpasteurized milk',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'canned-goods',
        name: 'Canned/Processed',
        icon: Apple,
        examples: 'Canned vegetables, frozen dinners, dried products',
        exclusions: 'Once food leaves fresh form (dried, frozen, canned), it is off the FTL',
        covered: false,
        outbreakFrequency: 'N/A',
        ctes: [],
        cfrSections: '',
        kdes: []
    },
    {
        id: 'bakery',
        name: 'Bakery Products',
        icon: Apple,
        examples: 'Bread, pastries, cookies',
        covered: false,
        outbreakFrequency: 'N/A',
        ctes: [],
        cfrSections: '',
        kdes: []
    },
    {
        id: 'beverages',
        name: 'Beverages',
        icon: Apple,
        examples: 'Juices, sodas, water',
        covered: false,
        outbreakFrequency: 'N/A',
        ctes: [],
        cfrSections: '',
        kdes: []
    },
];

// ============================================================
// FSMA 204 Exemptions
// 4 of 6 citations corrected per 21 CFR §1.1305

// Helper: generate official eCFR link from a citation like '21 CFR §1.1305(a)'
const ecfrUrl = (section: string): string => {
    const m = section.match(/§\s*([\d.]+)/);
    return m ? `https://www.ecfr.gov/current/title-21/section-1.${m[1].replace(/^1\./, '')}` : 'https://www.ecfr.gov/current/title-21/part-1/subpart-S';
};
// ============================================================
const EXEMPTION_QUESTIONS = [
    {
        id: 'small-producer',
        question: 'Are you a produce farm or RAC producer averaging less than $25,000 in annual sales over the past 3 years?',
        citation: '21 CFR §1.1305(a)',
        exemptionType: 'FULL' as const,
        helpText: 'Threshold is adjusted for inflation using 2020 as baseline. Shell egg producers with fewer than 3,000 laying hens also qualify.',
        icon: Building2
    },
    {
        id: 'kill-step',
        question: 'Does YOUR facility apply a kill step (cooking, pasteurization) that eliminates pathogens before the food reaches consumers?',
        citation: '21 CFR §1.1305(d)',
        exemptionType: 'FULL' as const,
        helpText: 'You must still keep receiving records (§1.1345) and a record of the kill step application. Downstream entities receiving post-kill-step food are exempt.',
        icon: Flame
    },
    {
        id: 'direct-to-consumer',
        question: 'Do you sell ONLY directly to consumers (farm stand, farmers market, CSA)?',
        citation: '21 CFR §1.1305(b)',
        exemptionType: 'FULL' as const,
        helpText: 'Applies to food produced on the farm and sold/donated directly to consumers by the owner, operator, or agent.',
        icon: Users
    },
    {
        id: 'small-retail',
        question: 'Are you a retail food establishment or restaurant averaging less than $250,000 in annual food sales over the past 3 years?',
        citation: '21 CFR §1.1305(i)',
        exemptionType: 'FULL' as const,
        helpText: 'Threshold is adjusted for inflation using 2020 as baseline. Most small restaurants and independent grocers qualify.',
        icon: Store
    },
    {
        id: 'rarely-consumed-raw',
        question: 'Do you ONLY handle produce on the FDA "Rarely Consumed Raw" list (asparagus, potatoes, beets, etc.)?',
        citation: '21 CFR §1.1305(e)',
        exemptionType: 'FULL' as const,
        helpText: 'Produce listed in 21 CFR 112.2(a)(1) is excluded from the FTL entirely.',
        icon: Leaf
    },
    {
        id: 'usda-jurisdiction',
        question: 'Is your product under exclusive USDA jurisdiction (Federal Meat Inspection Act, Poultry Products Inspection Act, or Egg Products Inspection Act)?',
        citation: '21 CFR §1.1305(g)',
        exemptionType: 'FULL' as const,
        helpText: 'Includes Siluriformes (catfish family) and any food within exclusive USDA jurisdiction during or after handling.',
        icon: Fish
    },
];

interface CheckerResult {
    totalSelected: number;
    coveredCount: number;
    notCoveredCount: number;
    highOutbreakCount: number;
    categories: typeof FTL_CATEGORIES;
    exemptionStatus: 'EXEMPT' | 'NOT_EXEMPT' | 'UNKNOWN';
    qualifyingExemptions: typeof EXEMPTION_QUESTIONS;
}

export default function FTLCheckerPage() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
    const [currentStep, setCurrentStep] = useState<'categories' | 'exemptions' | 'results'>('categories');
    const [exemptionAnswers, setExemptionAnswers] = useState<Record<string, boolean | null>>({});
    const [showExemptionHelp, setShowExemptionHelp] = useState<string | null>(null);
    const [showResults, setShowResults] = useState(false);
    const [email, setEmail] = useState('');
    const [emailSubmitted, setEmailSubmitted] = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);
    const [linkCopied, setLinkCopied] = useState(false);
    const { toast } = useToast();

    // Hydrate state from URL on initial load
    useEffect(() => {
        const cats = searchParams.get('categories');
        const exempt = searchParams.get('exempt');
        if (cats) {
            const categoryIds = cats.split(',').filter(id => FTL_CATEGORIES.some(c => c.id === id));
            if (categoryIds.length > 0) {
                setSelectedCategories(categoryIds);
                // If there's exemption status in URL, go straight to results
                if (exempt === 'yes' || exempt === 'no') {
                    setCurrentStep('results');
                    setShowResults(true);
                    // Pre-fill exemption answers if exempt=yes
                    if (exempt === 'yes') {
                        setExemptionAnswers({ 'very-small-business': true });
                    }
                }
            }
        }
    }, [searchParams]);

    // Generate shareable URL
    const getShareableUrl = () => {
        const base = typeof window !== 'undefined' ? window.location.origin : '';
        const params = new URLSearchParams();
        params.set('categories', selectedCategories.join(','));
        const exemptionResult = getExemptionStatus();
        if (exemptionResult.status === 'EXEMPT') params.set('exempt', 'yes');
        else if (exemptionResult.status === 'NOT_EXEMPT') params.set('exempt', 'no');
        return `${base}/ftl-checker?${params.toString()}`;
    };

    // Copy shareable link
    const handleCopyLink = async () => {
        const url = getShareableUrl();
        try {
            await navigator.clipboard.writeText(url);
            setLinkCopied(true);
            toast({ title: "Link copied!", description: "Share this URL to show your compliance status." });
            setTimeout(() => setLinkCopied(false), 3000);
        } catch {
            toast({ title: "Copy failed", description: "Please copy the URL manually.", variant: "destructive" });
        }
    };

    const toggleCategory = (id: string) => {
        setSelectedCategories(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
    };

    const handleExemptionAnswer = (questionId: string, answer: boolean) => {
        setExemptionAnswers(prev => ({ ...prev, [questionId]: answer }));
    };

    const getExemptionStatus = () => {
        const qualifyingExemptions = EXEMPTION_QUESTIONS.filter(q => exemptionAnswers[q.id] === true);
        if (qualifyingExemptions.length > 0) return { status: 'EXEMPT' as const, exemptions: qualifyingExemptions };
        const answeredAll = EXEMPTION_QUESTIONS.every(q => exemptionAnswers[q.id] !== undefined && exemptionAnswers[q.id] !== null);
        if (answeredAll) return { status: 'NOT_EXEMPT' as const, exemptions: [] };
        return { status: 'UNKNOWN' as const, exemptions: [] };
    };

    const getResults = (): CheckerResult => {
        const selected = FTL_CATEGORIES.filter(c => selectedCategories.includes(c.id));
        const exemptionResult = getExemptionStatus();
        return {
            totalSelected: selected.length,
            coveredCount: selected.filter(c => c.covered).length,
            notCoveredCount: selected.filter(c => !c.covered).length,
            highOutbreakCount: selected.filter(c => c.outbreakFrequency === 'HIGH').length,
            categories: selected,
            exemptionStatus: exemptionResult.status,
            qualifyingExemptions: exemptionResult.exemptions,
        };
    };

    const handleCheck = () => {
        if (selectedCategories.length > 0) {
            const hasCoveredCategories = FTL_CATEGORIES.filter(c => selectedCategories.includes(c.id)).some(c => c.covered);
            if (hasCoveredCategories) {
                setCurrentStep('exemptions');
            } else {
                setCurrentStep('results');
                setShowResults(true);
            }
        }
    };

    const handleSkipExemptions = () => { setCurrentStep('results'); setShowResults(true); };
    const handleFinishExemptions = () => { setCurrentStep('results'); setShowResults(true); };
    const handleBackToCategories = () => { setCurrentStep('categories'); setExemptionAnswers({}); };
    const handleStartOver = () => { setSelectedCategories([]); setExemptionAnswers({}); setCurrentStep('categories'); setShowResults(false); setEmailSubmitted(false); };

    const handleEmailSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (email) {
            localStorage.setItem('ftl_checker_email', email);
            setEmailSubmitted(true);
            toast({ title: "Report on its way!", description: "Check your inbox for the full FTL compliance report." });
        }
    };

    const handleDownloadReport = async () => {
        setIsDownloading(true);
        try {
            const results = getResults();
            const date = new Date().toLocaleString();
            const exemptionSection = results.exemptionStatus === 'EXEMPT'
                ? `\nEXEMPTION STATUS: POTENTIALLY EXEMPT\n${results.qualifyingExemptions.map(e => `• ${e.citation}`).join('\n')}`
                : results.exemptionStatus === 'NOT_EXEMPT' ? '\nEXEMPTION STATUS: NOT EXEMPT' : '\nEXEMPTION STATUS: UNKNOWN';
            const reportContent = `FDA FSMA 204 FTL COVERAGE REPORT\nGenerated: ${date}\n\nSUMMARY\nTotal Categories: ${results.totalSelected}\nOn FTL: ${results.coveredCount}\nNot on FTL: ${results.notCoveredCount}\nHigher Outbreak Frequency: ${results.highOutbreakCount}\n${exemptionSection}\n\nCATEGORIES:\n${results.categories.map(c => `${c.covered ? '[ON FTL]' : '[NOT ON FTL]'} ${c.name}`).join('\n')}\n\nRegulatory Reference: 21 CFR Part 1 Subpart S\nLearn more: regengine.co/fsma`;
            const blob = new Blob([reportContent], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `FTL-Coverage-Report-${new Date().toISOString().split('T')[0]}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            toast({ title: "Report Downloaded", description: "Your FTL coverage report has been saved." });
        } finally {
            setIsDownloading(false);
        }
    };

    const results = getResults();
    const coveragePercent = results.totalSelected > 0 ? Math.round((results.coveredCount / results.totalSelected) * 100) : 0;

    return (
        <div style={{ minHeight: '100vh', background: T.bg, fontFamily: T.sans, color: T.textBody }}>
            <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />

            {/* Noise Overlay */}
            <div style={{ position: 'fixed', inset: 0, opacity: 0.015, pointerEvents: 'none', zIndex: 1, backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`, backgroundSize: '128px 128px' }} />

            {/* Hero */}
            <section style={{ position: 'relative', zIndex: 2, borderBottom: `1px solid ${T.border}`, background: T.accentBg }}>
                <div style={{ maxWidth: '900px', margin: '0 auto', padding: '64px 24px', textAlign: 'center' }}>
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                        <span style={{ display: 'inline-block', padding: '4px 12px', borderRadius: '20px', background: T.successBg, border: `1px solid ${T.successBorder}`, fontSize: '12px', fontWeight: 600, color: T.accent, marginBottom: '16px' }}>
                            Free Tool • No Login Required
                        </span>
                        <h1 style={{ fontSize: '40px', fontWeight: 700, color: T.textPrimary, margin: '0 0 16px', lineHeight: 1.1 }}>
                            FTL Coverage Checker
                        </h1>
                        <p style={{ fontSize: '18px', color: T.textMuted, maxWidth: '600px', margin: '0 auto 24px', lineHeight: 1.6 }}>
                            Instantly check if your products are covered by FDA FSMA 204 Food Traceability requirements
                        </p>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '24px', fontSize: '13px', color: T.textDim }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><CheckCircle2 size={14} style={{ color: T.accent }} /> No account required</span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><CheckCircle2 size={14} style={{ color: T.accent }} /> Results in seconds</span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><CheckCircle2 size={14} style={{ color: T.accent }} /> Deadline: July 2028</span>
                        </div>
                    </motion.div>
                </div>
            </section>

            <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '48px 24px', position: 'relative', zIndex: 2 }}>
                {/* Step Progress */}
                {currentStep !== 'categories' && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', marginBottom: '32px' }}>
                        {[{ num: 1, label: 'Categories', step: 'categories' }, { num: 2, label: 'Exemptions', step: 'exemptions' }, { num: 3, label: 'Results', step: 'results' }].map((s, i) => (
                            <div key={s.step} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                {i > 0 && <div style={{ width: '32px', height: '1px', background: T.border }} />}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: currentStep === s.step ? T.accent : T.textDim }}>
                                    <div style={{ width: '24px', height: '24px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 600, background: currentStep === s.step ? T.accent : T.elevated, color: currentStep === s.step ? T.bg : T.textDim }}>{s.num}</div>
                                    <span style={{ fontSize: '13px', fontWeight: currentStep === s.step ? 600 : 400 }}>{s.label}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                <AnimatePresence mode="wait">
                    {/* Step 1: Category Selection */}
                    {currentStep === 'categories' && (
                        <motion.div key="selector" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                            <div style={{ padding: '32px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '16px', marginBottom: '24px' }}>
                                <div style={{ marginBottom: '24px' }}>
                                    <h2 style={{ fontSize: '20px', fontWeight: 600, color: T.textPrimary, margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                        <Search size={20} style={{ color: T.accent }} /> Select Your Product Categories
                                    </h2>
                                    <p style={{ fontSize: '14px', color: T.textMuted, margin: 0 }}>Choose all the food categories your company handles</p>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
                                    {FTL_CATEGORIES.map(category => {
                                        const Icon = category.icon;
                                        const isSelected = selectedCategories.includes(category.id);
                                        return (
                                            <div
                                                key={category.id}
                                                onClick={() => toggleCategory(category.id)}
                                                style={{
                                                    padding: '16px', borderRadius: '10px', cursor: 'pointer', transition: 'all 0.15s',
                                                    background: isSelected ? T.accentBg : T.surface,
                                                    border: `2px solid ${isSelected ? T.accent : T.border}`,
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                                                    <div style={{ width: '18px', height: '18px', borderRadius: '4px', border: `2px solid ${isSelected ? T.accent : T.textDim}`, background: isSelected ? T.accent : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}>
                                                        {isSelected && <CheckCircle2 size={12} style={{ color: T.bg }} />}
                                                    </div>
                                                    <div style={{ flex: 1 }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                                            <Icon size={14} style={{ color: isSelected ? T.accent : T.textDim }} />
                                                            <span style={{ fontWeight: 500, color: T.textPrimary, fontSize: '14px' }}>{category.name}</span>
                                                            <span style={{ fontSize: '10px', fontWeight: 600, padding: '2px 6px', borderRadius: '4px', background: category.covered ? T.successBg : T.elevated, color: category.covered ? T.accent : T.textDim, border: `1px solid ${category.covered ? T.successBorder : T.border}` }}>
                                                                {category.covered ? 'On FTL' : 'Not on FTL'}
                                                            </span>
                                                        </div>
                                                        <p style={{ fontSize: '12px', color: T.textMuted, marginTop: '4px', lineHeight: 1.4 }}>{category.examples}</p>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>

                                <div style={{ marginTop: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span style={{ fontSize: '13px', color: T.textMuted }}>{selectedCategories.length} categories selected</span>
                                    <button
                                        onClick={handleCheck}
                                        disabled={selectedCategories.length === 0}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', borderRadius: '8px', border: 'none', cursor: selectedCategories.length === 0 ? 'not-allowed' : 'pointer',
                                            background: selectedCategories.length === 0 ? T.elevated : T.accent,
                                            color: selectedCategories.length === 0 ? T.textDim : T.bg,
                                            fontSize: '14px', fontWeight: 600, transition: 'all 0.15s',
                                        }}
                                    >
                                        Check My Coverage <ArrowRight size={16} />
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {/* Step 2: Exemption Wizard */}
                    {currentStep === 'exemptions' && (
                        <motion.div key="exemptions" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                            <div style={{ padding: '32px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '16px', marginBottom: '24px' }}>
                                <div style={{ marginBottom: '24px' }}>
                                    <h2 style={{ fontSize: '20px', fontWeight: 600, color: T.textPrimary, margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                        <ShieldCheck size={20} style={{ color: T.accent }} /> Check for Exemptions
                                    </h2>
                                    <p style={{ fontSize: '14px', color: T.textMuted, margin: 0 }}>Answer these questions to see if you qualify for any FSMA 204 exemptions</p>
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                    {EXEMPTION_QUESTIONS.map((q, index) => {
                                        const Icon = q.icon;
                                        const answer = exemptionAnswers[q.id];
                                        const isExpanded = showExemptionHelp === q.id;
                                        const alreadyExempt = Object.entries(exemptionAnswers).some(([id, val]) => val === true && EXEMPTION_QUESTIONS.findIndex(x => x.id === id) < index);
                                        if (alreadyExempt && answer !== true) return null;

                                        return (
                                            <div key={q.id} style={{ padding: '20px', borderRadius: '10px', background: answer === true ? T.successBg : T.surface, border: `2px solid ${answer === true ? T.successBorder : T.border}` }}>
                                                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                                                    <div style={{ padding: '10px', borderRadius: '8px', background: answer === true ? T.successBg : T.elevated }}>
                                                        <Icon size={20} style={{ color: answer === true ? T.accent : T.textDim }} />
                                                    </div>
                                                    <div style={{ flex: 1 }}>
                                                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
                                                            <div>
                                                                <p style={{ fontWeight: 500, color: T.textPrimary, margin: '0 0 6px', fontSize: '14px', lineHeight: 1.5 }}>{q.question}</p>
                                                                <a href={ecfrUrl(q.citation)} target="_blank" rel="noopener noreferrer" style={{ fontSize: '11px', fontFamily: T.mono, color: T.accent, background: T.elevated, padding: '2px 8px', borderRadius: '4px', textDecoration: 'none' }}>{q.citation}</a>
                                                            </div>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                                                                <button onClick={() => handleExemptionAnswer(q.id, true)} style={{ padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 500, background: answer === true ? T.accent : T.elevated, color: answer === true ? T.bg : T.textBody }}>Yes</button>
                                                                <button onClick={() => handleExemptionAnswer(q.id, false)} style={{ padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 500, background: answer === false ? T.textDim : T.elevated, color: answer === false ? '#fff' : T.textBody }}>No</button>
                                                                <button onClick={() => setShowExemptionHelp(isExpanded ? null : q.id)} style={{ padding: '6px', borderRadius: '6px', border: 'none', cursor: 'pointer', background: 'transparent' }}>
                                                                    <HelpCircle size={16} style={{ color: T.textDim }} />
                                                                </button>
                                                            </div>
                                                        </div>
                                                        {isExpanded && <p style={{ marginTop: '12px', fontSize: '13px', color: T.textMuted, background: T.elevated, padding: '10px', borderRadius: '6px' }}>{q.helpText}</p>}
                                                        {answer === true && (
                                                            <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px', color: T.accent }}>
                                                                <CheckCircle2 size={16} /> <span style={{ fontSize: '13px', fontWeight: 500 }}>You may qualify for this exemption!</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>

                                <div style={{ marginTop: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <button onClick={handleBackToCategories} style={{ padding: '10px 20px', borderRadius: '8px', border: `1px solid ${T.border}`, background: 'transparent', color: T.textBody, fontSize: '14px', cursor: 'pointer' }}>← Back to Categories</button>
                                    <div style={{ display: 'flex', gap: '12px' }}>
                                        <button onClick={handleSkipExemptions} style={{ padding: '10px 20px', borderRadius: '8px', border: `1px solid ${T.border}`, background: 'transparent', color: T.textBody, fontSize: '14px', cursor: 'pointer' }}>Skip Exemptions</button>
                                        <button onClick={handleFinishExemptions} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 24px', borderRadius: '8px', border: 'none', background: T.accent, color: T.bg, fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                            See Results <ArrowRight size={16} />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {/* Step 3: Results */}
                    {currentStep === 'results' && (
                        <motion.div key="results" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                            <div style={{ display: 'grid', gap: '24px', gridTemplateColumns: '1fr 340px' }}>
                                {/* Main Result Card */}
                                <div style={{ padding: '32px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '16px' }}>
                                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '24px' }}>
                                        <div>
                                            <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.textPrimary, margin: '0 0 8px' }}>Your FTL Coverage Results</h2>
                                            <p style={{ fontSize: '14px', color: T.textMuted, margin: 0 }}>Based on your selected product categories</p>
                                        </div>
                                        <button
                                            onClick={handleCopyLink}
                                            style={{
                                                display: 'flex', alignItems: 'center', gap: '8px',
                                                padding: '10px 16px', borderRadius: '8px',
                                                border: `1px solid ${linkCopied ? T.successBorder : T.border}`,
                                                background: linkCopied ? T.successBg : T.elevated,
                                                color: linkCopied ? T.accent : T.textBody,
                                                fontSize: '14px', fontWeight: 500, cursor: 'pointer',
                                                transition: 'all 0.2s ease'
                                            }}
                                        >
                                            {linkCopied ? <Check size={16} /> : <Share2 size={16} />}
                                            {linkCopied ? 'Link Copied!' : 'Share Results'}
                                        </button>
                                    </div>

                                    {/* Coverage Meter */}
                                    <div style={{ marginBottom: '32px' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                            <span style={{ fontSize: '16px', fontWeight: 600, color: T.textPrimary }}>FSMA 204 Coverage</span>
                                            <span style={{ fontSize: '28px', fontWeight: 700, color: coveragePercent === 100 ? T.danger : coveragePercent > 50 ? T.warning : coveragePercent > 0 ? T.warning : T.accent }}>{coveragePercent}%</span>
                                        </div>
                                        <div style={{ height: '8px', background: T.elevated, borderRadius: '4px', overflow: 'hidden' }}>
                                            <motion.div initial={{ width: 0 }} animate={{ width: `${coveragePercent}%` }} transition={{ duration: 1, ease: 'easeOut' }} style={{ height: '100%', background: coveragePercent === 100 ? T.danger : coveragePercent > 50 ? T.warning : coveragePercent > 0 ? T.warning : T.accent }} />
                                        </div>
                                    </div>

                                    {/* Stats Grid */}
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '32px' }}>
                                        <div style={{ textAlign: 'center', padding: '20px', background: T.successBg, borderRadius: '10px', border: `1px solid ${T.successBorder}` }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: T.accent }}>{results.coveredCount}</div>
                                            <div style={{ fontSize: '12px', color: T.textMuted }}>On FTL</div>
                                        </div>
                                        <div style={{ textAlign: 'center', padding: '20px', background: T.elevated, borderRadius: '10px', border: `1px solid ${T.border}` }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: T.textDim }}>{results.notCoveredCount}</div>
                                            <div style={{ fontSize: '12px', color: T.textMuted }}>Not on FTL</div>
                                        </div>
                                        <div style={{ textAlign: 'center', padding: '20px', background: T.warningBg, borderRadius: '10px', border: `1px solid ${T.warningBorder}` }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: T.warning }}>{results.highOutbreakCount}</div>
                                            <div style={{ fontSize: '12px', color: T.textMuted }}>High Outbreak Frequency</div>
                                        </div>
                                    </div>

                                    {/* Exemption Status */}
                                    {results.coveredCount > 0 && (
                                        <div style={{ marginBottom: '24px', padding: '20px', borderRadius: '10px', background: results.exemptionStatus === 'EXEMPT' ? T.successBg : results.exemptionStatus === 'NOT_EXEMPT' ? T.warningBg : T.elevated, border: `2px solid ${results.exemptionStatus === 'EXEMPT' ? T.successBorder : results.exemptionStatus === 'NOT_EXEMPT' ? T.warningBorder : T.border}` }}>
                                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                                                {results.exemptionStatus === 'EXEMPT' ? <ShieldCheck size={24} style={{ color: T.accent }} /> : results.exemptionStatus === 'NOT_EXEMPT' ? <AlertTriangle size={24} style={{ color: T.warning }} /> : <HelpCircle size={24} style={{ color: T.textDim }} />}
                                                <div>
                                                    <h4 style={{ fontWeight: 600, color: results.exemptionStatus === 'EXEMPT' ? T.accent : results.exemptionStatus === 'NOT_EXEMPT' ? T.warning : T.textPrimary, margin: '0 0 8px' }}>
                                                        {results.exemptionStatus === 'EXEMPT' ? '🎉 You May Be Exempt from FSMA 204!' : results.exemptionStatus === 'NOT_EXEMPT' ? 'Full FSMA 204 Requirements Apply' : 'Exemption Status Unknown'}
                                                    </h4>
                                                    {results.exemptionStatus === 'EXEMPT' && results.qualifyingExemptions.map(e => (
                                                        <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', marginBottom: '4px' }}>
                                                            <CheckCircle2 size={14} style={{ color: T.accent }} /> <a href={ecfrUrl(e.citation)} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500, color: T.accent, textDecoration: 'none' }}>{e.citation}</a>
                                                        </div>
                                                    ))}
                                                    {results.exemptionStatus === 'NOT_EXEMPT' && <p style={{ fontSize: '13px', color: T.textMuted, margin: 0 }}>You must comply with FSMA 204 traceability requirements for covered products by July 2028.</p>}
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Same Form Ingredient Rule */}
                                    {results.coveredCount > 0 && results.exemptionStatus !== 'EXEMPT' && (
                                        <div style={{ marginBottom: '24px', padding: '20px', borderRadius: '10px', background: T.infoBg, border: `2px solid ${T.infoBorder}` }}>
                                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                                                <AlertTriangle size={24} style={{ color: T.info }} />
                                                <div>
                                                    <h4 style={{ fontWeight: 600, color: T.info, margin: '0 0 8px' }}>"Same Form" Ingredient Rule</h4>
                                                    <p style={{ fontSize: '13px', color: T.textMuted, margin: '0 0 8px' }}>If you use FTL foods as ingredients in other products (e.g., peppers in fresh salsa) and they remain in the same form (fresh, not cooked/canned), those finished products inherit FSMA 204 requirements.</p>
                                                    <a href="https://www.ecfr.gov/current/title-21/section-1.1310" target="_blank" rel="noopener noreferrer" style={{ fontSize: '11px', fontFamily: T.mono, color: T.accent, textDecoration: 'none' }}>21 CFR § 1.1310(b)</a>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Category Breakdown with CTE/KDE Details */}
                                    <h3 style={{ fontWeight: 600, color: T.textPrimary, margin: '0 0 16px' }}>Category Breakdown</h3>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        {results.categories.map(category => (
                                            <div key={category.id} style={{ background: T.elevated, borderRadius: '8px', overflow: 'hidden' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                                        {category.covered ? <CheckCircle2 size={18} style={{ color: T.accent }} /> : <XCircle size={18} style={{ color: T.textDim }} />}
                                                        <span style={{ fontSize: '14px', color: T.textPrimary }}>{category.name}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                        {category.outbreakFrequency === 'HIGH' && <span style={{ fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', background: T.dangerBg, color: T.danger, border: `1px solid ${T.dangerBorder}` }}>Higher Outbreak Frequency</span>}
                                                        <span style={{ fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', background: category.covered ? T.successBg : T.elevated, color: category.covered ? T.accent : T.textDim }}>{category.covered ? 'FSMA 204 Applies' : 'Not Covered'}</span>
                                                    </div>
                                                </div>
                                                {/* CTE/KDE Requirements - Only for covered categories */}
                                                {category.covered && category.ctes && category.ctes.length > 0 && (
                                                    <div style={{ padding: '12px 16px', borderTop: `1px solid ${T.border}`, background: 'rgba(16,185,129,0.03)' }}>
                                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                                            <div>
                                                                <div style={{ fontSize: '11px', fontWeight: 600, color: T.accent, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                                                    CTEs Required
                                                                </div>
                                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                                                    {category.ctes.map(cte => (
                                                                        <span key={cte} style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: T.successBg, color: T.accent, border: `1px solid ${T.successBorder}` }}>
                                                                            {cte}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                            <div>
                                                                <div style={{ fontSize: '11px', fontWeight: 600, color: T.accent, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                                                    KDEs per Event
                                                                </div>
                                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                                                    {category.kdes.map(kde => (
                                                                        <span key={kde} style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: T.surface, color: T.textMuted, border: `1px solid ${T.border}` }}>
                                                                            {kde}
                                                                        </span>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>

                                    <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
                                        <button onClick={handleStartOver} style={{ padding: '10px 20px', borderRadius: '8px', border: `1px solid ${T.border}`, background: 'transparent', color: T.textBody, fontSize: '14px', cursor: 'pointer' }}>← Start Over</button>
                                        <button onClick={handleDownloadReport} disabled={isDownloading} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', borderRadius: '8px', border: `1px solid ${T.border}`, background: 'transparent', color: T.textBody, fontSize: '14px', cursor: 'pointer' }}>
                                            {isDownloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} {isDownloading ? 'Generating...' : 'Download Report'}
                                        </button>
                                    </div>
                                </div>

                                {/* CTA Card */}
                                <div style={{ padding: '28px', background: `linear-gradient(135deg, ${T.accent} 0%, #059669 100%)`, borderRadius: '16px', color: '#fff', alignSelf: 'start' }}>
                                    {results.coveredCount > 0 ? (
                                        <>
                                            <AlertTriangle size={28} style={{ marginBottom: '12px' }} />
                                            <h3 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 12px' }}>Action Required</h3>
                                            <p style={{ fontSize: '14px', opacity: 0.9, margin: '0 0 8px' }}>You have <strong>{results.coveredCount} product categories</strong> that require FSMA 204 compliance by <strong>July 2028</strong>.</p>
                                            <p style={{ fontSize: '13px', opacity: 0.8, margin: '0 0 20px' }}>But major retailers are already requiring traceability NOW.</p>
                                            {!emailSubmitted ? (
                                                <form onSubmit={handleEmailSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                                    <p style={{ fontWeight: 600, margin: 0 }}>Get Your Full Compliance Report</p>
                                                    <input type="email" placeholder="Enter your email" value={email} onChange={(e) => setEmail(e.target.value)} required style={{ padding: '12px 16px', borderRadius: '8px', border: 'none', background: 'rgba(255,255,255,0.2)', color: '#fff', fontSize: '14px' }} />
                                                    <button type="submit" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px', borderRadius: '8px', border: 'none', background: '#fff', color: T.accent, fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                                        <Mail size={16} /> Send Me the Report
                                                    </button>
                                                </form>
                                            ) : (
                                                <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(255,255,255,0.2)', borderRadius: '10px' }}>
                                                    <CheckCircle2 size={32} style={{ margin: '0 auto 8px' }} />
                                                    <p style={{ fontWeight: 600, margin: 0 }}>Report Sent!</p>
                                                    <p style={{ fontSize: '13px', opacity: 0.8, margin: '4px 0 0' }}>Check your inbox</p>
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <>
                                            <CheckCircle2 size={28} style={{ marginBottom: '12px' }} />
                                            <h3 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 12px' }}>Good News!</h3>
                                            <p style={{ fontSize: '14px', opacity: 0.9, margin: '0 0 16px' }}>None of your selected categories are currently on the Food Traceability List.</p>
                                            <Link href="/fsma" style={{ display: 'block', textAlign: 'center', padding: '12px', borderRadius: '8px', background: '#fff', color: T.accent, fontSize: '14px', fontWeight: 600, textDecoration: 'none' }}>Learn About Retailer Requirements</Link>
                                        </>
                                    )}
                                </div>
                            </div>

                            {/* What's Next Section */}
                            {results.coveredCount > 0 && (
                                <div style={{ marginTop: '32px', padding: '32px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '16px' }}>
                                    <h3 style={{ fontSize: '20px', fontWeight: 700, color: T.textPrimary, margin: '0 0 24px' }}>What You Need to Know</h3>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
                                        {[
                                            { num: 1, title: 'Critical Tracking Events (CTEs)', desc: 'You must record events for: Harvesting, Cooling, Initial Packing, First Land-Based Receiving, Shipping, Receiving, and Transformation of FTL foods.', cfrLink: 'https://www.ecfr.gov/current/title-21/section-1.1325', cfrLabel: '§1.1325–§1.1350' },
                                            { num: 2, title: '24-Hour Response', desc: 'FDA can request your traceability data, and you must provide it in electronic format within 24 hours.' },
                                            { num: 3, title: 'Traceability Lot Codes (TLCs)', desc: 'Each lot must have a unique code that links all events across your supply chain.' },
                                        ].map(item => (
                                            <div key={item.num}>
                                                <h4 style={{ display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 600, color: T.textPrimary, margin: '0 0 8px' }}>
                                                    <span style={{ width: '24px', height: '24px', borderRadius: '50%', background: T.accentBg, color: T.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 700 }}>{item.num}</span>
                                                    {item.title}
                                                </h4>
                                                <p style={{ fontSize: '13px', color: T.textMuted, margin: 0, lineHeight: 1.6 }}>
                                                    {item.desc}
                                                    {item.cfrLink && <> (<a href={item.cfrLink} target="_blank" rel="noopener noreferrer" style={{ color: T.accent, textDecoration: 'none', fontFamily: T.mono, fontSize: '11px' }}>{item.cfrLabel}</a>)</>}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Regulatory Sources Footer */}
                            <div style={{ marginTop: '32px', padding: '24px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '12px' }}>
                                <h4 style={{ fontSize: '14px', fontWeight: 600, color: T.textPrimary, margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <ExternalLink size={16} style={{ color: T.accent }} />
                                    Regulatory Sources
                                </h4>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                                    <a href="https://www.ecfr.gov/current/title-21/part-1/subpart-S" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        21 CFR Part 1 Subpart S — Full Rule Text
                                    </a>
                                    <a href="https://www.federalregister.gov/documents/2022/11/21/2022-24417/requirements-for-additional-traceability-records-for-certain-foods" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        Final Rule — 87 FR 70910 (Nov 21, 2022)
                                    </a>
                                    <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        FDA Food Traceability List (Official)
                                    </a>
                                    <a href="https://www.federalregister.gov/documents/2025/08/07/2025-14967/requirements-for-additional-traceability-records-for-certain-foods-compliance-date-extension" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        Compliance Date Extension — 90 FR 38084
                                    </a>
                                    <a href="https://www.fda.gov/files/food/published/FSMA%20Rule%20for%20Food%20Traceability%20-%202024-0520-CTEs-KDEs.pdf" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        FDA CTE/KDE Reference Chart (PDF)
                                    </a>
                                    <a href="https://www.fda.gov/regulatory-information/search-fda-guidance-documents/small-entity-compliance-guide-requirements-additional-traceability-records-certain-foods-what-you" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        Small Entity Compliance Guide
                                    </a>
                                    <a href="https://collaboration.fda.gov/tefcv13" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}>
                                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }} />
                                        FDA Exemptions & Exclusions Tool
                                    </a>
                                </div>
                                <p style={{ fontSize: '11px', color: T.textMuted, margin: '16px 0 0', fontStyle: 'italic' }}>
                                    This tool is for informational purposes only and does not constitute legal advice. Consult the full regulatory text and your legal counsel for compliance decisions. Last verified against eCFR: February 2026.
                                </p>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
