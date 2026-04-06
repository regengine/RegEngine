'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
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

// Food Traceability List categories (Verified against FDA official sources)
const FTL_CATEGORIES = [
    { id: 'leafy-greens', name: 'Leafy Greens (including fresh-cut)', examples: 'Lettuce, spinach, kale, arugula, spring mix', icon: Leaf },
    { id: 'tomatoes', name: 'Fresh Tomatoes', examples: 'Vine-ripe, Roma, cherry, grape tomatoes', icon: Package },
    { id: 'peppers', name: 'Fresh Peppers', examples: 'Bell peppers, jalapeños, hot peppers', icon: Package },
    { id: 'cucumbers', name: 'Fresh Cucumbers', examples: 'Slicing, pickling, English cucumbers', icon: Package },
    { id: 'herbs', name: 'Fresh Herbs', examples: 'Cilantro, basil, parsley (dill exempt per § 1.1305(e))', icon: Leaf },
    { id: 'melons', name: 'Melons', examples: 'Cantaloupe, honeydew, watermelon', icon: Package },
    { id: 'tropical', name: 'Tropical Tree Fruits', examples: 'Mango, papaya, mamey (not banana, avocado, citrus)', icon: Package },
    { id: 'sprouts', name: 'Sprouts', examples: 'Alfalfa, bean, broccoli sprouts', icon: Leaf },
    { id: 'fresh-cut-fruits', name: 'Fresh-Cut Fruits', examples: 'Pre-cut fruit mixes, fruit cups', icon: Package },
    { id: 'fresh-cut-vegetables', name: 'Fresh-Cut Vegetables (non-leafy)', examples: 'Veggie trays, pre-cut carrots, celery', icon: Package },
    { id: 'deli-salads', name: 'Ready-to-Eat Deli Salads', examples: 'Egg salad, seafood salad, pasta salad', icon: Package },
    { id: 'finfish', name: 'Finfish (including smoked)', examples: 'Salmon, tuna, cod, smoked salmon, lox', icon: Package },
    { id: 'crustaceans', name: 'Crustaceans', examples: 'Shrimp, crab, lobster, crawfish', icon: Package },
    { id: 'molluscan-shellfish', name: 'Molluscan Shellfish (bivalves)', examples: 'Oysters, clams, mussels, scallops', icon: Package },
    { id: 'nut-butters', name: 'Nut Butters', examples: 'Peanut butter, almond butter', icon: Package },
    { id: 'eggs', name: 'Shell Eggs', examples: 'Chicken eggs, duck eggs', icon: Package },
    { id: 'cheese', name: 'Cheeses (other than hard cheeses)', examples: 'Brie, Camembert, queso fresco, cottage, ricotta', icon: Package },
];

// Critical Tracking Events (CTEs)
const CTES = [
    { id: 'harvesting', name: 'Harvesting', description: 'Harvesting of raw agricultural commodities' },
    { id: 'cooling', name: 'Cooling', description: 'Cooling before initial packing' },
    { id: 'initial_packing', name: 'Initial Packing', description: 'Initial packing of raw agricultural commodities' },
    { id: 'first_receiver', name: 'First Land-Based Receiving', description: 'First receipt of food at a US facility from a fishing vessel or import' },
    { id: 'shipping', name: 'Shipping', description: 'Sending food from one location to another' },
    { id: 'receiving', name: 'Receiving', description: 'Receipt of food at a facility' },
    { id: 'transformation', name: 'Transformation', description: 'Manufacturing, processing, or changing a food' },
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

export function FSMA204Assessment() {
    const [currentStep, setCurrentStep] = useState(0);
    const [selectedProducts, setSelectedProducts] = useState<string[]>([]);
    const [selectedRole, setSelectedRole] = useState<string | null>(null);
    const [selectedCTEs, setSelectedCTEs] = useState<string[]>([]);
    const [selectedKDEs, setSelectedKDEs] = useState<string[]>([]);
    const [systemAnswers, setSystemAnswers] = useState<Record<string, boolean>>({});

    const progress = ((currentStep + 1) / ASSESSMENT_STEPS.length) * 100;

    const toggleProduct = (id: string) => {
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

    const getReadinessLevel = (score: number) => {
        if (score >= 80) return { level: 'Ready', color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 };
        if (score >= 60) return { level: 'Partially Ready', color: 'text-amber-600', bg: 'bg-amber-100', icon: AlertTriangle };
        if (score >= 40) return { level: 'Needs Improvement', color: 'text-orange-600', bg: 'bg-orange-100', icon: AlertTriangle };
        return { level: 'Not Ready', color: 'text-red-600', bg: 'bg-red-100', icon: XCircle };
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
                                    className={`p-3 rounded-lg border text-left transition-all ${isSelected
                                        ? 'border-primary bg-primary/10 ring-2 ring-primary'
                                        : 'border-border hover:border-primary/50 hover:bg-muted/50'
                                        }`}
                                >
                                    <div className="flex items-center gap-2 mb-1">
                                        <Icon className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                                        <span className="font-medium text-sm">{category.name}</span>
                                    </div>
                                    <p className="text-xs text-muted-foreground line-clamp-2">{category.examples}</p>
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
                                    className={`p-4 rounded-lg border text-left transition-all ${isSelected
                                        ? 'border-primary bg-primary/10 ring-2 ring-primary'
                                        : 'border-border hover:border-primary/50 hover:bg-muted/50'
                                        }`}
                                >
                                    <div className="font-medium mb-1">{role.name}</div>
                                    <p className="text-xs text-muted-foreground">{role.description}</p>
                                </button>
                            );
                        })}
                    </div>
                );

            case 2:
                return (
                    <div className="space-y-3">
                        <p className="text-sm text-muted-foreground mb-4">
                            Critical Tracking Events (CTEs) are key points where traceability data must be captured.
                        </p>
                        {CTES.map(cte => {
                            const isSelected = selectedCTEs.includes(cte.id);
                            return (
                                <button
                                    key={cte.id}
                                    onClick={() => toggleCTE(cte.id)}
                                    className={`w-full p-4 rounded-lg border text-left transition-all flex items-center gap-4 ${isSelected
                                        ? 'border-primary bg-primary/10'
                                        : 'border-border hover:border-primary/50'
                                        }`}
                                >
                                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${isSelected ? 'border-primary bg-primary' : 'border-muted-foreground'
                                        }`}>
                                        {isSelected && <CheckCircle2 className="h-4 w-4 text-white" />}
                                    </div>
                                    <div>
                                        <div className="font-medium">{cte.name}</div>
                                        <p className="text-sm text-muted-foreground">{cte.description}</p>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                );

            case 3:
                return (
                    <div className="space-y-3">
                        <p className="text-sm text-muted-foreground mb-4">
                            Key Data Elements (KDEs) are the specific information required at each CTE.
                        </p>
                        {KDES.map(kde => {
                            const isSelected = selectedKDEs.includes(kde.id);
                            return (
                                <button
                                    key={kde.id}
                                    onClick={() => toggleKDE(kde.id)}
                                    className={`w-full p-4 rounded-lg border text-left transition-all flex items-center gap-4 ${isSelected
                                        ? 'border-primary bg-primary/10'
                                        : 'border-border hover:border-primary/50'
                                        }`}
                                >
                                    <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${isSelected ? 'border-primary bg-primary' : 'border-muted-foreground'
                                        }`}>
                                        {isSelected && <CheckCircle2 className="h-4 w-4 text-white" />}
                                    </div>
                                    <div>
                                        <div className="font-medium">{kde.name}</div>
                                        <p className="text-sm text-muted-foreground">{kde.description}</p>
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
                                    className="flex items-center justify-between p-4 rounded-lg border"
                                >
                                    <span className="text-sm pr-4">{q.question}</span>
                                    <div className="flex gap-2 shrink-0">
                                        <Button
                                            size="sm"
                                            variant={isYes === true ? 'default' : 'outline'}
                                            onClick={() => setSystemAnswers(prev => ({ ...prev, [q.id]: true }))}
                                        >
                                            Yes
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant={isYes === false ? 'destructive' : 'outline'}
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
                        <div className="text-center py-8">
                            <div className={`inline-flex items-center justify-center w-32 h-32 rounded-full ${readiness.bg} mb-4`}>
                                <div className="text-center">
                                    <span className={`text-4xl font-bold ${readiness.color}`}>{score}</span>
                                    <span className="text-lg text-muted-foreground">/100</span>
                                </div>
                            </div>
                            <div className={`flex items-center justify-center gap-2 ${readiness.color}`}>
                                <ReadinessIcon className="h-5 w-5" />
                                <span className="text-xl font-semibold">{readiness.level}</span>
                            </div>
                        </div>

                        {/* Breakdown */}
                        <div className="grid grid-cols-2 gap-4">
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Package className="h-4 w-4 text-primary" />
                                        <span className="font-medium">Products</span>
                                    </div>
                                    <p className="text-2xl font-bold">{selectedProducts.length}</p>
                                    <p className="text-xs text-muted-foreground">FTL categories covered</p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <ClipboardCheck className="h-4 w-4 text-primary" />
                                        <span className="font-medium">CTEs</span>
                                    </div>
                                    <p className="text-2xl font-bold">{selectedCTEs.length}/{CTES.length}</p>
                                    <p className="text-xs text-muted-foreground">Events tracked</p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <FileCheck className="h-4 w-4 text-primary" />
                                        <span className="font-medium">KDEs</span>
                                    </div>
                                    <p className="text-2xl font-bold">{selectedKDEs.length}/{KDES.length}</p>
                                    <p className="text-xs text-muted-foreground">Data elements captured</p>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Shield className="h-4 w-4 text-primary" />
                                        <span className="font-medium">Systems</span>
                                    </div>
                                    <p className="text-2xl font-bold">
                                        {Object.values(systemAnswers).filter(Boolean).length}/{SYSTEM_QUESTIONS.length}
                                    </p>
                                    <p className="text-xs text-muted-foreground">Capabilities in place</p>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Recommendations */}
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-lg">Recommendations</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {selectedCTEs.length < CTES.length && (
                                    <div className="flex items-start gap-2 text-sm">
                                        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5" />
                                        <span>Implement tracking for missing CTEs: {CTES.filter(c => !selectedCTEs.includes(c.id)).map(c => c.name).join(', ')}</span>
                                    </div>
                                )}
                                {selectedKDEs.length < KDES.length && (
                                    <div className="flex items-start gap-2 text-sm">
                                        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5" />
                                        <span>Capture missing KDEs: {KDES.filter(k => !selectedKDEs.includes(k.id)).map(k => k.name).join(', ')}</span>
                                    </div>
                                )}
                                {!systemAnswers['electronic'] && (
                                    <div className="flex items-start gap-2 text-sm">
                                        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5" />
                                        <span>Transition to electronic record-keeping for faster FDA response</span>
                                    </div>
                                )}
                                {!systemAnswers['24hr'] && (
                                    <div className="flex items-start gap-2 text-sm">
                                        <XCircle className="h-4 w-4 text-red-500 mt-0.5" />
                                        <span className="font-medium">Critical: Develop capability to produce records within 24 hours</span>
                                    </div>
                                )}
                                {!systemAnswers['testing'] && (
                                    <div className="flex items-start gap-2 text-sm">
                                        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5" />
                                        <span>Conduct mock recall drills to test your traceability system</span>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Deadline Reminder */}
                        <Card className="border-primary/50 bg-primary/5">
                            <CardContent className="pt-4">
                                <div className="flex items-center gap-3">
                                    <Clock className="h-8 w-8 text-primary" />
                                    <div>
                                        <p className="font-semibold">Compliance Deadline: July 2028</p>
                                        <p className="text-sm text-muted-foreground">
                                            Approximately 30 months to achieve full compliance
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                );

            default:
                return null;
        }
    };

    const step = ASSESSMENT_STEPS[currentStep];
    const StepIcon = step.icon;

    return (
        <Card className="w-full max-w-4xl mx-auto">
            <CardHeader>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900">
                            <StepIcon className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div>
                            <CardTitle>{step.title}</CardTitle>
                            <CardDescription>{step.description}</CardDescription>
                        </div>
                    </div>
                    <Badge variant="outline">
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
                    variant="outline"
                    onClick={() => setCurrentStep(prev => prev - 1)}
                    disabled={currentStep === 0}
                >
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back
                </Button>

                {currentStep < ASSESSMENT_STEPS.length - 1 ? (
                    <Button
                        onClick={() => setCurrentStep(prev => prev + 1)}
                        disabled={!canProceed()}
                    >
                        Next
                        <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                ) : (
                    <Button onClick={() => setCurrentStep(0)}>
                        Start Over
                    </Button>
                )}
            </CardFooter>
        </Card>
    );
}
