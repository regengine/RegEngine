'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Database,
    Cpu,
    ClipboardCheck,
    Network,
    Shield,
    TrendingUp,
    ChevronRight,
    X,
    CheckCircle2,
    Circle,
    Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { DemoCompletionModal } from './DemoCompletionModal';

// Demo steps configuration
const DEMO_STEPS = [
    {
        id: 'ingest',
        label: 'Ingestion',
        path: '/ingest',
        icon: Database,
        description: 'Fetch DORA regulation from EUR-Lex'
    },
    {
        id: 'process',
        label: 'Processing',
        path: null,
        icon: Cpu,
        description: 'NLP extracts obligations and thresholds'
    },
    {
        id: 'review',
        label: 'Review',
        path: '/review',
        icon: ClipboardCheck,
        description: 'Curator reviews extracted data'
    },
    {
        id: 'graph',
        label: 'Graph',
        path: '/trace',
        icon: Network,
        description: 'Explore regulatory knowledge graph'
    },
    {
        id: 'compliance',
        label: 'Compliance',
        path: '/compliance',
        icon: Shield,
        description: 'Validate against checklists'
    },
    {
        id: 'opportunities',
        label: 'Opportunities',
        path: '/opportunities',
        icon: TrendingUp,
        description: 'Discover arbitrage & gaps'
    },
];

interface DemoContextValue {
    isActive: boolean;
    currentStep: number;
    startDemo: () => void;
    endDemo: () => void;
    nextStep: () => void;
    goToStep: (step: number) => void;
    steps: typeof DEMO_STEPS;
}

const DemoContext = createContext<DemoContextValue | null>(null);

export function useDemoProgress() {
    const context = useContext(DemoContext);
    if (!context) {
        throw new Error('useDemoProgress must be used within DemoProgressProvider');
    }
    return context;
}

interface DemoProgressProviderProps {
    children: ReactNode;
}

export function DemoProgressProvider({ children }: DemoProgressProviderProps) {
    const [isActive, setIsActive] = useState(false);
    const [currentStep, setCurrentStep] = useState(0);
    const router = useRouter();
    const pathname = usePathname();

    // Load demo state from localStorage on mount
    useEffect(() => {
        const savedState = localStorage.getItem('regengine_demo');
        if (savedState) {
            try {
                const { isActive: savedActive, currentStep: savedStep } = JSON.parse(savedState);
                setIsActive(savedActive);
                setCurrentStep(savedStep);
            } catch (e) {
                // Invalid state, reset
                localStorage.removeItem('regengine_demo');
            }
        }
    }, []);

    // Save demo state when it changes
    useEffect(() => {
        if (isActive) {
            localStorage.setItem('regengine_demo', JSON.stringify({ isActive, currentStep }));
        } else {
            localStorage.removeItem('regengine_demo');
        }
    }, [isActive, currentStep]);

    // Auto-update step based on current path
    useEffect(() => {
        if (isActive && pathname) {
            const stepIndex = DEMO_STEPS.findIndex(s => s.path === pathname);
            if (stepIndex !== -1 && stepIndex > currentStep) {
                setCurrentStep(stepIndex);
            }
        }
    }, [pathname, isActive, currentStep]);

    const startDemo = () => {
        setIsActive(true);
        setCurrentStep(0);
    };

    const endDemo = () => {
        setIsActive(false);
        setCurrentStep(0);
        localStorage.removeItem('regengine_demo');
    };

    const nextStep = () => {
        if (currentStep < DEMO_STEPS.length - 1) {
            const nextIdx = currentStep + 1;
            setCurrentStep(nextIdx);
            const nextPath = DEMO_STEPS[nextIdx].path;
            if (nextPath) {
                router.push(nextPath);
            }
        }
    };

    const goToStep = (step: number) => {
        if (step >= 0 && step < DEMO_STEPS.length) {
            setCurrentStep(step);
            const targetPath = DEMO_STEPS[step].path;
            if (targetPath) {
                router.push(targetPath);
            }
        }
    };

    return (
        <DemoContext.Provider value={{
            isActive,
            currentStep,
            startDemo,
            endDemo,
            nextStep,
            goToStep,
            steps: DEMO_STEPS,
        }}>
            {children}
            <AnimatePresence>
                {isActive && <DemoProgressBar />}
            </AnimatePresence>
        </DemoContext.Provider>
    );
}

function DemoProgressBar() {
    const { currentStep, steps, nextStep, goToStep, endDemo, startDemo } = useDemoProgress();
    const progress = ((currentStep + 1) / steps.length) * 100;
    const [showCompletionModal, setShowCompletionModal] = useState(false);

    const handleComplete = () => {
        setShowCompletionModal(true);
    };

    const handleRestart = () => {
        setShowCompletionModal(false);
        startDemo();
    };

    const handleClose = () => {
        setShowCompletionModal(false);
        endDemo();
    };

    return (
        <motion.div
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 100, opacity: 0 }}
            className="fixed bottom-0 left-0 right-0 z-50 bg-background/95 backdrop-blur border-t shadow-lg"
        >
            {/* Progress bar */}
            <div className="h-1 bg-muted">
                <motion.div
                    className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-green-500"
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                />
            </div>

            <div className="container mx-auto px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                    {/* Step indicators */}
                    <div className="hidden md:flex items-center gap-1 overflow-x-auto">
                        {steps.map((step, idx) => {
                            const Icon = step.icon;
                            const isCompleted = idx < currentStep;
                            const isCurrent = idx === currentStep;
                            const isClickable = step.path !== null;

                            return (
                                <React.Fragment key={step.id}>
                                    <button
                                        onClick={() => isClickable && goToStep(idx)}
                                        disabled={!isClickable}
                                        className={cn(
                                            "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-all",
                                            isCompleted && "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
                                            isCurrent && "bg-primary/10 text-primary font-medium",
                                            !isCompleted && !isCurrent && "text-muted-foreground",
                                            isClickable && "hover:bg-muted cursor-pointer",
                                            !isClickable && "cursor-default"
                                        )}
                                    >
                                        {isCompleted ? (
                                            <CheckCircle2 className="h-4 w-4" />
                                        ) : isCurrent ? (
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                            <Circle className="h-4 w-4" />
                                        )}
                                        <span className="hidden lg:inline">{step.label}</span>
                                    </button>
                                    {idx < steps.length - 1 && (
                                        <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                    )}
                                </React.Fragment>
                            );
                        })}
                    </div>

                    {/* Mobile step info */}
                    <div className="md:hidden flex items-center gap-2">
                        <span className="text-sm font-medium">
                            Step {currentStep + 1}/{steps.length}
                        </span>
                        <span className="text-sm text-muted-foreground">
                            {steps[currentStep].label}
                        </span>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="hidden sm:block text-sm text-muted-foreground">
                            {steps[currentStep].description}
                        </span>
                        {currentStep < steps.length - 1 ? (
                            <Button size="sm" onClick={nextStep}>
                                Next Step
                                <ChevronRight className="ml-1 h-4 w-4" />
                            </Button>
                        ) : (
                            <Button
                                size="sm"
                                variant="outline"
                                className="bg-green-500/10 text-green-600 border-green-500/30 hover:bg-green-500/20"
                                onClick={handleComplete}
                            >
                                <CheckCircle2 className="mr-1 h-4 w-4" />
                                Complete!
                            </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={endDemo}>
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </div>

            <DemoCompletionModal
                isOpen={showCompletionModal}
                onClose={handleClose}
                onRestart={handleRestart}
            />
        </motion.div>
    );
}

export { DEMO_STEPS };
