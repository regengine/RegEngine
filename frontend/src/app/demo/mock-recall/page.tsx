'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    AlertTriangle,
    ArrowRight,
    Play,
    RotateCcw,
    Download,
    Clock,
    MapPin,
    Package,
    Building2,
    Truck,
    Store,
    ChefHat,
    CheckCircle2,
    XCircle,
    Timer,
    Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/components/ui/use-toast';
import Link from 'next/link';

// Mock contamination scenarios
const SCENARIOS = [
    {
        id: 'romaine-ecoli',
        name: 'E. coli in Romaine Lettuce',
        product: 'Romaine Lettuce',
        contaminant: 'E. coli O157:H7',
        origin: 'Taylor Farms - Salinas, CA',
        lot: 'TF-2024-ROM-0847',
        severity: 'CRITICAL',
    },
    {
        id: 'salmon-listeria',
        name: 'Listeria in Smoked Salmon',
        product: 'Smoked Atlantic Salmon',
        contaminant: 'Listeria monocytogenes',
        origin: 'Trident Seafoods - Seattle, WA',
        lot: 'TS-2024-SAL-2391',
        severity: 'CRITICAL',
    },
];

// Simulated supply chain nodes
const SUPPLY_CHAIN = [
    { id: 'grower', type: 'GROWING', icon: Package, label: 'Grower', location: 'Salinas, CA', time: 'Jan 5, 2024 06:00' },
    { id: 'packer', type: 'PACKING', icon: Package, label: 'Packing Facility', location: 'Salinas, CA', time: 'Jan 5, 2024 14:00' },
    { id: 'cooler', type: 'COOLING', icon: Building2, label: 'Cold Storage', location: 'Salinas, CA', time: 'Jan 5, 2024 18:00' },
    { id: 'shipper', type: 'SHIPPING', icon: Truck, label: 'Distribution', location: 'Los Angeles, CA', time: 'Jan 6, 2024 04:00' },
    { id: 'dc1', type: 'RECEIVING', icon: Building2, label: 'DC West', location: 'Phoenix, AZ', time: 'Jan 6, 2024 14:00' },
    { id: 'dc2', type: 'RECEIVING', icon: Building2, label: 'DC Southwest', location: 'Dallas, TX', time: 'Jan 7, 2024 02:00' },
    { id: 'retail1', type: 'RECEIVING', icon: Store, label: 'Organic Market #247', location: 'Scottsdale, AZ', time: 'Jan 7, 2024 08:00' },
    { id: 'retail2', type: 'RECEIVING', icon: Store, label: 'Regional Grocery #1842', location: 'Plano, TX', time: 'Jan 7, 2024 10:00' },
    { id: 'retail3', type: 'RECEIVING', icon: Store, label: 'Valley Grocery #892', location: 'Tucson, AZ', time: 'Jan 7, 2024 09:00' },
    { id: 'restaurant1', type: 'RECEIVING', icon: ChefHat, label: 'Fast Casual #4521', location: 'Phoenix, AZ', time: 'Jan 7, 2024 11:00' },
    { id: 'restaurant2', type: 'RECEIVING', icon: ChefHat, label: 'Health Bowl #189', location: 'Austin, TX', time: 'Jan 7, 2024 13:00' },
];

interface TraceState {
    phase: 'idle' | 'tracing' | 'complete';
    tracedNodes: string[];
    elapsedSeconds: number;
}

export default function MockRecallPage() {
    const [scenario] = useState(SCENARIOS[0]);
    const [traceState, setTraceState] = useState<TraceState>({
        phase: 'idle',
        tracedNodes: [],
        elapsedSeconds: 0,
    });
    const [isDownloading, setIsDownloading] = useState(false);
    const { toast } = useToast();

    // Simulate tracing animation
    useEffect(() => {
        if (traceState.phase !== 'tracing') return;

        const nodeInterval = setInterval(() => {
            setTraceState(prev => {
                const nextIndex = prev.tracedNodes.length;
                if (nextIndex >= SUPPLY_CHAIN.length) {
                    clearInterval(nodeInterval);
                    return { ...prev, phase: 'complete' };
                }
                return {
                    ...prev,
                    tracedNodes: [...prev.tracedNodes, SUPPLY_CHAIN[nextIndex].id],
                };
            });
        }, 200); // Trace each node with 200ms delay

        return () => clearInterval(nodeInterval);
    }, [traceState.phase]);

    // Timer for elapsed time
    useEffect(() => {
        if (traceState.phase !== 'tracing' && traceState.phase !== 'complete') return;

        const timerInterval = setInterval(() => {
            setTraceState(prev => ({
                ...prev,
                elapsedSeconds: prev.elapsedSeconds + 1,
            }));
        }, 1000);

        // Stop timer when trace is complete
        if (traceState.phase === 'complete') {
            // Keep running for demo effect
            setTimeout(() => clearInterval(timerInterval), 5000);
        }

        return () => clearInterval(timerInterval);
    }, [traceState.phase]);

    const startTrace = () => {
        setTraceState({
            phase: 'tracing',
            tracedNodes: [],
            elapsedSeconds: 0,
        });
    };

    const resetTrace = () => {
        setTraceState({
            phase: 'idle',
            tracedNodes: [],
            elapsedSeconds: 0,
        });
    };

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const handleDownloadReport = async () => {
        setIsDownloading(true);
        try {
            const report = generateFDA204Report();
            const blob = new Blob(['\uFEFF', report], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `FDA-204-Report-${scenario.lot}-${new Date().toISOString().split('T')[0]}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            toast({
                title: "Report Downloaded",
                description: "Your FDA 204 compliance report has been saved.",
            });
        } catch (error) {
            toast({
                title: "Download Failed",
                description: "There was an error generating your report.",
                variant: "destructive",
            });
        } finally {
            setIsDownloading(false);
        }
    };

    const generateFDA204Report = () => {
        const date = new Date().toLocaleString();
        const tracedNodes = SUPPLY_CHAIN.filter(n => traceState.tracedNodes.includes(n.id));
        return `
===========================================
     FDA FSMA 204 TRACEABILITY REPORT
===========================================
Generated: ${date}
Report Type: Forward Trace (Mock Recall Drill)

CONTAMINATION SCENARIO
----------------------
Product: ${scenario.product}
Contaminant: ${scenario.contaminant}
Origin: ${scenario.origin}
Traceability Lot Code (TLC): ${scenario.lot}
Severity: ${scenario.severity}

TRACE SUMMARY
-------------
Trace Direction: FORWARD
Trace Time: ${traceState.elapsedSeconds} seconds
Total Events Traced: ${SUPPLY_CHAIN.length}
Impacted Locations: ${impactedRetailers + impactedRestaurants}
States Affected: 3 (AZ, TX, CA)

FDA 24-HOUR REQUIREMENT: ✓ MET (${traceState.elapsedSeconds}s response)

SUPPLY CHAIN TRACE RESULTS
--------------------------
${tracedNodes.map((node, i) =>
            `${i + 1}. ${node.label}
   Type: ${node.type}
   Location: ${node.location}
   Timestamp: ${node.time}
   Status: IMPACTED`
        ).join('\n\n')}

KEY DATA ELEMENTS (KDEs) CAPTURED
---------------------------------
- Traceability Lot Code (TLC): ${scenario.lot}
- Product Description: ${scenario.product}
- Quantity/Unit of Measure: Traced across ${SUPPLY_CHAIN.length} nodes
- Location Identifiers (GLNs): All facilities identified
- Event Timestamps: All Critical Tracking Events logged

RECOMMENDED ACTIONS
-------------------
1. Issue immediate stop-sale order for lot ${scenario.lot}
2. Notify all ${impactedRetailers + impactedRestaurants} downstream locations
3. Begin consumer notification protocol
4. Coordinate with FDA/CDC as required
5. Initiate product recovery/destruction plan

-------------------------------------------
Report generated by RegEngine FSMA 204 Platform
For more information: regengine.co/fsma
-------------------------------------------
`;
    };

    const impactedRetailers = SUPPLY_CHAIN.filter(
        n => traceState.tracedNodes.includes(n.id) && (n.type === 'RECEIVING')
    ).length;
    const impactedRestaurants = SUPPLY_CHAIN.filter(
        n => traceState.tracedNodes.includes(n.id) && n.icon === ChefHat
    ).length;


    return (
        <div className="min-h-screen bg-gradient-to-b from-red-50 to-white dark:from-gray-900 dark:to-gray-800">            {/* Alert Banner */}
            <div className="bg-red-600 text-white py-3">
                <div className="max-w-6xl mx-auto px-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <AlertTriangle className="h-5 w-5 animate-pulse" />
                        <span className="font-semibold">MOCK RECALL DRILL</span>
                        <Badge variant="outline" className="bg-white/20 text-white border-white/30">
                            Demo Mode
                        </Badge>
                    </div>
                    <span className="text-sm text-white/80">
                        This is a simulation. No real recall is in progress.
                    </span>
                </div>
            </div>

            {/* Hero Section */}
            <div className="py-12 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                    >
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">
                            See Your Supply Chain<br />
                            <span className="text-red-600">Light Up in Seconds</span>
                        </h1>
                        <p className="text-xl text-muted-foreground mb-8">
                            FDA FSMA 204 requires 24-hour response. Watch RegEngine trace a
                            contaminated lot through your entire supply chain—in under 5 seconds.
                        </p>
                    </motion.div>
                </div>
            </div>

            {/* Main Demo Area */}
            <div className="max-w-6xl mx-auto px-4 pb-16">
                <div className="grid lg:grid-cols-3 gap-6">
                    {/* Scenario Card */}
                    <Card className="lg:col-span-1">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <AlertTriangle className="h-5 w-5 text-red-600" />
                                Contamination Scenario
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <p className="text-sm text-muted-foreground">Product</p>
                                <p className="font-semibold">{scenario.product}</p>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Contaminant</p>
                                <p className="font-semibold text-red-600">{scenario.contaminant}</p>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Origin</p>
                                <p className="font-semibold">{scenario.origin}</p>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Lot Code (TLC)</p>
                                <code className="px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded text-sm font-mono">
                                    {scenario.lot}
                                </code>
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Severity</p>
                                <Badge variant="destructive">{scenario.severity}</Badge>
                            </div>

                            <div className="pt-4 space-y-3">
                                {traceState.phase === 'idle' && (
                                    <Button
                                        onClick={startTrace}
                                        className="w-full bg-red-600 hover:bg-red-700"
                                        size="lg"
                                    >
                                        <Play className="mr-2 h-4 w-4" />
                                        Start Trace
                                    </Button>
                                )}
                                {traceState.phase !== 'idle' && (
                                    <Button
                                        onClick={resetTrace}
                                        variant="outline"
                                        className="w-full"
                                    >
                                        <RotateCcw className="mr-2 h-4 w-4" />
                                        Reset Demo
                                    </Button>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Trace Visualization */}
                    <Card className="lg:col-span-2">
                        <CardHeader className="flex flex-row items-center justify-between">
                            <div>
                                <CardTitle>Forward Trace: Supply Chain Impact</CardTitle>
                                <CardDescription>
                                    Tracing lot {scenario.lot} through downstream distribution
                                </CardDescription>
                            </div>
                            {traceState.phase !== 'idle' && (
                                <div className="flex items-center gap-4 text-right">
                                    <div>
                                        <p className="text-2xl font-bold font-mono">{formatTime(traceState.elapsedSeconds)}</p>
                                        <p className="text-xs text-muted-foreground">Elapsed</p>
                                    </div>
                                    {traceState.phase === 'complete' && (
                                        <CheckCircle2 className="h-6 w-6 text-emerald-600" />
                                    )}
                                </div>
                            )}
                        </CardHeader>
                        <CardContent>
                            {/* Progress Bar */}
                            {traceState.phase !== 'idle' && (
                                <div className="mb-6">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-sm font-medium">Trace Progress</span>
                                        <span className="text-sm text-muted-foreground">
                                            {traceState.tracedNodes.length} / {SUPPLY_CHAIN.length} nodes
                                        </span>
                                    </div>
                                    <Progress
                                        value={(traceState.tracedNodes.length / SUPPLY_CHAIN.length) * 100}
                                        className="h-2"
                                    />
                                </div>
                            )}

                            {/* Supply Chain Nodes */}
                            <div className="space-y-3">
                                {SUPPLY_CHAIN.map((node, index) => {
                                    const Icon = node.icon;
                                    const isTraced = traceState.tracedNodes.includes(node.id);
                                    const isTracing = traceState.phase === 'tracing' &&
                                        traceState.tracedNodes.length === index;

                                    return (
                                        <motion.div
                                            key={node.id}
                                            initial={{ opacity: 0.3 }}
                                            animate={{
                                                opacity: isTraced ? 1 : 0.3,
                                                scale: isTracing ? 1.02 : 1,
                                            }}
                                            transition={{ duration: 0.3 }}
                                            className={`
                        flex items-center gap-4 p-3 rounded-lg border-2 transition-all
                        ${isTraced
                                                    ? 'border-red-500 bg-red-50 dark:bg-red-900/20'
                                                    : 'border-gray-200 dark:border-gray-700'}
                        ${isTracing ? 'ring-2 ring-red-500 ring-offset-2' : ''}
                      `}
                                        >
                                            <div className={`
                        p-2 rounded-lg
                        ${isTraced
                                                    ? 'bg-red-100 dark:bg-red-900'
                                                    : 'bg-gray-100 dark:bg-gray-800'}
                      `}>
                                                <Icon className={`h-5 w-5 ${isTraced ? 'text-red-600' : 'text-gray-400'}`} />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <p className={`font-medium ${isTraced ? '' : 'text-muted-foreground'}`}>
                                                        {node.label}
                                                    </p>
                                                    <Badge variant="outline" className="text-xs">
                                                        {node.type}
                                                    </Badge>
                                                </div>
                                                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                                                    <span className="flex items-center gap-1">
                                                        <MapPin className="h-3 w-3" />
                                                        {node.location}
                                                    </span>
                                                    <span className="flex items-center gap-1">
                                                        <Clock className="h-3 w-3" />
                                                        {node.time}
                                                    </span>
                                                </div>
                                            </div>
                                            {isTraced && (
                                                <motion.div
                                                    initial={{ scale: 0 }}
                                                    animate={{ scale: 1 }}
                                                    className="flex-shrink-0"
                                                >
                                                    <XCircle className="h-5 w-5 text-red-600" />
                                                </motion.div>
                                            )}
                                        </motion.div>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Results Panel */}
                <AnimatePresence>
                    {traceState.phase === 'complete' && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="mt-8"
                        >
                            <Card className="border-2 border-red-500">
                                <CardHeader className="bg-red-50 dark:bg-red-900/20">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <CardTitle className="text-red-700">Trace Complete</CardTitle>
                                            <CardDescription>
                                                Full supply chain impact identified in {traceState.elapsedSeconds} seconds
                                            </CardDescription>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Timer className="h-5 w-5 text-emerald-600" />
                                            <span className="text-lg font-bold text-emerald-600">
                                                FDA requirement: 24 hours ✓
                                            </span>
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent className="pt-6">
                                    <div className="grid md:grid-cols-4 gap-4 mb-6">
                                        <div className="text-center p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
                                            <p className="text-3xl font-bold text-red-600">{SUPPLY_CHAIN.length}</p>
                                            <p className="text-sm text-muted-foreground">Total Events</p>
                                        </div>
                                        <div className="text-center p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
                                            <p className="text-3xl font-bold text-orange-600">{impactedRetailers + impactedRestaurants}</p>
                                            <p className="text-sm text-muted-foreground">Impacted Locations</p>
                                        </div>
                                        <div className="text-center p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
                                            <p className="text-3xl font-bold text-yellow-600">3</p>
                                            <p className="text-sm text-muted-foreground">States Affected</p>
                                        </div>
                                        <div className="text-center p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg">
                                            <p className="text-3xl font-bold text-emerald-600">{traceState.elapsedSeconds}s</p>
                                            <p className="text-sm text-muted-foreground">Response Time</p>
                                        </div>
                                    </div>

                                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                        <Button
                                            onClick={handleDownloadReport}
                                            disabled={isDownloading}
                                            className="bg-red-600 hover:bg-red-700"
                                        >
                                            {isDownloading ? (
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            ) : (
                                                <Download className="mr-2 h-4 w-4" />
                                            )}
                                            {isDownloading ? 'Generating...' : 'Export FDA 204 Report'}
                                        </Button>
                                        <Link href="/pricing">
                                            <Button variant="outline">
                                                Get This For Your Supply Chain
                                                <ArrowRight className="ml-2 h-4 w-4" />
                                            </Button>
                                        </Link>
                                    </div>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* CTA Section */}
                {traceState.phase === 'idle' && (
                    <div className="mt-12 text-center">
                        <Card className="bg-gradient-to-r from-emerald-600 to-blue-600 text-white border-0">
                            <CardContent className="py-8">
                                <h2 className="text-2xl font-bold mb-4">
                                    This demo took 5 seconds. How long would it take you?
                                </h2>
                                <p className="text-white/90 mb-6 max-w-2xl mx-auto">
                                    Most companies rely on phone calls, spreadsheets, and emails to trace
                                    product through their supply chain. When FDA comes knocking, you have
                                    24 hours to respond—not 24 days.
                                </p>
                                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                    <Button
                                        onClick={startTrace}
                                        size="lg"
                                        className="bg-white text-emerald-700 hover:bg-white/90"
                                    >
                                        <Play className="mr-2 h-4 w-4" />
                                        Run the Demo
                                    </Button>
                                    <Link href="/ftl-checker">
                                        <Button
                                            size="lg"
                                            variant="outline"
                                            className="border-white text-white hover:bg-white/10"
                                        >
                                            Check If You&apos;re Covered by FSMA 204
                                        </Button>
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )}
            </div>
        </div>
    );
}
