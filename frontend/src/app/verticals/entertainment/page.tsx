'use client';

import Link from 'next/link';
import { Film, CheckCircle, AlertCircle, Users, Shield, TrendingUp, ArrowRight, PlayCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function EntertainmentVerticalPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            {/* Hero Section */}
            <section className="relative overflow-hidden bg-gradient-to-r from-purple-600 to-pink-600 text-white">
                <div className="max-w-6xl mx-auto px-4 py-20">
                    <div className="text-center">
                        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/20 mb-6">
                            <Film className="h-5 w-5" />
                            <span className="text-sm font-medium">Production Compliance OS</span>
                        </div>

                        <h1 className="text-5xl md:text-6xl font-bold mb-6">
                            Entertainment & Production
                            <br />
                            <span className="text-purple-200">Compliance Automation</span>
                        </h1>

                        <p className="text-xl text-purple-100 max-w-3xl mx-auto mb-8">
                            Automate union compliance, crew eligibility verification, and production safety tracking.
                            Prevent costly production shut-downs with real-time SAG-AFTRA, IATSE, and DGA compliance.
                        </p>

                        <div className="flex justify-center gap-4 mb-8">
                            <Link href="/pcos">
                                <Button size="lg" variant="secondary" className="bg-white text-purple-600 hover:bg-purple-50">
                                    <PlayCircle className="mr-2 h-5 w-5" />
                                    Try PCOS Demo
                                </Button>
                            </Link>
                            <Link href="/verticals/entertainment/pricing">
                                <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                    View Pricing
                                </Button>
                            </Link>
                        </div>

                        <div className="flex justify-center gap-8 text-sm text-purple-100">
                            <span className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4" />
                                Union rule compliance
                            </span>
                            <span className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4" />
                                Crew eligibility verification
                            </span>
                            <span className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4" />
                                Production safety tracking
                            </span>
                        </div>
                    </div>
                </div>

                {/* Wave decoration */}
                <div className="absolute bottom-0 left-0 right-0">
                    <svg viewBox="0 0 1440 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M0 0L60 10C120 20 240 40 360 50C480 60 600 60 720 55C840 50 960 40 1080 35C1200 30 1320 30 1380 30L1440 30V120H1380C1320 120 1200 120 1080 120C960 120 840 120 720 120C600 120 480 120 360 120C240 120 120 120 60 120H0V0Z" fill="currentColor" className="text-background" />
                    </svg>
                </div>
            </section>

            {/* Pain Points Section */}
            <section className="py-16 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">
                            The Production Compliance Challenge
                        </h2>
                        <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
                            Production companies face complex union regulations, multi-state labor laws, and safety compliance requirements
                            that can shut down a $25M production in hours.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-6">
                        {/* Pain Point 1 */}
                        <Card>
                            <CardHeader>
                                <AlertCircle className="h-10 w-10 text-red-600 mb-2" />
                                <CardTitle>Union Compliance Violations</CardTitle>
                                <CardDescription>
                                    SAG-AFTRA, IATSE, and DGA each have different work rules, residual formulas, and rest periods
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground mb-4">
                                    A single missed SAG residual payment or IATSE work rule violation can trigger union
                                    grievances and production shut-downs costing $100K-$500K per day.
                                </p>
                                <div className="space-y-2">
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-red-600 font-bold">×</span>
                                        <span>Manual Excel tracking of union contracts</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-red-600 font-bold">×</span>
                                        <span>No real-time union rule verification</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-red-600 font-bold">×</span>
                                        <span>Violations discovered weeks after filming</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Pain Point 2 */}
                        <Card>
                            <CardHeader>
                                <Users className="h-10 w-10 text-orange-600 mb-2" />
                                <CardTitle>Crew Eligibility Verification</CardTitle>
                                <CardDescription>
                                    Manually verifying union membership, certifications, and work permits for 200+ crew members
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Hiring ineligible crew (expired union membership, fake certifications, invalid work permits)
                                    creates legal liability and union grievances.
                                </p>
                                <div className="space-y-2">
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-orange-600 font-bold">×</span>
                                        <span>2 hours per crew member verification</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-orange-600 font-bold">×</span>
                                        <span>No real-time credential expiration alerts</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-orange-600 font-bold">×</span>
                                        <span>Risk of hiring ineligible crew</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Pain Point 3 */}
                        <Card>
                            <CardHeader>
                                <Shield className="h-10 w-10 text-yellow-600 mb-2" />
                                <CardTitle>Production Safety Incidents</CardTitle>
                                <CardDescription>
                                    On-set accidents, stunt safety violations, and pyrotechnics incidents require immediate reporting
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground mb-4">
                                    OSHA requires 8-hour incident reporting for serious injuries. Late reporting = $70K-$500K fines
                                    and insurance policy violations.
                                </p>
                                <div className="space-y-2">
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-yellow-600 font-bold">×</span>
                                        <span>Paper-based incident reporting (slow)</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-yellow-600 font-bold">×</span>
                                        <span>No centralized safety tracking</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-yellow-600 font-bold">×</span>
                                        <span>Risk of insurance claim denials</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Pain Point 4 */}
                        <Card>
                            <CardHeader>
                                <TrendingUp className="h-10 w-10 text-blue-600 mb-2" />
                                <CardTitle>Multi-State Production Tracking</CardTitle>
                                <CardDescription>
                                    Filming in CA, NY, GA means different labor laws, tax credits, and permit requirements
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Each state has different overtime thresholds, meal penalty rules, and tax credit documentation.
                                    Missing paperwork = lost tax credits worth $500K-$5M.
                                </p>
                                <div className="space-y-2">
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-blue-600 font-bold">×</span>
                                        <span>No unified multi-state dashboard</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-blue-600 font-bold">×</span>
                                        <span>Manual tax credit documentation</span>
                                    </div>
                                    <div className="flex items-start gap-2 text-sm">
                                        <span className="text-blue-600 font-bold">×</span>
                                        <span>Risk of non-compliance across locations</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </section>

            {/* Solution Features Section */}
            <section className="py-16 px-4 bg-muted/30">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">
                            The PCOS Solution
                        </h2>
                        <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
                            Production Compliance OS automates union compliance, crew verification, and safety tracking
                            to prevent production shut-downs.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-8">
                        <div className="space-y-4">
                            <div className="flex items-start gap-4">
                                <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900/20">
                                    <CheckCircle className="h-6 w-6 text-purple-600" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold mb-2">Automated Crew Eligibility Verification</h3>
                                    <p className="text-sm text-muted-foreground">
                                        Real-time verification of union membership, certifications, and work permits.
                                        Alerts when credentials expire. 2 hours → 30 seconds per crew member.
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-start gap-4">
                                <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900/20">
                                    <CheckCircle className="h-6 w-6 text-purple-600" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold mb-2">Union Rule Compliance Checking</h3>
                                    <p className="text-sm text-muted-foreground">
                                        Automated verification against SAG-AFTRA, IATSE, and DGA work rules.
                                        Real-time alerts for rest period violations, overtime thresholds, and meal penalties.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="space-y-4">
                            <div className="flex items-start gap-4">
                                <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900/20">
                                    <CheckCircle className="h-6 w-6 text-purple-600" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold mb-2">Real-Time Safety Incident Reporting</h3>
                                    <p className="text-sm text-muted-foreground">
                                        Mobile incident reporting from set. Automatic OSHA notifications within 8-hour window.
                                        Insurance-ready documentation.
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-start gap-4">
                                <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900/20">
                                    <CheckCircle className="h-6 w-6 text-purple-600" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-semibold mb-2">Multi-Production Dashboard</h3>
                                    <p className="text-sm text-muted-foreground">
                                        Unified view of compliance across all productions. Track 15-20 simultaneous shoots
                                        across CA, NY, GA with state-specific labor law compliance.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ROI Section */}
            <section className="py-16 px-4">
                <div className="max-w-4xl mx-auto">
                    <Card className="border-2">
                        <CardHeader>
                            <CardTitle className="text-2xl">Business Impact & ROI</CardTitle>
                            <CardDescription>
                                For mid-size production company (12 productions/year, $5M avg budget)
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-6">
                                <div className="grid md:grid-cols-3 gap-4">
                                    <div className="text-center p-4 rounded-lg bg-green-50 dark:bg-green-900/20">
                                        <div className="text-3xl font-bold text-green-600">$1.08M</div>
                                        <div className="text-sm text-muted-foreground mt-1">Annual Cost Avoidance</div>
                                    </div>
                                    <div className="text-center p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20">
                                        <div className="text-3xl font-bold text-blue-600">90%</div>
                                        <div className="text-sm text-muted-foreground mt-1">Fewer Union Violations</div>
                                    </div>
                                    <div className="text-center p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20">
                                        <div className="text-3xl font-bold text-purple-600">1.1 mo</div>
                                        <div className="text-sm text-muted-foreground mt-1">Payback Period</div>
                                    </div>
                                </div>

                                <div className="border-t pt-6">
                                    <h4 className="font-semibold mb-3">ROI Breakdown:</h4>
                                    <div className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span>Production shut-down prevention</span>
                                            <span className="font-semibold">$900K/year</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Crew verification time savings</span>
                                            <span className="font-semibold">$135K/year</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Union violation prevention</span>
                                            <span className="font-semibold">$120K/year</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Insurance premium reduction (15%)</span>
                                            <span className="font-semibold">$30K/year</span>
                                        </div>
                                        <div className="border-t pt-2 flex justify-between font-bold">
                                            <span>Total Annual Benefit</span>
                                            <span className="text-green-600">$1.185M/year</span>
                                        </div>
                                        <div className="flex justify-between text-muted-foreground">
                                            <span>PCOS Platform Cost</span>
                                            <span>-$100K/year</span>
                                        </div>
                                        <div className="border-t pt-2 flex justify-between font-bold text-lg">
                                            <span>Net Benefit</span>
                                            <span className="text-green-600">$1.085M/year</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-16 px-4">
                <div className="max-w-4xl mx-auto">
                    <Card className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0">
                        <CardContent className="pt-6">
                            <div className="text-center space-y-4">
                                <h2 className="text-3xl font-bold">Ready to See PCOS in Action?</h2>
                                <p className="text-purple-100 max-w-2xl mx-auto">
                                    Try our interactive Production Compliance OS demo or calculate your ROI
                                </p>
                                <div className="flex justify-center gap-4 pt-4">
                                    <Link href="/pcos">
                                        <Button size="lg" variant="secondary">
                                            <PlayCircle className="mr-2 h-4 w-4" />
                                            Try PCOS Demo
                                        </Button>
                                    </Link>
                                    <Link href="/verticals/entertainment/calculator">
                                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                            Calculate ROI
                                            <ArrowRight className="ml-2 h-4 w-4" />
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </section>        </div>
    );
}
