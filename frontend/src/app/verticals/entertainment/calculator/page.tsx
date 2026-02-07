'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Calculator, Download, ArrowRight, TrendingUp, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function EntertainmentROICalculatorPage() {
    // Input state
    const [productions, setProductions] = useState(12);
    const [avgBudget, setAvgBudget] = useState('5-25M');
    const [unionCrews, setUnionCrews] = useState(['SAG-AFTRA', 'IATSE']);
    const [annualViolationFines, setAnnualViolationFines] = useState(150000);
    const [insurancePremium, setInsurancePremium] = useState(200000);
    const [avgCrewSize, setAvgCrewSize] = useState(75);

    // Calculate ROI
    const calculateROI = () => {
        // 1. Union Violation Prevention
        const violationPrevention = annualViolationFines * 0.8; // 80% reduction

        // 2. Production Shut-Down Avoidance
        const avgViolations = 2; // industry average
        const shutdownProbability = 0.3; // 30% of violations lead to shutdowns
        const avgShutdownDays = 2;
        const costPerDay = 250000;
        const shutdownReduction = 0.9; // 90% reduction

        const shutdownAvoidance = avgViolations * shutdownProbability * avgShutdownDays * costPerDay * shutdownReduction;

        // 3. Insurance Premium Savings
        const insuranceSavings = insurancePremium * 0.15; // 15% reduction

        // 4. Crew Verification Time Savings
        const hoursPerCrew = 2;
        const costPerHour = 75;
        const timeReduction = 0.98; // 98% reduction (2 hours -> 2 minutes)

        const crewVerificationSavings = avgCrewSize * hoursPerCrew * costPerHour * productions * timeReduction;

        // Total benefits
        const totalBenefit = violationPrevention + shutdownAvoidance + insuranceSavings + crewVerificationSavings;

        // PCOS Cost (tiered)
        let pcosCost = 60000; // base
        if (productions >= 16) pcosCost = 150000;
        else if (productions >= 6) pcosCost = 100000;

        const netBenefit = totalBenefit - pcosCost;
        const paybackMonths = (pcosCost / totalBenefit) * 12;
        const roi = ((netBenefit / pcosCost) * 100);

        return {
            violationPrevention,
            shutdownAvoidance,
            insuranceSavings,
            crewVerificationSavings,
            totalBenefit,
            pcosCost,
            netBenefit,
            paybackMonths,
            roi
        };
    };

    const results = calculateROI();

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            {/* Hero */}
            <section className="pt-20 pb-12 px-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
                <div className="max-w-4xl mx-auto text-center">
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/20 mb-6">
                        <Calculator className="h-5 w-5" />
                        <span className="text-sm font-medium">PCOS ROI Calculator</span>
                    </div>

                    <h1 className="text-4xl md:text-5xl font-bold mb-4">
                        Calculate Your Production Compliance ROI
                    </h1>
                    <p className="text-xl text-purple-100 max-w-2xl mx-auto">
                        See how much your production company can save by preventing union violations and production shut-downs
                    </p>
                </div>
            </section>

            {/* Calculator */}
            <section className="py-12 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="grid md:grid-cols-2 gap-8">
                        {/* Inputs */}
                        <div>
                            <Card>
                                <CardHeader>
                                    <CardTitle>Your Production Company</CardTitle>
                                    <CardDescription>Adjust these inputs to match your company profile</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-6">
                                    {/* Productions per year */}
                                    <div>
                                        <label className="block text-sm font-medium mb-2">
                                            Productions per Year: <span className="text-purple-600 font-bold">{productions}</span>
                                        </label>
                                        <input
                                            type="range"
                                            min="1"
                                            max="30"
                                            value={productions}
                                            onChange={(e) => setProductions(Number(e.target.value))}
                                            className="w-full"
                                        />
                                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                            <span>1</span>
                                            <span>30</span>
                                        </div>
                                    </div>

                                    {/* Average Budget */}
                                    <div>
                                        <label className="block text-sm font-medium mb-2">
                                            Average Production Budget
                                        </label>
                                        <select
                                            value={avgBudget}
                                            onChange={(e) => setAvgBudget(e.target.value)}
                                            className="w-full px-4 py-2 border rounded-lg bg-background"
                                        >
                                            <option value="<1M">{'< $1M'}</option>
                                            <option value="1-5M">$1M - $5M</option>
                                            <option value="5-25M">$5M - $25M</option>
                                            <option value="25M+">$25M+</option>
                                        </select>
                                    </div>

                                    {/* Union Crews */}
                                    <div>
                                        <label className="block text-sm font-medium mb-2">
                                            Union Crews Used (check all that apply)
                                        </label>
                                        <div className="space-y-2">
                                            {['SAG-AFTRA', 'IATSE', 'DGA', 'Teamsters'].map(union => (
                                                <label key={union} className="flex items-center gap-2">
                                                    <input
                                                        type="checkbox"
                                                        checked={unionCrews.includes(union)}
                                                        onChange={(e) => {
                                                            if (e.target.checked) {
                                                                setUnionCrews([...unionCrews, union]);
                                                            } else {
                                                                setUnionCrews(unionCrews.filter(u => u !== union));
                                                            }
                                                        }}
                                                        className="rounded"
                                                    />
                                                    <span className="text-sm">{union}</span>
                                                </label>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Annual Violation Fines */}
                                    <div>
                                        <label className="block text-sm font-medium mb-2">
                                            Annual Union Violation Fines Paid: ${(annualViolationFines / 1000).toFixed(0)}K
                                        </label>
                                        <input
                                            type="range"
                                            min="0"
                                            max="500000"
                                            step="10000"
                                            value={annualViolationFines}
                                            onChange={(e) => setAnnualViolationFines(Number(e.target.value))}
                                            className="w-full"
                                        />
                                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                            <span>$0</span>
                                            <span>$500K</span>
                                        </div>
                                    </div>

                                    {/* Insurance Premium */}
                                    <div>
                                        <label className="block text-sm font-medium mb-2">
                                            Production Insurance Premium: ${(insurancePremium / 1000).toFixed(0)}K/year
                                        </label>
                                        <input
                                            type="range"
                                            min="50000"
                                            max="500000"
                                            step="10000"
                                            value={insurancePremium}
                                            onChange={(e) => setInsurancePremium(Number(e.target.value))}
                                            className="w-full"
                                        />
                                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                            <span>$50K</span>
                                            <span>$500K</span>
                                        </div>
                                    </div>

                                    {/* Average Crew Size */}
                                    <div>
                                        <label className="block text-sm font-medium mb-2">
                                            Average Crew Size: <span className="text-purple-600 font-bold">{avgCrewSize}</span>
                                        </label>
                                        <input
                                            type="range"
                                            min="10"
                                            max="500"
                                            step="5"
                                            value={avgCrewSize}
                                            onChange={(e) => setAvgCrewSize(Number(e.target.value))}
                                            className="w-full"
                                        />
                                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                            <span>10</span>
                                            <span>500</span>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Results */}
                        <div className="space-y-6">
                            {/* Summary Card */}
                            <Card className="border-2 border-purple-600">
                                <CardHeader className="bg-gradient-to-r from-purple-600 to-pink-600 text-white">
                                    <CardTitle className="text-2xl">Your PCOS ROI</CardTitle>
                                    <CardDescription className="text-purple-100">
                                        Annual savings with Production Compliance OS
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="pt-6">
                                    <div className="space-y-4">
                                        <div className="text-center p-6 rounded-lg bg-green-50 dark:bg-green-900/20">
                                            <div className="text-4xl font-bold text-green-600">
                                                ${(results.netBenefit / 1000).toFixed(0)}K
                                            </div>
                                            <div className="text-sm text-muted-foreground mt-1">Net Annual Benefit</div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="text-center p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20">
                                                <div className="text-2xl font-bold text-blue-600">{results.paybackMonths.toFixed(1)}</div>
                                                <div className="text-xs text-muted-foreground mt-1">Months Payback</div>
                                            </div>
                                            <div className="text-center p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20">
                                                <div className="text-2xl font-bold text-purple-600">{results.roi.toFixed(0)}%</div>
                                                <div className="text-xs text-muted-foreground mt-1">Annual ROI</div>
                                            </div>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Breakdown */}
                            <Card>
                                <CardHeader>
                                    <CardTitle>Cost Avoidance Breakdown</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-3">
                                        <div className="flex justify-between items-center pb-2 border-b">
                                            <div>
                                                <div className="font-medium">Production Shut-Down Prevention</div>
                                                <div className="text-xs text-muted-foreground">90% reduction in union-mandated shut-downs</div>
                                            </div>
                                            <div className="text-lg font-bold text-green-600">
                                                ${(results.shutdownAvoidance / 1000).toFixed(0)}K
                                            </div>
                                        </div>

                                        <div className="flex justify-between items-center pb-2 border-b">
                                            <div>
                                                <div className="font-medium">Crew Verification Time Savings</div>
                                                <div className="text-xs text-muted-foreground">2 hours → 30 seconds per crew member</div>
                                            </div>
                                            <div className="text-lg font-bold text-green-600">
                                                ${(results.crewVerificationSavings / 1000).toFixed(0)}K
                                            </div>
                                        </div>

                                        <div className="flex justify-between items-center pb-2 border-b">
                                            <div>
                                                <div className="font-medium">Union Violation Prevention</div>
                                                <div className="text-xs text-muted-foreground">80% reduction in compliance fines</div>
                                            </div>
                                            <div className="text-lg font-bold text-green-600">
                                                ${(results.violationPrevention / 1000).toFixed(0)}K
                                            </div>
                                        </div>

                                        <div className="flex justify-between items-center pb-2 border-b">
                                            <div>
                                                <div className="font-medium">Insurance Premium Reduction</div>
                                                <div className="text-xs text-muted-foreground">15% discount for compliance systems</div>
                                            </div>
                                            <div className="text-lg font-bold text-green-600">
                                                ${(results.insuranceSavings / 1000).toFixed(0)}K
                                            </div>
                                        </div>

                                        <div className="flex justify-between items-center pt-2 font-bold">
                                            <div>Total Annual Benefit</div>
                                            <div className="text-xl text-green-600">
                                                ${(results.totalBenefit / 1000).toFixed(0)}K
                                            </div>
                                        </div>

                                        <div className="flex justify-between items-center text-muted-foreground">
                                            <div>PCOS Platform Cost</div>
                                            <div>-${(results.pcosCost / 1000).toFixed(0)}K</div>
                                        </div>

                                        <div className="flex justify-between items-center pt-2 border-t font-bold text-lg">
                                            <div>Net Annual Benefit</div>
                                            <div className="text-green-600">
                                                ${(results.netBenefit / 1000).toFixed(0)}K
                                            </div>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Download CTA */}
                            <Card className="bg-muted/50">
                                <CardContent className="pt-6">
                                    <div className="flex items-start gap-4">
                                        <AlertCircle className="h-5 w-5 text-purple-600 mt-1" />
                                        <div className="flex-1">
                                            <h4 className="font-semibold mb-2">Want a Detailed ROI Report?</h4>
                                            <p className="text-sm text-muted-foreground mb-4">
                                                Download a PDF with full ROI methodology, case studies, and implementation timeline
                                            </p>
                                            <Link href="/contact">
                                                <Button className="w-full">
                                                    <Download className="mr-2 h-4 w-4" />
                                                    Download Full Report
                                                </Button>
                                            </Link>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                </div>
            </section>

            {/* Next Steps */}
            <section className="py-12 px-4 bg-muted/30">
                <div className="max-w-4xl mx-auto">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-2xl text-center">Ready to See PCOS in Action?</CardTitle>
                            <CardDescription className="text-center">
                                Explore pricing tiers or try our interactive demo
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-col md:flex-row gap-4 justify-center">
                                <Link href="/verticals/entertainment/pricing">
                                    <Button size="lg" variant="default" className="w-full md:w-auto">
                                        View Pricing
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </Button>
                                </Link>
                                <Link href="/pcos">
                                    <Button size="lg" variant="outline" className="w-full md:w-auto">
                                        Try PCOS Demo
                                    </Button>
                                </Link>
                                <Link href="/contact">
                                    <Button size="lg" variant="outline" className="w-full md:w-auto">
                                        Contact Sales
                                    </Button>
                                </Link>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </section>

            {/* Assumptions */}
            <section className="py-12 px-4">
                <div className="max-w-4xl mx-auto">
                    <h2 className="text-2xl font-bold mb-6 text-center">ROI Calculation Methodology</h2>
                    <div className="grid md:grid-cols-2 gap-6">
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <CheckCircle className="h-5 w-5 text-green-600" />
                                    Production Shut-Down Prevention
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="text-sm space-y-2">
                                <p><strong>Assumption:</strong> 2 violations per year (industry average from Producers Guild 2023 survey)</p>
                                <p><strong>Shut-down probability:</strong> 30% of violations lead to production halts</p>
                                <p><strong>Average shut-down:</strong> 2 days at $250K/day</p>
                                <p><strong>PCOS reduction:</strong> 90% (database-enforced prevention)</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <CheckCircle className="h-5 w-5 text-green-600" />
                                    Crew Verification Savings
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="text-sm space-y-2">
                                <p><strong>Manual process:</strong> 2 hours per crew member (union calls, reference checks)</p>
                                <p><strong>PCOS process:</strong> 30 seconds (automated verification)</p>
                                <p><strong>Cost per hour:</strong> $75 (production coordinator hourly rate)</p>
                                <p><strong>Time reduction:</strong> 98% (2 hours → 30 seconds)</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <CheckCircle className="h-5 w-5 text-green-600" />
                                    Union Violation Prevention
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="text-sm space-y-2">
                                <p><strong>Industry average fines:</strong> $150K/year for 12-production company</p>
                                <p><strong>PCOS reduction:</strong> 80% (real-time rule enforcement)</p>
                                <p><strong>Remaining violations:</strong> Typically related to approved waivers or edge cases</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <CheckCircle className="h-5 w-5 text-green-600" />
                                    Insurance Premium Reduction
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="text-sm space-y-2">
                                <p><strong>Typical reduction:</strong> 15-20% for documented compliance systems</p>
                                <p><strong>Calculation:</strong> Current premium × 15%</p>
                                <p><strong>Requirement:</strong> SOC 2 audit + compliance documentation (PCOS provides both)</p>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="mt-8 p-6 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                        <h3 className="font-semibold mb-2 flex items-center gap-2">
                            <TrendingUp className="h-5 w-5 text-blue-600" />
                            Conservative Estimates
                        </h3>
                        <p className="text-sm text-muted-foreground">
                            This calculator uses conservative industry averages. Actual ROI may be higher if your company has:
                            (1) experienced recent shut-downs, (2) higher violation rates, (3) larger crew sizes, or (4) multi-state productions.
                            SilverScreen Studios (case study) achieved 975% ROI over 18 months with similar inputs.
                        </p>
                    </div>
                </div>
            </section>        </div>
    );
}
