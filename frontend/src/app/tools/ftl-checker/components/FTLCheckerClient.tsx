'use client';

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { usePostHog } from 'posthog-js/react';
import { motion, AnimatePresence } from 'framer-motion';
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { RelatedTools } from "@/components/layout/related-tools";
import { FREE_TOOLS } from "@/lib/fsma-tools-data";
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
import { generateBrandedPDF } from '@/lib/pdf-report';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS (Unified Dark Theme)
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    surfaceHover: 'rgba(255,255,255,0.04)',
    elevated: 'rgba(255,255,255,0.06)',
    border: 'rgba(255,255,255,0.06)',
    borderStrong: 'rgba(255,255,255,0.10)',
    accent: 'var(--re-brand)',
    accentHover: 'var(--re-brand-dark)',
    accentBg: 'rgba(16,185,129,0.08)',
    accentBorder: 'rgba(16,185,129,0.2)',
    textPrimary: 'var(--re-text-primary)',
    textBody: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    warning: 'var(--re-warning)',
    warningBg: 'rgba(245,158,11,0.1)',
    warningBorder: 'rgba(245,158,11,0.2)',
    danger: 'var(--re-danger)',
    dangerBg: 'rgba(239,68,68,0.1)',
    dangerBorder: 'rgba(239,68,68,0.2)',
    info: 'var(--re-info)',
    infoBg: 'rgba(96,165,250,0.1)',
    infoBorder: 'rgba(96,165,250,0.2)',
    success: 'var(--re-brand)',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
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
        category: 'Produce',
        icon: Apple,
        examples: 'Veggie trays, pre-cut carrots, celery sticks, broccoli florets',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'finfish-histamine',
        name: 'Finfish — Scombrotoxin/Histamine-Forming',
        category: 'Seafood',
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
        category: 'Seafood',
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
        category: 'Seafood',
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
        category: 'Seafood',
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
        category: 'Seafood',
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
        category: 'Seafood',
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
        id: 'deli-salads',
        name: 'Ready-to-Eat Deli Salads',
        category: 'Other',
        icon: Apple,
        examples: 'Egg salad, seafood salad, pasta salad, potato salad',
        covered: true,
        outbreakFrequency: 'MODERATE',
        ctes: ['Receiving', 'Transformation', 'Shipping'],
        cfrSections: '§1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Input TLCs', 'New TLC Assigned']
    },
    {
        id: 'eggs',
        name: 'Shell Eggs',
        category: 'Eggs',
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
        category: 'Other',
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
        category: 'Dairy',
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
        category: 'Dairy',
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
        category: 'Dairy',
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
        category: 'Other',
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
        category: 'Other',
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
        category: 'Other',
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

export function FTLCheckerClient() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const posthog = usePostHog();
    const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
    const [currentStep, setCurrentStep] = useState<'categories' | 'exemptions' | 'results'>('categories');
    const [exemptionAnswers, setExemptionAnswers] = useState<Record<string, boolean | null>>({});
    const [showExemptionHelp, setShowExemptionHelp] = useState<string | null>(null);
    const [showResults, setShowResults] = useState(false);
    const [email, setEmail] = useState('');
    const [emailSubmitted, setEmailSubmitted] = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);
    const [linkCopied, setLinkCopied] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [activeFilter, setActiveFilter] = useState<'All' | 'Seafood' | 'Produce' | 'Dairy' | 'Eggs' | 'Other'>('All');
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

            // Capture lead
            const results = getResults();
            posthog?.capture('ftl_report_requested', {
                email: email,
                categories_selected: selectedCategories,
                covered_count: results.coveredCount,
                risk_level: results.coveredCount > 0 ? 'HIGH' : 'LOW'
            });
            posthog?.identify(email, { email: email });

            toast({ title: "We'll be in touch!", description: "A member of our team will review your coverage and reach out shortly." });
        }
    };

    const handleDownloadReport = async () => {
        setIsDownloading(true);
        try {
            const results = getResults();

            const exemptionLabel =
                results.exemptionStatus === 'EXEMPT'
                    ? 'POTENTIALLY EXEMPT'
                    : results.exemptionStatus === 'NOT_EXEMPT'
                        ? 'NOT EXEMPT'
                        : 'UNKNOWN';

            generateBrandedPDF({
                title: 'FTL Coverage Report',
                subtitle: `${results.totalSelected} categor${results.totalSelected === 1 ? 'y' : 'ies'} analyzed`,
                reportType: 'FDA FSMA 204 - Food Traceability List',
                sections: [
                    { type: 'heading', text: 'Summary', level: 2 },
                    {
                        type: 'keyValue',
                        pairs: [
                            { key: 'Total Categories', value: String(results.totalSelected) },
                            { key: 'On FTL', value: String(results.coveredCount), status: 'success' },
                            {
                                key: 'Not on FTL',
                                value: String(results.notCoveredCount),
                                status: results.notCoveredCount > 0 ? 'danger' : 'neutral',
                            },
                            {
                                key: 'Higher Outbreak Frequency',
                                value: String(results.highOutbreakCount),
                                status: results.highOutbreakCount > 0 ? 'warning' : 'neutral',
                            },
                            {
                                key: 'Exemption Status',
                                value: exemptionLabel,
                                status: exemptionLabel === 'NOT EXEMPT' ? 'danger' : 'warning',
                            },
                        ],
                    },
                    { type: 'divider' },
                    { type: 'heading', text: 'Category Results', level: 2 },
                    {
                        type: 'table',
                        headers: ['Category', 'FTL Status'],
                        rows: results.categories.map((category) => [
                            category.name,
                            category.covered ? 'ON FTL' : 'NOT ON FTL',
                        ]),
                    },
                    ...(results.exemptionStatus === 'EXEMPT' && results.qualifyingExemptions.length > 0
                        ? [
                            { type: 'spacer' as const },
                            { type: 'heading' as const, text: 'Qualifying Exemptions', level: 2 as const },
                            {
                                type: 'table' as const,
                                headers: ['Citation'],
                                rows: results.qualifyingExemptions.map((exemption) => [exemption.citation]),
                            },
                        ]
                        : []),
                ],
                footer: {
                    left: 'Confidential',
                    right: 'regengine.co',
                    legalLine: 'Regulatory Reference: 21 CFR Part 1 Subpart S',
                },
                filename: `FTL-Coverage-Report-${new Date().toISOString().split('T')[0]}`,
            });

            toast({ title: "Report Downloaded", description: "Your FTL coverage report has been saved." });
        } finally {
            setIsDownloading(false);
        }
    };

    const results = getResults();
    const coveragePercent = results.totalSelected > 0 ? Math.round((results.coveredCount / results.totalSelected) * 100) : 0;

    return (
        <div style={{ minHeight: '100vh', background: T.bg, fontFamily: T.sans, color: T.textBody, padding: '24px' }}>
            <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "FTL Checker" }
                    ]}
                />
            </div>
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
                            <span className="flex items-center gap-1.5"><CheckCircle2 size={14} className="text-re-brand" /> No account required</span>
                            <span className="flex items-center gap-1.5"><CheckCircle2 size={14} className="text-re-brand" /> Results in seconds</span>
                            <span className="flex items-center gap-1.5"><CheckCircle2 size={14} className="text-re-brand" /> Deadline: July 2028</span>
                        </div>
                    </motion.div>
                </div>
            </section>

            <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '48px 24px', position: 'relative', zIndex: 2 }}>
                {/* Step Progress */}
                {currentStep !== 'categories' && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', marginBottom: '32px' }}>
                        {[{ num: 1, label: 'Categories', step: 'categories' }, { num: 2, label: 'Exemptions', step: 'exemptions' }, { num: 3, label: 'Results', step: 'results' }].map((s, i) => (
                            <div key={s.step} className="flex items-center gap-2">
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
                                <div className="mb-6 space-y-4">
                                    <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
                                        <div>
                                            <h2 style={{ fontSize: '20px', fontWeight: 600, color: T.textPrimary, margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                <Search size={20} className="text-re-brand" /> Select Your Product Categories
                                            </h2>
                                            <p className="text-sm text-re-text-muted m-0">Choose all the food categories your company handles</p>
                                        </div>
                                        <div className="relative w-full md:w-64">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--re-text-dim)]" />
                                            <input
                                                type="text"
                                                placeholder="Search products (e.g. shrimp)"
                                                value={searchTerm}
                                                onChange={(e) => setSearchTerm(e.target.value)}
                                                className="w-full bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] rounded-xl py-2 pl-9 pr-4 text-sm focus:outline-none focus:border-[var(--re-brand)] transition-colors"
                                            />
                                        </div>
                                    </div>

                                    {/* Filter Chips */}
                                    <div className="flex flex-wrap gap-2">
                                        {(['All', 'Seafood', 'Produce', 'Dairy', 'Eggs', 'Other'] as const).map(f => (
                                            <button
                                                key={f}
                                                onClick={() => setActiveFilter(f)}
                                                className={`px-3 py-1 rounded-full text-xs font-bold transition-all ${activeFilter === f
                                                    ? 'bg-[var(--re-brand)] text-white'
                                                    : 'bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)] hover:text-[var(--re-text-secondary)] border border-[var(--re-border-default)]'
                                                    }`}
                                            >
                                                {f === 'Seafood' ? '🦀 Seafood' : f === 'Produce' ? '🥬 Produce' : f === 'Dairy' ? '🧀 Dairy' : f === 'Eggs' ? '🥚 Eggs' : f}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px', maxHeight: '500px', overflowY: 'auto', paddingRight: '8px' }} className="re-scrollbar">
                                    {FTL_CATEGORIES
                                        .filter(c => {
                                            const matchesSearch = c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                                                c.examples.toLowerCase().includes(searchTerm.toLowerCase());
                                            const matchesFilter = activeFilter === 'All' || c.category === activeFilter;
                                            return matchesSearch && matchesFilter;
                                        })
                                        .map(category => {
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
                                                    <div className="flex items-start gap-3">
                                                        <div style={{ width: '18px', height: '18px', borderRadius: '4px', border: `2px solid ${isSelected ? T.accent : T.textDim}`, background: isSelected ? T.accent : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}>
                                                            {isSelected && <CheckCircle2 size={12} style={{ color: T.bg }} />}
                                                        </div>
                                                        <div className="flex-1">
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

                                <div className="mt-6 flex items-center justify-between">
                                    <span className="text-[13px] text-re-text-muted">{selectedCategories.length} categories selected</span>
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
                                <div className="mb-6">
                                    <h2 style={{ fontSize: '20px', fontWeight: 600, color: T.textPrimary, margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                                        <ShieldCheck size={20} className="text-re-brand" /> Check for Exemptions
                                    </h2>
                                    <p className="text-sm text-re-text-muted m-0">Answer these questions to see if you qualify for any FSMA 204 exemptions</p>
                                </div>

                                <div className="flex flex-col gap-3">
                                    {EXEMPTION_QUESTIONS.map((q, index) => {
                                        const Icon = q.icon;
                                        const answer = exemptionAnswers[q.id];
                                        const isExpanded = showExemptionHelp === q.id;
                                        const alreadyExempt = Object.entries(exemptionAnswers).some(([id, val]) => val === true && EXEMPTION_QUESTIONS.findIndex(x => x.id === id) < index);
                                        if (alreadyExempt && answer !== true) return null;

                                        return (
                                            <div key={q.id} style={{ padding: '20px', borderRadius: '10px', background: answer === true ? T.successBg : T.surface, border: `2px solid ${answer === true ? T.successBorder : T.border}` }}>
                                                <div className="flex items-start gap-4">
                                                    <div style={{ padding: '10px', borderRadius: '8px', background: answer === true ? T.successBg : T.elevated }}>
                                                        <Icon size={20} style={{ color: answer === true ? T.accent : T.textDim }} />
                                                    </div>
                                                    <div className="flex-1">
                                                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
                                                            <div>
                                                                <p style={{ fontWeight: 500, color: T.textPrimary, margin: '0 0 6px', fontSize: '14px', lineHeight: 1.5 }}>{q.question}</p>
                                                                <a href={ecfrUrl(q.citation)} target="_blank" rel="noopener noreferrer" style={{ fontSize: '11px', fontFamily: T.mono, color: T.accent, background: T.elevated, padding: '2px 8px', borderRadius: '4px', textDecoration: 'none' }}>{q.citation}</a>
                                                            </div>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                                                                <button onClick={() => handleExemptionAnswer(q.id, true)} style={{ padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 500, background: answer === true ? T.accent : T.elevated, color: answer === true ? T.bg : T.textBody }}>Yes</button>
                                                                <button onClick={() => handleExemptionAnswer(q.id, false)} style={{ padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 500, background: answer === false ? T.textDim : T.elevated, color: answer === false ? '#fff' : T.textBody }}>No</button>
                                                                <button onClick={() => setShowExemptionHelp(isExpanded ? null : q.id)} style={{ padding: '6px', borderRadius: '6px', border: 'none', cursor: 'pointer', background: 'transparent' }}>
                                                                    <HelpCircle size={16} className="text-re-text-disabled" />
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

                                <div className="mt-6 flex items-center justify-between">
                                    <button onClick={handleBackToCategories} style={{ padding: '10px 20px', borderRadius: '8px', border: `1px solid ${T.border}`, background: 'transparent', color: T.textBody, fontSize: '14px', cursor: 'pointer' }}>← Back to Categories</button>
                                    <div className="flex gap-3">
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
                                            <p className="text-sm text-re-text-muted m-0">Based on your selected product categories</p>
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
                                    <div className="mb-8">
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
                                            <div className="text-xs text-re-text-muted">On FTL</div>
                                        </div>
                                        <div style={{ textAlign: 'center', padding: '20px', background: T.elevated, borderRadius: '10px', border: `1px solid ${T.border}` }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: T.textDim }}>{results.notCoveredCount}</div>
                                            <div className="text-xs text-re-text-muted">Not on FTL</div>
                                        </div>
                                        <div style={{ textAlign: 'center', padding: '20px', background: T.warningBg, borderRadius: '10px', border: `1px solid ${T.warningBorder}` }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: T.warning }}>{results.highOutbreakCount}</div>
                                            <div className="text-xs text-re-text-muted">High Outbreak Frequency</div>
                                        </div>
                                    </div>

                                    {/* Exemption Status */}
                                    {results.coveredCount > 0 && (
                                        <div style={{ marginBottom: '24px', padding: '20px', borderRadius: '10px', background: results.exemptionStatus === 'EXEMPT' ? T.successBg : results.exemptionStatus === 'NOT_EXEMPT' ? T.warningBg : T.elevated, border: `2px solid ${results.exemptionStatus === 'EXEMPT' ? T.successBorder : results.exemptionStatus === 'NOT_EXEMPT' ? T.warningBorder : T.border}` }}>
                                            <div className="flex items-start gap-3">
                                                {results.exemptionStatus === 'EXEMPT' ? <ShieldCheck size={24} className="text-re-brand" /> : results.exemptionStatus === 'NOT_EXEMPT' ? <AlertTriangle size={24} className="text-re-warning" /> : <HelpCircle size={24} className="text-re-text-disabled" />}
                                                <div>
                                                    <h4 style={{ fontWeight: 600, color: results.exemptionStatus === 'EXEMPT' ? T.accent : results.exemptionStatus === 'NOT_EXEMPT' ? T.warning : T.textPrimary, margin: '0 0 8px' }}>
                                                        {results.exemptionStatus === 'EXEMPT' ? '🎉 You May Be Exempt from FSMA 204!' : results.exemptionStatus === 'NOT_EXEMPT' ? 'Full FSMA 204 Requirements Apply' : 'Exemption Status Unknown'}
                                                    </h4>
                                                    {results.exemptionStatus === 'EXEMPT' && results.qualifyingExemptions.map(e => (
                                                        <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', marginBottom: '4px' }}>
                                                            <CheckCircle2 size={14} className="text-re-brand" /> <a href={ecfrUrl(e.citation)} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500, color: T.accent, textDecoration: 'none' }}>{e.citation}</a>
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
                                            <div className="flex items-start gap-3">
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
                                    <div className="flex flex-col gap-2">
                                        {results.categories.map(category => (
                                            <div key={category.id} style={{ background: T.elevated, borderRadius: '8px', overflow: 'hidden' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px' }}>
                                                    <div className="flex items-center gap-3">
                                                        {category.covered ? <CheckCircle2 size={18} className="text-re-brand" /> : <XCircle size={18} className="text-re-text-disabled" />}
                                                        <span style={{ fontSize: '14px', color: T.textPrimary }}>{category.name}</span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
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
                                            {isDownloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} {isDownloading ? 'Generating...' : 'Download PDF Report'}
                                        </button>
                                    </div>
                                </div>

                                {/* CTA Card */}
                                <div style={{ padding: '28px', background: `linear-gradient(135deg, ${T.accent} 0%, #059669 100%)`, borderRadius: '16px', color: '#fff', alignSelf: 'start' }}>
                                    {results.coveredCount > 0 ? (
                                        <>
                                            <AlertTriangle size={28} className="mb-3" />
                                            <h3 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 12px' }}>Action Required</h3>
                                            <p style={{ fontSize: '14px', opacity: 0.9, margin: '0 0 8px' }}>You have <strong>{results.coveredCount} product categories</strong> that require FSMA 204 compliance by <strong>July 2028</strong>.</p>
                                            <p style={{ fontSize: '13px', opacity: 0.8, margin: '0 0 20px' }}>But major retailers are already requiring traceability NOW.</p>
                                            {!emailSubmitted ? (
                                                <form onSubmit={handleEmailSubmit} className="flex flex-col gap-3">
                                                    <p style={{ fontWeight: 600, margin: 0 }}>Get Your Full Compliance Report</p>
                                                    <input type="email" placeholder="Enter your email" value={email} onChange={(e) => setEmail(e.target.value)} required style={{ padding: '12px 16px', borderRadius: '8px', border: 'none', background: 'rgba(255,255,255,0.2)', color: '#fff', fontSize: '14px' }} />
                                                    <button type="submit" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '12px', borderRadius: '8px', border: 'none', background: '#fff', color: T.accent, fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}>
                                                        <Mail size={16} /> Send Me the Report
                                                    </button>
                                                </form>
                                            ) : (
                                                <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(255,255,255,0.2)', borderRadius: '10px' }}>
                                                    <CheckCircle2 size={32} style={{ margin: '0 auto 8px' }} />
                                                    <p style={{ fontWeight: 600, margin: 0 }}>Request Received!</p>
                                                    <p style={{ fontSize: '13px', opacity: 0.8, margin: '4px 0 0' }}>We'll be in touch shortly</p>
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <>
                                            <CheckCircle2 size={28} className="mb-3" />
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
                                            { num: 2, title: '24-Hour Response', desc: 'FDA can request your traceability data, and you must provide it in electronic format within 24 hours.', cfrLink: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)', cfrLabel: '§1.1455(c)' },
                                            { num: 3, title: 'Traceability Lot Codes (TLCs)', desc: 'Each lot must have a unique code that links all events across your supply chain.', cfrLink: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1320', cfrLabel: '§1.1320' },
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
                                    <ExternalLink size={16} className="text-re-brand" />
                                    Regulatory Sources
                                </h4>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                                    <a href="https://www.ecfr.gov/current/title-21/part-1/subpart-S" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
                                        21 CFR Part 1 Subpart S — Full Rule Text
                                    </a>
                                    <a href="https://www.federalregister.gov/documents/2022/11/21/2022-24417/requirements-for-additional-traceability-records-for-certain-foods" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
                                        Final Rule — 87 FR 70910 (Nov 21, 2022)
                                    </a>
                                    <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
                                        FDA Food Traceability List (Official)
                                    </a>
                                    <a href="https://www.federalregister.gov/documents/2025/08/07/2025-14967/requirements-for-additional-traceability-records-for-certain-foods-compliance-date-extension" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
                                        Compliance Date Extension — 90 FR 38084
                                    </a>
                                    <a href="https://www.fda.gov/files/food/published/FSMA%20Rule%20for%20Food%20Traceability%20-%202024-0520-CTEs-KDEs.pdf" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
                                        FDA CTE/KDE Reference Chart (PDF)
                                    </a>
                                    <a href="https://www.fda.gov/regulatory-information/search-fda-guidance-documents/small-entity-compliance-guide-requirements-additional-traceability-records-certain-foods-what-you" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
                                        Small Entity Compliance Guide
                                    </a>
                                    <a href="https://collaboration.fda.gov/tefcv13" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-[13px] text-re-brand no-underline">
                                        <span className="re-dot bg-re-brand" />
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

                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['recall-readiness', 'kde-checker', 'roi-calculator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
