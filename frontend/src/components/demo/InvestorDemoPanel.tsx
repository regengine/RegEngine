'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    Rocket,
    Play,
    CheckCircle,
    Clock,
    DollarSign,
    Shield,
    Building,
    Truck,
    Store,
    ArrowRight,
    Users,
    TrendingUp,
} from 'lucide-react';

interface DemoStep {
    id: number;
    title: string;
    description: string;
    icon: React.ReactNode;
    metrics?: { label: string; value: string }[];
    duration: string;
}

const DEMO_STEPS: DemoStep[] = [
    {
        id: 1,
        title: 'Customer Onboarding',
        description: 'Self-service signup with API key generation',
        icon: <Users className="h-5 w-5" />,
        metrics: [
            { label: 'Time to value', value: '< 2 minutes' },
            { label: 'No sales call', value: 'Required' },
        ],
        duration: '30s',
    },
    {
        id: 2,
        title: 'Data Ingestion',
        description: 'Load supply chain topology and lot data',
        icon: <Building className="h-5 w-5" />,
        metrics: [
            { label: 'Facilities', value: '15' },
            { label: 'Active lots', value: '500+' },
            { label: 'CTEs', value: '4,000+' },
        ],
        duration: '60s',
    },
    {
        id: 3,
        title: 'Compliance Check',
        description: 'FSMA 204 readiness assessment',
        icon: <Shield className="h-5 w-5" />,
        metrics: [
            { label: 'KDE completeness', value: '91%' },
            { label: 'Gaps identified', value: '3' },
        ],
        duration: '60s',
    },
    {
        id: 4,
        title: 'Live Traceability',
        description: 'Real-time supply chain trace query',
        icon: <Truck className="h-5 w-5" />,
        metrics: [
            { label: 'Nodes traced', value: '11' },
            { label: 'Response time', value: '< 1 second' },
        ],
        duration: '60s',
    },
    {
        id: 5,
        title: 'Recall Drill',
        description: 'Contamination scenario simulation',
        icon: <Store className="h-5 w-5" />,
        metrics: [
            { label: 'Trace time', value: '7 seconds' },
            { label: 'vs FDA requirement', value: '24 hours' },
        ],
        duration: '90s',
    },
    {
        id: 6,
        title: 'ROI Summary',
        description: 'Value proposition and pricing',
        icon: <TrendingUp className="h-5 w-5" />,
        metrics: [
            { label: 'Time savings', value: '37,000x' },
            { label: 'Cost per recall', value: '-$9.5M' },
        ],
        duration: '30s',
    },
];

const ROI_STATS = [
    { label: 'Response Time', before: '72 hours', after: '7 seconds', improvement: '37,000x faster' },
    { label: 'Recall Cost', before: '$10M', after: '$500K', improvement: '$9.5M saved' },
    { label: 'Compliance', before: 'Manual', after: 'Automated', improvement: '100% FSMA 204' },
];

export function InvestorDemoPanel() {
    const [isExpanded, setIsExpanded] = useState(false);
    const [activeStep, setActiveStep] = useState<number | null>(null);

    const handleStartDemo = () => {
        // Open mock recall demo in new tab
        window.open('/demo/mock-recall', '_blank');
    };

    return (
        <Card className="border-2 border-purple-500/20 bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-950/20 dark:to-indigo-950/20">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900">
                            <Rocket className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                            <CardTitle className="text-lg">Investor Demo Mode</CardTitle>
                            <CardDescription>5-minute guided walkthrough</CardDescription>
                        </div>
                    </div>
                    <Badge variant="outline" className="bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300">
                        Fresh Valley Foods
                    </Badge>
                </div>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Quick Actions */}
                <div className="flex gap-2">
                    <Button
                        onClick={handleStartDemo}
                        className="flex-1 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700"
                    >
                        <Play className="mr-2 h-4 w-4" />
                        Start Mock Recall Demo
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => setIsExpanded(!isExpanded)}
                    >
                        {isExpanded ? 'Hide' : 'Show'} Steps
                    </Button>
                </div>

                {/* Demo Steps */}
                <AnimatePresence>
                    {isExpanded && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                        >
                            <div className="space-y-2 pt-2">
                                {DEMO_STEPS.map((step) => (
                                    <motion.div
                                        key={step.id}
                                        className={`p-3 rounded-lg border cursor-pointer transition-colors ${activeStep === step.id
                                                ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                                                : 'border-border hover:border-purple-300'
                                            }`}
                                        onClick={() => setActiveStep(activeStep === step.id ? null : step.id)}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <div className={`p-1.5 rounded ${activeStep === step.id
                                                        ? 'bg-purple-200 dark:bg-purple-800'
                                                        : 'bg-muted'
                                                    }`}>
                                                    {step.icon}
                                                </div>
                                                <div>
                                                    <p className="font-medium text-sm">
                                                        Step {step.id}: {step.title}
                                                    </p>
                                                    <p className="text-xs text-muted-foreground">{step.description}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Badge variant="secondary" className="text-xs">
                                                    <Clock className="mr-1 h-3 w-3" />
                                                    {step.duration}
                                                </Badge>
                                            </div>
                                        </div>

                                        {/* Metrics Dropdown */}
                                        <AnimatePresence>
                                            {activeStep === step.id && step.metrics && (
                                                <motion.div
                                                    initial={{ height: 0, opacity: 0 }}
                                                    animate={{ height: 'auto', opacity: 1 }}
                                                    exit={{ height: 0, opacity: 0 }}
                                                    className="mt-3 pt-3 border-t border-dashed"
                                                >
                                                    <div className="grid grid-cols-2 gap-2">
                                                        {step.metrics.map((metric, idx) => (
                                                            <div key={idx} className="text-sm">
                                                                <span className="text-muted-foreground">{metric.label}: </span>
                                                                <span className="font-semibold text-purple-600 dark:text-purple-400">
                                                                    {metric.value}
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </motion.div>
                                ))}
                            </div>

                            {/* ROI Summary */}
                            <div className="mt-4 p-4 rounded-lg bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/20 dark:to-emerald-950/20 border border-green-200 dark:border-green-800">
                                <h4 className="font-semibold text-green-800 dark:text-green-200 mb-3 flex items-center gap-2">
                                    <DollarSign className="h-4 w-4" />
                                    ROI Highlights
                                </h4>
                                <div className="grid grid-cols-3 gap-4">
                                    {ROI_STATS.map((stat, idx) => (
                                        <div key={idx} className="text-center">
                                            <p className="text-xs text-muted-foreground">{stat.label}</p>
                                            <p className="text-lg font-bold text-green-600 dark:text-green-400">
                                                {stat.improvement}
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                {stat.before} → {stat.after}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Quick Links */}
                <div className="flex flex-wrap gap-2 pt-2">
                    <Button variant="ghost" size="sm" asChild>
                        <a href="/demo/mock-recall">
                            Mock Recall <ArrowRight className="ml-1 h-3 w-3" />
                        </a>
                    </Button>
                    <Button variant="ghost" size="sm" asChild>
                        <a href="/ftl-checker">
                            FTL Checker <ArrowRight className="ml-1 h-3 w-3" />
                        </a>
                    </Button>
                    <Button variant="ghost" size="sm" asChild>
                        <a href="/fsma">
                            FSMA Dashboard <ArrowRight className="ml-1 h-3 w-3" />
                        </a>
                    </Button>
                    <Button variant="ghost" size="sm" asChild>
                        <a href="/pricing">
                            Pricing <ArrowRight className="ml-1 h-3 w-3" />
                        </a>
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
