'use client';

import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { usePostHog } from '@/lib/posthog-provider';
import { motion, AnimatePresence } from 'framer-motion';
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { RelatedTools } from "@/components/layout/related-tools";
import { FREE_TOOLS } from "@/lib/fsma-tools-data";
import { experimentalFeaturesEnabled } from "@/lib/experimental-features";
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
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { submitAssessment } from '@/app/actions/submit-assessment';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Container } from '@/components/layout/container';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { getConversionAttribution, getReferrerHostname, trackEmailCaptureSubmit, trackToolRunStarted, trackToolRunCompleted } from '@/lib/conversion-events';

/** Selected/unselected row recipe shared by the pick lists (SPEC §4). */
const pickClasses = (selected: boolean) =>
    cn(
        'w-full rounded-lg border p-4 text-left transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none',
        selected
            ? 'border-re-border-strong bg-re-surface-inset'
            : 'border-re-border bg-re-surface-card hover:border-re-border-strong hover:bg-re-surface-inset'
    );

/** Filter chips carry a lucide glyph instead of an emoji (SPEC §5.4). */
const FILTER_ICONS: Record<string, typeof Leaf | null> = {
    All: null,
    Seafood: Fish,
    Produce: Leaf,
    Dairy: Milk,
    Eggs: Egg,
    Other: null,
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
        examples: 'Whole leaf lettuce, spinach bunches, kale, arugula, chard. Leafy greens listed in 21 CFR 112.2(a)(1), such as collards, are exempt under §1.1305(e).',
        exclusions: 'Does not include whole head cabbages (green, red, savoy) or banana/grape/tree leaves. Leafy greens listed in 21 CFR 112.2(a)(1), such as collards, are exempt under §1.1305(e). See fresh-cut leafy greens for pre-cut/bagged products.',
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
        name: 'Finfish, histamine-producing species',
        category: 'Seafood',
        icon: Fish,
        examples: 'Tuna, mackerel, mahi-mahi, bluefish, amberjack, bonito, swordfish',
        exclusions: 'Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g)',
        covered: true,
        outbreakFrequency: 'HIGH',
        ctes: ['First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation'],
        cfrSections: '§1.1335, §1.1340, §1.1345, §1.1350',
        kdes: ['Traceability Lot Code (TLC)', 'Location Identifier (GLN)', 'Date/Time', 'Quantity & UOM', 'Product Description', 'Reference Document Type & Number', 'Vessel Name', 'Harvest Area', 'Landing Port']
    },
    {
        id: 'finfish-ciguatoxin',
        name: 'Finfish, species potentially contaminated with ciguatoxin',
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
        name: 'Finfish, species not associated with histamine or ciguatoxin',
        category: 'Seafood',
        icon: Fish,
        examples: 'Salmon, cod, halibut, tilapia, trout, bass',
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
        examples: 'Oysters, clams, mussels, scallops. The scallop adductor muscle alone is excluded.',
        exclusions: 'The scallop adductor muscle alone is excluded. Raw bivalves under NSSP may be exempt per §1.1305(f)',
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
        examples: 'Shell eggs of the domesticated chicken',
        exclusions: 'Shell egg means the egg of the domesticated chicken.',
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
        examples: 'Brie, camembert, monterey jack, muenster, havarti, oaxaca, feta (per FTL definition; verify your specific cheese)',
        exclusions: 'Hard cheeses per 21 CFR 133.150 (e.g., aged cheddar, parmesan, asiago, aged gouda) are excluded. Semi-soft classification per FDA guidance includes cheeses with moisture content >39%. Confirm the FDA classification for your cheese.',
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
    const runStarted = useRef(false);
    const runCompleted = useRef(false);

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

    useEffect(() => {
        if (currentStep === 'results' && runStarted.current && !runCompleted.current) {
            runCompleted.current = true;
            trackToolRunCompleted('ftl-checker', 'success');
            posthog?.capture('tool_completed', { tool_id: 'ftl-checker', status: 'success' });
        }
    }, [currentStep, posthog]);

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
            toast({ title: "Link copied!", description: "Share this URL to show your self-check result. This is informational, not a compliance determination." });
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
            if (runCompleted.current) {
                runStarted.current = false;
                runCompleted.current = false;
            }
            if (!runStarted.current) {
                runStarted.current = true;
                trackToolRunStarted('ftl-checker');
                posthog?.capture('tool_started', { tool_id: 'ftl-checker' });
            }
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
    const handleStartOver = () => { runStarted.current = false; runCompleted.current = false; setSelectedCategories([]); setExemptionAnswers({}); setCurrentStep('categories'); setShowResults(false); setEmailSubmitted(false); };

    const handleEmailSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (email) {
            setEmailSubmitted(true);

            const results = getResults();

            // PostHog event for funnel analytics
            posthog?.capture('ftl_report_requested', {
                categories_selected: selectedCategories,
                covered_count: results.coveredCount,
                risk_level: results.coveredCount > 0 ? 'HIGH' : 'LOW'
            });

            // Persist lead to assessment_submissions so it survives without PostHog access.
            // Fire-and-forget: UI transitions optimistically, errors logged but not surfaced.
            const { utm_source, utm_medium, utm_campaign } = getConversionAttribution();
            submitAssessment({
                name: email.split('@')[0],
                email,
                company: 'Unknown (FTL Checker)',
                role: '',
                source: 'ftl-checker',
                utmSource: utm_source,
                utmMedium: utm_medium,
                utmCampaign: utm_campaign,
                referrer: getReferrerHostname(),
                toolInputs: {
                    selectedCategories,
                    coveredCount: results.coveredCount,
                    riskLevel: results.coveredCount > 0 ? 'HIGH' : 'LOW',
                },
            }).then((result) => {
                if (result.success) {
                    trackEmailCaptureSubmit({ form: 'lead_gate', step: 'gate', tool: 'ftl-checker', outcome: 'success' });
                } else {
                    trackEmailCaptureSubmit({
                        form: 'lead_gate', step: 'gate', tool: 'ftl-checker', outcome: 'error',
                        error_code: result.error?.includes('valid email') ? 'validation' : 'server',
                    });
                }
            }).catch(() => {
                trackEmailCaptureSubmit({ form: 'lead_gate', step: 'gate', tool: 'ftl-checker', outcome: 'error', error_code: 'server' });
                console.error('[ftl-checker] submitAssessment failed');
            });

            toast({ title: "Request received", description: "A member of our team may follow up about your FTL coverage." });
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

            await generateBrandedPDF({
                title: 'FTL Coverage Report',
                subtitle: `${results.totalSelected} categor${results.totalSelected === 1 ? 'y' : 'ies'} analyzed`,
                reportType: 'FDA FSMA 204: Food Traceability List',
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
        <div className="min-h-screen bg-re-surface-base">
            <Container width="tool" className="pt-6">
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "FTL List Checker" }
                    ]}
                />
            </Container>

            {/* Hero */}
            <section className="border-b border-re-border-subtle">
                <Container width="tool" className="py-10 text-center sm:py-16">
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                        <Badge tone="neutral" className="mb-4">
                            Free tool · no login · not a determination
                        </Badge>
                        <h1 className="font-display text-display text-re-text-primary">
                            FTL List Checker
                        </h1>
                        <p className="mx-auto mt-4 max-w-[68ch] text-body text-re-text-secondary">
                            The Food Traceability List is the list of foods. Who must keep Subpart S records is a separate question. This page does not decide either one. Verify every grouping against the current FDA FTL.
                        </p>
                        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-small text-re-text-tertiary">
                            <span className="flex items-center gap-1.5"><CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" /> No account required</span>
                            <span className="flex items-center gap-1.5"><CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" /> FDA won't enforce before July 20, 2028</span>
                        </div>
                    </motion.div>
                </Container>
            </section>

            <Container width="tool" className="py-10 sm:py-12">
                {/* Step Progress */}
                {currentStep !== 'categories' && (
                    <nav aria-label="Progress" className="mb-8 flex flex-wrap items-center justify-center gap-4">
                        {[{ num: 1, label: 'Categories', step: 'categories' }, { num: 2, label: 'Exemptions', step: 'exemptions' }, { num: 3, label: 'Results', step: 'results' }].map((s, i) => (
                            <div key={s.step} className="flex items-center gap-2">
                                {i > 0 && <span className="h-px w-8 bg-re-border" aria-hidden="true" />}
                                <div
                                    className={cn('flex items-center gap-2', currentStep === s.step ? 'text-re-text-primary' : 'text-re-text-tertiary')}
                                    aria-current={currentStep === s.step ? 'step' : undefined}
                                >
                                    <span
                                        className={cn(
                                            'flex h-6 w-6 items-center justify-center rounded-full border font-mono uppercase text-label',
                                            currentStep === s.step
                                                ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
                                                : 'border-re-border bg-re-surface-card text-re-text-tertiary'
                                        )}
                                    >
                                        {s.num}
                                    </span>
                                    <span className={cn('text-small', currentStep === s.step && 'font-medium')}>{s.label}</span>
                                </div>
                            </div>
                        ))}
                    </nav>
                )}

                <AnimatePresence mode="wait">
                    {/* Step 1: Category Selection */}
                    {currentStep === 'categories' && (
                        <motion.div key="selector" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                            <Card padding="spacious" className="mb-6">
                                <div className="mb-6 space-y-4">
                                    <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-center">
                                        <div>
                                            <h2 className="flex items-center gap-2.5 text-heading text-re-text-primary">
                                                <Search size={20} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" /> Select Your Product Categories
                                            </h2>
                                            <p className="mt-1 text-ui text-re-text-secondary">Choose all the food categories your company handles</p>
                                        </div>
                                        <div className="w-full md:w-64">
                                            <Field label="Search products (e.g. shrimp)" htmlFor="ftl-search" className="[&>label]:sr-only">
                                                <Input
                                                    type="text"
                                                    placeholder="Search products (e.g. shrimp)"
                                                    value={searchTerm}
                                                    onChange={(e) => setSearchTerm(e.target.value)}
                                                    leadingIcon={<Search strokeWidth={1.75} />}
                                                />
                                            </Field>
                                        </div>
                                    </div>

                                    {/* Filter Chips */}
                                    <div className="flex flex-wrap gap-2">
                                        {(['All', 'Seafood', 'Produce', 'Dairy', 'Eggs', 'Other'] as const).map(f => {
                                            const FilterIcon = FILTER_ICONS[f];
                                            return (
                                                <Button
                                                    key={f}
                                                    variant="secondary"
                                                    size="sm"
                                                    aria-pressed={activeFilter === f}
                                                    onClick={() => setActiveFilter(f)}
                                                    className={cn(activeFilter === f && 'bg-re-surface-inset font-semibold text-re-text-primary')}
                                                    leadingIcon={FilterIcon ? <FilterIcon strokeWidth={1.75} aria-hidden="true" /> : undefined}
                                                >
                                                    {f}
                                                </Button>
                                            );
                                        })}
                                    </div>
                                </div>

                                <div className="re-scrollbar grid max-h-[500px] grid-cols-1 gap-3 overflow-y-auto pr-2 sm:grid-cols-2">
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
                                                <button
                                                    key={category.id}
                                                    type="button"
                                                    aria-pressed={isSelected}
                                                    onClick={() => toggleCategory(category.id)}
                                                    className={pickClasses(isSelected)}
                                                >
                                                    <div className="flex items-start gap-3">
                                                        <span
                                                            className={cn(
                                                                'mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-sm border',
                                                                isSelected ? 'border-re-border-strong bg-re-surface-card' : 'border-re-border'
                                                            )}
                                                            aria-hidden="true"
                                                        >
                                                            {isSelected && <CheckCircle2 size={12} strokeWidth={1.75} className="text-re-text-primary" />}
                                                        </span>
                                                        <div className="min-w-0 flex-1">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <Icon size={14} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-re-text-tertiary" />
                                                                <span className="text-ui font-medium text-re-text-primary">{category.name}</span>
                                                                <Badge tone={category.covered ? 'success' : 'neutral'} size="sm">
                                                                    {category.covered ? 'Listed' : 'Not listed'}
                                                                </Badge>
                                                            </div>
                                                            <p className="mt-1 text-small text-re-text-tertiary">{category.examples}</p>
                                                        </div>
                                                    </div>
                                                </button>
                                            );
                                        })}
                                </div>

                                <div className="mt-6 flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
                                    <span className="text-small tabular-nums text-re-text-tertiary">{selectedCategories.length} categories selected</span>
                                    <Button
                                        size="lg"
                                        onClick={handleCheck}
                                        disabled={selectedCategories.length === 0}
                                        trailingIcon={<ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />}
                                    >
                                        Check Listed Groupings
                                    </Button>
                                </div>
                            </Card>
                        </motion.div>
                    )}

                    {/* Step 2: Exemption Wizard */}
                    {currentStep === 'exemptions' && (
                        <motion.div key="exemptions" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                            <Card padding="spacious" className="mb-6">
                                <div className="mb-6">
                                    <h2 className="flex items-center gap-2.5 text-heading text-re-text-primary">
                                        <ShieldCheck size={20} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" /> Check for Exemptions
                                    </h2>
                                    <p className="mt-1 text-ui text-re-text-secondary">Answer these questions to see if you qualify for any FSMA 204 exemptions</p>
                                </div>

                                <div className="flex flex-col gap-3">
                                    {EXEMPTION_QUESTIONS.map((q, index) => {
                                        const Icon = q.icon;
                                        const answer = exemptionAnswers[q.id];
                                        const isExpanded = showExemptionHelp === q.id;
                                        const alreadyExempt = Object.entries(exemptionAnswers).some(([id, val]) => val === true && EXEMPTION_QUESTIONS.findIndex(x => x.id === id) < index);
                                        if (alreadyExempt && answer !== true) return null;

                                        return (
                                            <div
                                                key={q.id}
                                                className={cn(
                                                    'rounded-lg border p-5',
                                                    answer === true ? 'border-re-border-strong bg-re-surface-inset' : 'border-re-border bg-re-surface-card'
                                                )}
                                            >
                                                <div className="flex items-start gap-4">
                                                    <Icon size={20} strokeWidth={1.75} aria-hidden="true" className="mt-0.5 shrink-0 text-re-text-tertiary" />
                                                    <div className="min-w-0 flex-1">
                                                        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
                                                            <div className="min-w-0">
                                                                <p className="text-ui font-medium text-re-text-primary">{q.question}</p>
                                                                <a
                                                                    href={ecfrUrl(q.citation)}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="mt-1.5 inline-block rounded-sm bg-re-surface-inset px-2 py-0.5 font-mono text-label text-re-brand no-underline"
                                                                >
                                                                    {q.citation}
                                                                </a>
                                                            </div>
                                                            <div className="flex shrink-0 items-center gap-2">
                                                                <Button
                                                                    size="sm"
                                                                    variant="secondary"
                                                                    aria-pressed={answer === true}
                                                                    className={cn(answer === true && 'bg-re-surface-inset font-semibold text-re-text-primary')}
                                                                    onClick={() => handleExemptionAnswer(q.id, true)}
                                                                >
                                                                    Yes
                                                                </Button>
                                                                <Button
                                                                    size="sm"
                                                                    variant="secondary"
                                                                    aria-pressed={answer === false}
                                                                    className={cn(answer === false && 'bg-re-surface-inset font-semibold text-re-text-primary')}
                                                                    onClick={() => handleExemptionAnswer(q.id, false)}
                                                                >
                                                                    No
                                                                </Button>
                                                                <Button
                                                                    size="icon"
                                                                    variant="ghost"
                                                                    aria-label="Show help"
                                                                    aria-expanded={isExpanded}
                                                                    onClick={() => setShowExemptionHelp(isExpanded ? null : q.id)}
                                                                >
                                                                    <HelpCircle size={16} strokeWidth={1.75} aria-hidden="true" />
                                                                </Button>
                                                            </div>
                                                        </div>
                                                        {isExpanded && (
                                                            <p className="mt-3 rounded-md bg-re-surface-inset p-2.5 text-small text-re-text-secondary">{q.helpText}</p>
                                                        )}
                                                        {answer === true && (
                                                            <div className="mt-3 flex items-center gap-2 text-small text-re-text-secondary">
                                                                <CheckCircle2 size={16} strokeWidth={1.75} aria-hidden="true" className="text-re-success" />
                                                                <span className="font-medium">You may qualify for this exemption!</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>

                                <div className="mt-6 flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
                                    <Button variant="secondary" onClick={handleBackToCategories}>← Back to Categories</Button>
                                    <div className="flex flex-col gap-3 sm:flex-row">
                                        <Button variant="secondary" onClick={handleSkipExemptions}>Skip Exemptions</Button>
                                        <Button
                                            size="lg"
                                            onClick={handleFinishExemptions}
                                            trailingIcon={<ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            See Results
                                        </Button>
                                    </div>
                                </div>
                            </Card>
                        </motion.div>
                    )}

                    {/* Step 3: Results */}
                    {currentStep === 'results' && (
                        <motion.div key="results" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                            <LeadGate
                                source="ftl-checker"
                                headline="Unlock Your Full FTL Coverage Report"
                                subheadline="See detailed category-by-category results, exemption analysis, and compliance action items."
                                ctaText="Get Full Report"
                                toolContext={{ toolInputs: { coveredCount: results.coveredCount, totalSelected: results.totalSelected, coveragePercent } }}
                                teaser={
                                    <Card padding="spacious" className="text-center">
                                        <p className="text-subheading text-re-text-primary">FSMA 204 Coverage</p>
                                        <p className="my-2 text-[3.5rem] leading-none tabular-nums text-re-text-primary">{coveragePercent}%</p>
                                        <p className="text-ui text-re-text-secondary">{results.coveredCount} of {results.totalSelected} selected categories on the FTL</p>
                                    </Card>
                                }
                            >
                                <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
                                    {/* Main Result Card */}
                                    <Card padding="spacious" className="min-w-0">
                                        <div className="mb-6 flex flex-col items-start justify-between gap-3 sm:flex-row">
                                            <div>
                                                <h2 className="text-heading text-re-text-primary">Your FTL Coverage Results</h2>
                                                <p className="mt-1 text-ui text-re-text-secondary">Based on your selected product categories</p>
                                            </div>
                                            <Button
                                                variant="secondary"
                                                onClick={handleCopyLink}
                                                leadingIcon={linkCopied
                                                    ? <Check size={16} strokeWidth={1.75} aria-hidden="true" />
                                                    : <Share2 size={16} strokeWidth={1.75} aria-hidden="true" />}
                                            >
                                                {linkCopied ? 'Link Copied!' : 'Share Results'}
                                            </Button>
                                        </div>

                                        {/* Coverage Meter */}
                                        <div className="mb-8">
                                            <div className="mb-2 flex items-center justify-between gap-3">
                                                <span className="text-subheading text-re-text-primary">FSMA 204 Coverage</span>
                                                <span className="text-title tabular-nums text-re-text-primary">{coveragePercent}%</span>
                                            </div>
                                            <div className="h-2 overflow-hidden rounded-full bg-re-surface-inset">
                                                <motion.div
                                                    initial={{ width: 0 }}
                                                    animate={{ width: `${coveragePercent}%` }}
                                                    transition={{ duration: 1, ease: 'easeOut' }}
                                                    className="h-full rounded-full bg-re-text-tertiary"
                                                />
                                            </div>
                                        </div>

                                        {/* Stats Grid */}
                                        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
                                            <Card variant="inset" padding="compact" className="text-center">
                                                <div className="text-title tabular-nums text-re-text-primary">{results.coveredCount}</div>
                                                <div className="font-mono uppercase text-label text-re-text-muted">On FTL</div>
                                            </Card>
                                            <Card variant="inset" padding="compact" className="text-center">
                                                <div className="text-title tabular-nums text-re-text-primary">{results.notCoveredCount}</div>
                                                <div className="font-mono uppercase text-label text-re-text-muted">Not on FTL</div>
                                            </Card>
                                            <Card variant="inset" padding="compact" className="text-center">
                                                <div className="text-title tabular-nums text-re-text-primary">{results.highOutbreakCount}</div>
                                                <div className="font-mono uppercase text-label text-re-text-muted">High Outbreak Frequency</div>
                                            </Card>
                                        </div>

                                        {/* Exemption Status */}
                                        {results.coveredCount > 0 && (
                                            <Callout
                                                className="mb-6"
                                                tone={results.exemptionStatus === 'EXEMPT' ? 'success' : results.exemptionStatus === 'NOT_EXEMPT' ? 'warning' : 'neutral'}
                                                role="status"
                                                icon={results.exemptionStatus === 'EXEMPT' ? ShieldCheck : results.exemptionStatus === 'NOT_EXEMPT' ? AlertTriangle : HelpCircle}
                                                title={results.exemptionStatus === 'EXEMPT' ? 'You May Be Exempt from FSMA 204!' : results.exemptionStatus === 'NOT_EXEMPT' ? 'Full FSMA 204 Requirements Apply' : 'Exemption Status Unknown'}
                                            >
                                                {results.exemptionStatus === 'EXEMPT' && results.qualifyingExemptions.map(e => (
                                                    <div key={e.id} className="mb-1 flex items-center gap-2 text-small">
                                                        <CheckCircle2 size={14} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-re-success" />
                                                        <a href={ecfrUrl(e.citation)} target="_blank" rel="noopener noreferrer" className="font-mono font-medium text-re-brand no-underline">{e.citation}</a>
                                                    </div>
                                                ))}
                                                {results.exemptionStatus === 'NOT_EXEMPT' && <p className="text-small">Based on the categories selected, your operation does not appear to qualify for a §1.1305 exemption. This is not a regulatory determination. Confirm with counsel and the FDA Exemptions &amp; Exclusions Tool before relying on it.</p>}
                                            </Callout>
                                        )}

                                        {/* Same Form Ingredient Rule */}
                                        {results.coveredCount > 0 && results.exemptionStatus !== 'EXEMPT' && (
                                            <Callout
                                                className="mb-6"
                                                tone="info"
                                                role="note"
                                                icon={AlertTriangle}
                                                title={'"Same Form" Ingredient Rule'}
                                            >
                                                <p className="text-small">If you use FTL foods as ingredients in other products (e.g., peppers in fresh salsa) and they remain in the same form (fresh, not cooked/canned), those finished products inherit FSMA 204 requirements.</p>
                                                <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list" target="_blank" rel="noopener noreferrer" className="mt-1 inline-block font-mono text-label text-re-brand no-underline">FDA Food Traceability List</a>
                                            </Callout>
                                        )}

                                        {/* Category Breakdown with CTE/KDE Details */}
                                        <h3 className="mb-4 text-subheading text-re-text-primary">Category Breakdown</h3>
                                        <div className="flex flex-col gap-2">
                                            {results.categories.map(category => (
                                                <div key={category.id} className="overflow-hidden rounded-lg border border-re-border-subtle bg-re-surface-inset">
                                                    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                                                        <div className="flex items-center gap-3">
                                                            {category.covered
                                                                ? <CheckCircle2 size={18} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-re-success" />
                                                                : <XCircle size={18} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-re-text-tertiary" />}
                                                            <span className="text-ui text-re-text-primary">{category.name}</span>
                                                        </div>
                                                        <div className="flex flex-wrap items-center gap-2">
                                                            {category.outbreakFrequency === 'HIGH' && (
                                                                <Badge tone="danger" size="sm" className="h-auto whitespace-normal py-1 text-left">Higher Outbreak Frequency</Badge>
                                                            )}
                                                            <Badge tone={category.covered ? 'success' : 'neutral'} size="sm" className="h-auto whitespace-normal py-1 text-left">
                                                                {category.covered ? 'Listed grouping. Verify' : 'Not listed. Verify'}
                                                            </Badge>
                                                        </div>
                                                    </div>
                                                    {/* CTE/KDE Requirements - Only for covered categories */}
                                                    {category.covered && category.ctes && category.ctes.length > 0 && (
                                                        <div className="border-t border-re-border-subtle bg-re-surface-card px-4 py-3">
                                                            <div className="grid grid-cols-1 gap-4">
                                                                <div>
                                                                    <div className="mb-1.5 font-mono uppercase text-label text-re-text-muted">
                                                                        Critical Tracking Event (CTE) Types Required
                                                                    </div>
                                                                    <div className="flex flex-wrap gap-1">
                                                                        {category.ctes.map(cte => (
                                                                            <Badge key={cte} tone="neutral" size="sm" className="h-auto whitespace-normal py-1 text-left">{cte}</Badge>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                                <div>
                                                                    <div className="mb-1.5 font-mono uppercase text-label text-re-text-muted">
                                                                        Key Data Element (KDE) Fields per Event
                                                                    </div>
                                                                    <div className="flex flex-wrap gap-1">
                                                                        {category.kdes.map(kde => (
                                                                            <Badge key={kde} tone="neutral" size="sm" className="h-auto whitespace-normal py-1 text-left">{kde}</Badge>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>

                                        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                                            <Button variant="secondary" onClick={handleStartOver}>← Start Over</Button>
                                            <Button
                                                variant="secondary"
                                                onClick={handleDownloadReport}
                                                disabled={isDownloading}
                                                leadingIcon={isDownloading
                                                    ? <Loader2 size={16} strokeWidth={1.75} aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
                                                    : <Download size={16} strokeWidth={1.75} aria-hidden="true" />}
                                            >
                                                {isDownloading ? 'Generating...' : 'Download PDF Report'}
                                            </Button>
                                        </div>
                                    </Card>

                                    {/* CTA Card */}
                                    <Card variant="inset" padding="spacious" className="self-start">
                                        {results.coveredCount > 0 ? (
                                            <>
                                                <AlertTriangle size={20} strokeWidth={1.75} aria-hidden="true" className="mb-3 text-re-text-tertiary" />
                                                <h3 className="mb-3 text-heading text-re-text-primary">Action Required</h3>
                                                <p className="mb-2 text-ui text-re-text-secondary">Based on your selections, <strong className="font-medium text-re-text-primary">{results.coveredCount} categor{results.coveredCount === 1 ? 'y' : 'ies'}</strong> may fall under FSMA 204 by <strong className="font-medium text-re-text-primary">July 20, 2028</strong>. This is not a regulatory determination. Verify each product against the FDA FTL.</p>
                                                <p className="mb-5 text-small text-re-text-tertiary">Some major retailers have announced their own traceability programs. Check your buyers&apos; requirements.</p>
                                                {!emailSubmitted ? (
                                                    <form onSubmit={handleEmailSubmit} className="flex flex-col gap-3">
                                                        <p className="text-ui font-medium text-re-text-primary">Request a Follow-Up Review</p>
                                                        <Field label="Enter your email" htmlFor="ftl-followup-email" className="[&>label]:sr-only">
                                                            <Input
                                                                type="email"
                                                                size="lg"
                                                                placeholder="Enter your email"
                                                                value={email}
                                                                onChange={(e) => setEmail(e.target.value)}
                                                                required
                                                            />
                                                        </Field>
                                                        <Button
                                                            type="submit"
                                                            size="lg"
                                                            className="w-full"
                                                            leadingIcon={<Mail size={16} strokeWidth={1.75} aria-hidden="true" />}
                                                        >
                                                            Request Follow-Up
                                                        </Button>
                                                    </form>
                                                ) : (
                                                    <div className="rounded-lg border border-re-border bg-re-surface-card p-4 text-center">
                                                        <CheckCircle2 size={24} strokeWidth={1.75} aria-hidden="true" className="mx-auto mb-2 text-re-success" />
                                                        <p className="text-ui font-medium text-re-text-primary">Request Received!</p>
                                                        <p className="mt-1 text-small text-re-text-tertiary">We may follow up if a review would be helpful</p>
                                                    </div>
                                                )}
                                            </>
                                        ) : (
                                            <>
                                                <CheckCircle2 size={20} strokeWidth={1.75} aria-hidden="true" className="mb-3 text-re-text-tertiary" />
                                                <h3 className="mb-3 text-heading text-re-text-primary">Good News!</h3>
                                                <p className="mb-4 text-ui text-re-text-secondary">None of your selected categories are currently on the Food Traceability List.</p>
                                                {experimentalFeaturesEnabled() && (
                                                    <Button asChild size="lg" className="w-full">
                                                        <Link href="/fsma">Learn About Retailer Requirements</Link>
                                                    </Button>
                                                )}
                                            </>
                                        )}
                                    </Card>
                                </div>

                                {/* What's Next Section */}
                                {results.coveredCount > 0 && (
                                    <Card padding="spacious" className="mt-8">
                                        <h3 className="mb-6 text-heading text-re-text-primary">What You Need to Know</h3>
                                        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                                            {[
                                                { num: 1, title: 'Critical Tracking Events (CTEs)', desc: 'You must record events for: Harvesting, Cooling, Initial Packing, First Land-Based Receiving, Shipping, Receiving, and Transformation of FTL foods.', cfrLink: 'https://www.ecfr.gov/current/title-21/section-1.1325', cfrLabel: '§1.1325 to §1.1350' },
                                                { num: 2, title: '24 Hour Response', desc: 'FDA can request your traceability data, and you must provide it in electronic format within 24 hours.', cfrLink: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)', cfrLabel: '§1.1455(c)' },
                                                { num: 3, title: 'Traceability Lot Codes (TLCs)', desc: 'Each lot must have a unique code that links all events across your supply chain.', cfrLink: 'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1320', cfrLabel: '§1.1320' },
                                            ].map(item => (
                                                <div key={item.num}>
                                                    <h4 className="mb-2 flex items-center gap-2.5 text-subheading text-re-text-primary">
                                                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-inset font-mono uppercase text-label text-re-text-secondary">{item.num}</span>
                                                        {item.title}
                                                    </h4>
                                                    <p className="text-small text-re-text-secondary">
                                                        {item.desc}
                                                        {item.cfrLink && <> (<a href={item.cfrLink} target="_blank" rel="noopener noreferrer" className="font-mono text-label text-re-brand no-underline">{item.cfrLabel}</a>)</>}
                                                    </p>
                                                </div>
                                            ))}
                                        </div>
                                    </Card>
                                )}

                                {/* Regulatory Sources Footer */}
                                <Card padding="spacious" className="mt-8">
                                    <h4 className="mb-4 flex items-center gap-2 text-subheading text-re-text-primary">
                                        <ExternalLink size={16} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" />
                                        Regulatory Sources
                                    </h4>
                                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                        <a href="https://www.ecfr.gov/current/title-21/part-1/subpart-S" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            21 CFR Part 1 Subpart S: Full Rule Text
                                        </a>
                                        <a href="https://www.federalregister.gov/documents/2022/11/21/2022-24417/requirements-for-additional-traceability-records-for-certain-foods" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            Final Rule: 87 FR 70910 (Nov 21, 2022)
                                        </a>
                                        <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            FDA Food Traceability List (Official)
                                        </a>
                                        <a href="https://www.federalregister.gov/documents/2025/08/07/2025-14967/requirements-for-additional-traceability-records-for-certain-foods-compliance-date-extension" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            Compliance Date Extension: 90 FR 38084
                                        </a>
                                        <a href="https://www.fda.gov/files/food/published/FSMA%20Rule%20for%20Food%20Traceability%20-%202024-0520-CTEs-KDEs.pdf" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            FDA CTE/KDE Reference Chart (PDF)
                                        </a>
                                        <a href="https://www.fda.gov/regulatory-information/search-fda-guidance-documents/small-entity-compliance-guide-requirements-additional-traceability-records-certain-foods-what-you" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            Small Entity Compliance Guide
                                        </a>
                                        <a href="https://collaboration.fda.gov/tefcv13" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-small text-re-brand no-underline">
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand" aria-hidden="true" />
                                            FDA Exemptions &amp; Exclusions Tool
                                        </a>
                                    </div>
                                    <p className="mt-4 text-small italic text-re-text-tertiary">
                                        This tool is for informational purposes only and does not constitute legal advice or a regulatory determination. The category list is RegEngine&apos;s interpretation of the FDA Food Traceability List; verify each product directly against the FDA FTL and consult your legal counsel for compliance decisions. Last reviewed against the FDA FTL: May 2026.
                                    </p>
                                </Card>
                            </LeadGate>
                        </motion.div>
                    )}
                </AnimatePresence>

                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['cte-mapper', 'kde-checker'].includes(t.id))}
                />
            </Container>
        </div>
    );
}
