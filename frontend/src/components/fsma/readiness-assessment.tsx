'use client';

import { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import {
    CheckCircle2,
    XCircle,
    AlertTriangle,
    ArrowRight,
    ArrowLeft,
    FileCheck,
    ClipboardCheck,
    Shield,
    Clock,
    Truck,
    Package,
    Building2,
    Leaf,
} from 'lucide-react';
import { FSMA_ENFORCEMENT_DATE, FSMA_ENFORCEMENT_FRAMING } from '@/lib/fsma-enforcement';
import { trackReadinessAssessmentSubmit, trackToolRunCompleted, trackToolRunStarted } from '@/lib/conversion-events';

// Food Traceability List categories — synced with the final FDA FTL as implemented
// in src/app/tools/ftl-checker/components/FTLCheckerClient.tsx (source of truth)
const FTL_CATEGORIES = [
    { id: 'leafy-greens-fresh', name: 'Leafy Greens (fresh, intact)', examples: 'Whole leaf lettuce, spinach bunches, kale, arugula, chard, collard greens', icon: Leaf },
    { id: 'leafy-greens-fresh-cut', name: 'Leafy Greens (fresh-cut)', examples: 'Bagged salad mix, spring mix, pre-washed spinach, chopped romaine', icon: Leaf },
    { id: 'tomatoes', name: 'Tomatoes', examples: 'Fresh tomatoes (not canned or dried)', icon: Package },
    { id: 'peppers', name: 'Peppers', examples: 'Bell peppers, jalapeños, chili peppers (fresh)', icon: Package },
    { id: 'cucumbers', name: 'Cucumbers', examples: 'Fresh cucumbers', icon: Package },
    { id: 'herbs', name: 'Fresh Herbs', examples: 'Cilantro, basil, parsley (dill exempt per § 1.1305(e))', icon: Leaf },
    { id: 'melons', name: 'Melons', examples: 'Cantaloupe, honeydew, watermelon', icon: Package },
    { id: 'tropical-fruits', name: 'Tropical Tree Fruits', examples: 'Mangoes, papayas, mamey, guava (not banana, avocado, citrus)', icon: Package },
    { id: 'sprouts', name: 'Sprouts', examples: 'Alfalfa, bean, broccoli sprouts', icon: Leaf },
    { id: 'fresh-cut-fruits', name: 'Fresh-Cut Fruits', examples: 'Pre-cut fruit mixes, fruit cups', icon: Package },
    { id: 'fresh-cut-vegetables', name: 'Fresh-Cut Vegetables (non-leafy)', examples: 'Veggie trays, pre-cut carrots, celery sticks, broccoli florets', icon: Package },
    { id: 'finfish-histamine', name: 'Finfish — Scombrotoxin/Histamine-Forming', examples: 'Tuna, mackerel, mahi-mahi, bluefish, amberjack', icon: Package },
    { id: 'finfish-ciguatoxin', name: 'Finfish — Ciguatoxin-Associated', examples: 'Barracuda, grouper, snapper, moray eel', icon: Package },
    { id: 'finfish-other', name: 'Finfish — Other (fresh/frozen)', examples: 'Salmon, cod, halibut, tilapia, trout', icon: Package },
    { id: 'finfish-smoked', name: 'Smoked Finfish', examples: 'Smoked salmon, lox, kippered herring, smoked trout', icon: Package },
    { id: 'crustaceans', name: 'Crustaceans', examples: 'Shrimp, crab, lobster, crawfish', icon: Package },
    { id: 'molluscan-shellfish', name: 'Molluscan Shellfish (bivalves)', examples: 'Oysters, clams, mussels, scallops', icon: Package },
    { id: 'deli-salads', name: 'Ready-to-Eat Deli Salads', examples: 'Egg salad, seafood salad, pasta salad, potato salad', icon: Package },
    { id: 'eggs', name: 'Shell Eggs', examples: 'Shell eggs of domesticated chickens (farms with fewer than 3,000 laying hens exempt)', icon: Package },
    { id: 'nut-butters', name: 'Nut Butters', examples: 'Peanut butter, almond butter', icon: Package },
    { id: 'cheese-fresh-soft', name: 'Fresh Soft Cheese', examples: 'Queso fresco, ricotta, cottage cheese, cream cheese', icon: Package },
    { id: 'cheese-soft-ripened', name: 'Soft Ripened & Semi-Soft Cheese', examples: 'Brie, camembert, monterey jack, muenster, feta', icon: Package },
    { id: 'cheese-unpasteurized', name: 'Cheese Made from Unpasteurized Milk (non-hard)', examples: 'Raw-milk brie, raw-milk feta, artisanal raw-milk soft cheeses', icon: Package },
];

// Critical Tracking Events (CTEs)
const CTES = [
    { id: 'harvesting', name: 'Harvesting (§1.1325)', description: 'Harvesting of raw agricultural commodities' },
    { id: 'cooling', name: 'Cooling (§1.1325)', description: 'Cooling of an RAC before initial packing (combined with Harvesting in §1.1325)' },
    { id: 'initial_packing', name: 'Initial Packing (§1.1330)', description: 'Initial packing of a raw agricultural commodity (other than food obtained from a fishing vessel)' },
    { id: 'first_receiver', name: 'First Land-Based Receiving (§1.1335) — Seafood', description: 'First land-based receipt of food obtained directly from a fishing vessel. Applies only to seafood obtained from a fishing vessel — non-seafood importers perform §1.1345 Receiving, not FLBR.' },
    { id: 'shipping', name: 'Shipping (§1.1340)', description: 'Sending food from one location to another' },
    { id: 'receiving', name: 'Receiving (§1.1345)', description: 'Receipt of food at a facility. Subject to the §1.1305(j) exemption for restaurants and retail food establishments selling food directly to consumers.' },
    { id: 'transformation', name: 'Transformation (§1.1350)', description: 'Manufacturing, processing, or changing a food into a new traceability lot' },
];

// Key Data Elements (KDEs)
const KDES = [
    { id: 'tlc', name: 'Traceability Lot Code (TLC)', description: 'Unique code to identify a batch' },
    { id: 'gln', name: 'Location Identifier (GLN)', description: 'Global Location Number for facilities' },
    { id: 'date', name: 'Event Date/Time', description: 'When the event occurred' },
    { id: 'quantity', name: 'Quantity & Unit', description: 'Amount of product' },
    { id: 'reference', name: 'Reference Document', description: 'Bill of lading, invoice, etc.' },
    { id: 'product', name: 'Product Description', description: 'What the food is' },
];

interface AssessmentStep {
    id: string;
    title: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
}

const ASSESSMENT_STEPS: AssessmentStep[] = [
    { id: 'products', title: 'Product Coverage', description: 'Which FTL products do you handle?', icon: Package },
    { id: 'role', title: 'Supply Chain Role', description: 'What is your role in the supply chain?', icon: Building2 },
    { id: 'ctes', title: 'Event Tracking', description: 'Which CTEs do you currently track?', icon: ClipboardCheck },
    { id: 'kdes', title: 'Data Elements', description: 'Which KDEs do you capture?', icon: FileCheck },
    { id: 'systems', title: 'Systems & Processes', description: 'Your current traceability capabilities', icon: Shield },
    { id: 'results', title: 'Readiness Score', description: 'Your FSMA 204 compliance readiness', icon: CheckCircle2 },
];

const SUPPLY_CHAIN_ROLES = [
    { id: 'grower', name: 'Grower/Farmer', description: 'Grow or harvest raw commodities' },
    { id: 'processor', name: 'Processor/Packer', description: 'Process, pack, or transform food' },
    { id: 'distributor', name: 'Distributor', description: 'Distribute or warehouse food' },
    { id: 'retailer', name: 'Retailer', description: 'Sell food to consumers' },
    { id: 'restaurant', name: 'Restaurant/Foodservice', description: 'Prepare and serve food' },
    { id: 'importer', name: 'Importer', description: 'Import food into the US' },
];

const SYSTEM_QUESTIONS = [
    { id: 'electronic', question: 'Do you maintain traceability records electronically?', weight: 15 },
    { id: '24hr', question: 'Can you produce records within 24 hours if requested by FDA?', weight: 20 },
    { id: 'lot-tracking', question: 'Do you use unique lot codes throughout your operation?', weight: 15 },
    { id: 'supplier', question: 'Do you collect traceability data from suppliers?', weight: 15 },
    { id: 'customer', question: 'Do you share traceability data with customers?', weight: 10 },
    { id: 'training', question: 'Have your staff been trained on FSMA 204 requirements?', weight: 10 },
    { id: 'sop', question: 'Do you have written SOPs for traceability?', weight: 10 },
    { id: 'testing', question: 'Have you conducted mock recall drills?', weight: 5 },
];

/** One selected-row recipe for every pick list in the assessment (SPEC §4). */
const selectableClasses = (selected: boolean, padding: string) =>
    cn(
        'w-full rounded-lg border text-left transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none',
        padding,
        selected
            ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
            : 'border-re-border bg-re-surface-card text-re-text-secondary hover:border-re-border-strong hover:bg-re-surface-inset'
    );

export function FSMA204Assessment() {
    const [currentStep, setCurrentStep] = useState(0);
    const resultTracked = useRef(false);
    const toolRunStarted = useRef(false);
    const [selectedProducts, setSelectedProducts] = useState<string[]>([]);
    const [selectedRole, setSelectedRole] = useState<string | null>(null);
    const [selectedCTEs, setSelectedCTEs] = useState<string[]>([]);
    const [selectedKDEs, setSelectedKDEs] = useState<string[]>([]);
    const [systemAnswers, setSystemAnswers] = useState<Record<string, boolean>>({});

    const progress = ((currentStep + 1) / ASSESSMENT_STEPS.length) * 100;

    const toggleProduct = (id: string) => {
        if (window.location.pathname === '/tools/self-reported-checklist' && !toolRunStarted.current) {
            toolRunStarted.current = true;
            trackToolRunStarted('self-reported-checklist');
        }
        setSelectedProducts(prev =>
            prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
        );
    };

    const toggleCTE = (id: string) => {
        setSelectedCTEs(prev =>
            prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
        );
    };

    const toggleKDE = (id: string) => {
        setSelectedKDEs(prev =>
            prev.includes(id) ? prev.filter(k => k !== id) : [...prev, id]
        );
    };

    const toggleSystemAnswer = (id: string) => {
        setSystemAnswers(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const calculateScore = () => {
        let score = 0;
        let maxScore = 100;

        // Products covered (up to 10 points)
        if (selectedProducts.length > 0) score += Math.min(10, selectedProducts.length * 2);

        // Role selected (5 points)
        if (selectedRole) score += 5;

        // CTEs tracked (up to 25 points)
        const cteScore = (selectedCTEs.length / CTES.length) * 25;
        score += cteScore;

        // KDEs captured (up to 25 points)
        const kdeScore = (selectedKDEs.length / KDES.length) * 25;
        score += kdeScore;

        // System questions (up to 35 points based on weights)
        SYSTEM_QUESTIONS.forEach(q => {
            if (systemAnswers[q.id]) {
                score += q.weight * 0.35;
            }
        });

        return Math.round(score);
    };

    const getReadinessLevel = (score: number): { level: string; tone: BadgeTone; icon: typeof CheckCircle2 } => {
        if (score >= 80) return { level: 'No gaps indicated', tone: 'success', icon: CheckCircle2 };
        if (score >= 60) return { level: 'Few gaps indicated', tone: 'warning', icon: AlertTriangle };
        if (score >= 40) return { level: 'Several gaps indicated', tone: 'warning', icon: AlertTriangle };
        return { level: 'Many gaps indicated', tone: 'danger', icon: XCircle };
    };

    const canProceed = () => {
        switch (currentStep) {
            case 0: return selectedProducts.length > 0;
            case 1: return selectedRole !== null;
            case 2: return selectedCTEs.length > 0;
            case 3: return selectedKDEs.length > 0;
            case 4: return Object.keys(systemAnswers).length > 0;
            default: return true;
        }
    };

    const renderStepContent = () => {
        switch (currentStep) {
            case 0:
                return (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        {FTL_CATEGORIES.map(category => {
                            const Icon = category.icon;
                            const isSelected = selectedProducts.includes(category.id);
                            return (
                                <button
                                    key={category.id}
                                    onClick={() => toggleProduct(category.id)}
                                    aria-pressed={isSelected}
                                    className={selectableClasses(isSelected, 'p-3')}
                                >
                                    <div className="mb-1 flex items-center gap-2">
                                        <Icon className={cn('h-4 w-4 shrink-0', isSelected ? 'text-re-text-primary' : 'text-re-text-tertiary')} strokeWidth={1.75} aria-hidden="true" />
                                        <span className="text-ui font-medium">{category.name}</span>
                                    </div>
                                    <p className="line-clamp-2 text-small text-re-text-tertiary">{category.examples}</p>
                                </button>
                            );
                        })}
                    </div>
                );

            case 1:
                return (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        {SUPPLY_CHAIN_ROLES.map(role => {
                            const isSelected = selectedRole === role.id;
                            return (
                                <button
                                    key={role.id}
                                    onClick={() => setSelectedRole(role.id)}
                                    aria-pressed={isSelected}
                                    className={selectableClasses(isSelected, 'p-4')}
                                >
                                    <div className="mb-1 text-ui font-medium">{role.name}</div>
                                    <p className="text-small text-re-text-tertiary">{role.description}</p>
                                </button>
                            );
                        })}
                    </div>
                );

            case 2:
                return (
                    <div className="space-y-3">
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Critical Tracking Events (CTEs) are key points where traceability data must be captured.
                        </p>
                        {CTES.map(cte => {
                            const isSelected = selectedCTEs.includes(cte.id);
                            return (
                                <button
                                    key={cte.id}
                                    onClick={() => toggleCTE(cte.id)}
                                    aria-pressed={isSelected}
                                    className={cn(selectableClasses(isSelected, 'p-4'), 'flex items-center gap-4')}
                                >
                                    <span className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-full border', isSelected ? 'border-re-border-strong' : 'border-re-border')} aria-hidden="true">
                                        {isSelected && <CheckCircle2 className="h-4 w-4 text-re-text-primary" strokeWidth={1.75} />}
                                    </span>
                                    <div>
                                        <div className="text-ui font-medium">{cte.name}</div>
                                        <p className="text-small text-re-text-tertiary">{cte.description}</p>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                );

            case 3:
                return (
                    <div className="space-y-3">
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Key Data Elements (KDEs) are the specific information required at each CTE.
                        </p>
                        {KDES.map(kde => {
                            const isSelected = selectedKDEs.includes(kde.id);
                            return (
                                <button
                                    key={kde.id}
                                    onClick={() => toggleKDE(kde.id)}
                                    aria-pressed={isSelected}
                                    className={cn(selectableClasses(isSelected, 'p-4'), 'flex items-center gap-4')}
                                >
                                    <span className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-full border', isSelected ? 'border-re-border-strong' : 'border-re-border')} aria-hidden="true">
                                        {isSelected && <CheckCircle2 className="h-4 w-4 text-re-text-primary" strokeWidth={1.75} />}
                                    </span>
                                    <div>
                                        <div className="text-ui font-medium">{kde.name}</div>
                                        <p className="text-small text-re-text-tertiary">{kde.description}</p>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                );

            case 4:
                return (
                    <div className="space-y-3">
                        {SYSTEM_QUESTIONS.map(q => {
                            const isYes = systemAnswers[q.id];
                            return (
                                <div
                                    key={q.id}
                                    className="flex flex-col gap-3 rounded-lg border border-re-border bg-re-surface-card p-4 sm:flex-row sm:items-center sm:justify-between"
                                >
                                    <span className="pr-4 text-ui text-re-text-secondary">{q.question}</span>
                                    <div className="flex shrink-0 gap-2">
                                        <Button
                                            size="sm"
                                            variant="secondary"
                                            aria-pressed={isYes === true}
                                            className={cn(isYes === true && 'bg-re-surface-inset font-semibold text-re-text-primary')}
                                            onClick={() => setSystemAnswers(prev => ({ ...prev, [q.id]: true }))}
                                        >
                                            Yes
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="secondary"
                                            aria-pressed={isYes === false}
                                            className={cn(isYes === false && 'bg-re-surface-inset font-semibold text-re-text-primary')}
                                            onClick={() => setSystemAnswers(prev => ({ ...prev, [q.id]: false }))}
                                        >
                                            No
                                        </Button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                );

            case 5:
                const score = calculateScore();
                const readiness = getReadinessLevel(score);
                const ReadinessIcon = readiness.icon;
                return (
                    <div className="space-y-6">
                        {/* Score Display */}
                        <div className="py-8 text-center">
                            <div className="mb-4 inline-flex h-32 w-32 items-center justify-center rounded-full border border-re-border bg-re-surface-inset">
                                <div className="text-center">
                                    <span className="text-title tabular-nums text-re-text-primary">{score}</span>
                                    <span className="text-ui text-re-text-tertiary">/100</span>
                                </div>
                            </div>
                            <div className="flex items-center justify-center">
                                <Badge tone={readiness.tone}>
                                    <ReadinessIcon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                    {readiness.level}
                                </Badge>
                            </div>
                        </div>

                        {/* Breakdown */}
                        <div className="grid grid-cols-2 gap-4">
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Package className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="font-mono uppercase text-label text-re-text-muted">Products</span>
                                    </div>
                                    <p className="text-title tabular-nums text-re-text-primary">{selectedProducts.length}</p>
                                    <p className="text-small text-re-text-tertiary">FTL categories covered</p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <ClipboardCheck className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="font-mono uppercase text-label text-re-text-muted">CTEs</span>
                                    </div>
                                    <p className="text-title tabular-nums text-re-text-primary">{selectedCTEs.length}/{CTES.length}</p>
                                    <p className="text-small text-re-text-tertiary">Events tracked</p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <FileCheck className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="font-mono uppercase text-label text-re-text-muted">KDEs</span>
                                    </div>
                                    <p className="text-title tabular-nums text-re-text-primary">{selectedKDEs.length}/{KDES.length}</p>
                                    <p className="text-small text-re-text-tertiary">Data elements captured</p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Shield className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="font-mono uppercase text-label text-re-text-muted">Systems</span>
                                    </div>
                                    <p className="text-title tabular-nums text-re-text-primary">
                                        {Object.values(systemAnswers).filter(Boolean).length}/{SYSTEM_QUESTIONS.length}
                                    </p>
                                    <p className="text-small text-re-text-tertiary">Capabilities in place</p>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Recommendations */}
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle>Recommendations</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {selectedCTEs.length < CTES.length && (
                                    <div className="flex items-start gap-2 text-ui text-re-text-secondary">
                                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                        <span>Implement tracking for missing CTEs: {CTES.filter(c => !selectedCTEs.includes(c.id)).map(c => c.name).join(', ')}</span>
                                    </div>
                                )}
                                {selectedKDEs.length < KDES.length && (
                                    <div className="flex items-start gap-2 text-ui text-re-text-secondary">
                                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                        <span>Capture missing KDEs: {KDES.filter(k => !selectedKDEs.includes(k.id)).map(k => k.name).join(', ')}</span>
                                    </div>
                                )}
                                {!systemAnswers['electronic'] && (
                                    <div className="flex items-start gap-2 text-ui text-re-text-secondary">
                                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                        <span>Transition to electronic record-keeping for faster FDA response</span>
                                    </div>
                                )}
                                {!systemAnswers['24hr'] && (
                                    <div className="flex items-start gap-2 text-ui text-re-text-secondary">
                                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                        <span>Gap indicated: ability to produce records within 24 hours of an FDA request — review your retrieval workflow.</span>
                                    </div>
                                )}
                                {!systemAnswers['testing'] && (
                                    <div className="flex items-start gap-2 text-ui text-re-text-secondary">
                                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                        <span>Conduct mock recall drills to test your traceability system</span>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Enforcement Reminder */}
                        <Callout
                            tone="info"
                            icon={Clock}
                            role="note"
                            title={`FDA enforcement begins ${FSMA_ENFORCEMENT_DATE}`}
                        >
                            {FSMA_ENFORCEMENT_FRAMING}
                        </Callout>
                    </div>
                );

            default:
                return null;
        }
    };

    const step = ASSESSMENT_STEPS[currentStep];
    const StepIcon = step.icon;

    return (
        <Card className="mx-auto w-full max-w-4xl">
            <CardHeader>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                        <span aria-hidden="true" className="shrink-0 text-re-text-tertiary [&_svg]:size-5 [&_svg]:stroke-[1.75]">
                            <StepIcon className="h-5 w-5" />
                        </span>
                        <div>
                            <CardTitle>{step.title}</CardTitle>
                            <CardDescription>{step.description}</CardDescription>
                        </div>
                    </div>
                    <Badge tone="neutral" mono>
                        Step {currentStep + 1} of {ASSESSMENT_STEPS.length}
                    </Badge>
                </div>
                <Progress value={progress} className="h-2" />
            </CardHeader>

            <CardContent className="min-h-[400px]">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={currentStep}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        transition={{ duration: 0.2 }}
                    >
                        {renderStepContent()}
                    </motion.div>
                </AnimatePresence>
            </CardContent>

            <CardFooter className="flex justify-between">
                <Button
                    variant="secondary"
                    onClick={() => setCurrentStep(prev => prev - 1)}
                    disabled={currentStep === 0}
                    leadingIcon={<ArrowLeft strokeWidth={1.75} aria-hidden="true" />}
                >
                    Back
                </Button>

                {currentStep < ASSESSMENT_STEPS.length - 1 ? (
                    <Button
                        onClick={() => {
                            if (currentStep === ASSESSMENT_STEPS.length - 2 && !resultTracked.current) {
                                // This assessment scores locally; entering the result is its submit action.
                                trackReadinessAssessmentSubmit({ outcome: 'success' });
                                if (toolRunStarted.current) trackToolRunCompleted('self-reported-checklist', 'success');
                                resultTracked.current = true;
                            }
                            setCurrentStep(prev => prev + 1);
                        }}
                        disabled={!canProceed()}
                        trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                    >
                        Next
                    </Button>
                ) : (
                    <Button onClick={() => { resultTracked.current = false; toolRunStarted.current = false; setCurrentStep(0); }}>
                        Start Over
                    </Button>
                )}
            </CardFooter>
        </Card>
    );
}
