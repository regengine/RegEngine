'use client';

import Link from 'next/link';
import { Leaf, CheckCircle, AlertCircle, TrendingUp, ArrowRight, PlayCircle, FileText, ClipboardCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function FoodSafetyVerticalPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            {/* Hero Section */}
            <section className="relative overflow-hidden bg-gradient-to-r from-green-600 to-emerald-600 text-white">
                <div className="max-w-6xl mx-auto px-4 py-20">
                    <div className="text-center">
                        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/20 mb-6">
                            <Leaf className="h-5 w-5" />
                            <span className="text-sm font-medium">FSMA 204 Compliance</span>
                        </div>

                        <h1 className="text-5xl md:text-6xl font-bold mb-6">
                            Food Safety
                            <br />
                            <span className="text-green-200">Traceability & Compliance</span>
                        </h1>

                        <p className="text-xl text-green-100 max-w-3xl mx-auto mb-8">
                            Automate FSMA 204 traceability requirements with lot-level tracking,
                            recall readiness, and supply chain transparency.
                        </p>

                        <div className="flex justify-center gap-4 mb-8">
                            <Link href="/verticals/food-safety/dashboard">
                                <Button size="lg" variant="secondary" className="bg-white text-green-600 hover:bg-green-50">
                                    <PlayCircle className="mr-2 h-5 w-5" />
                                    Explore FSMA Module
                                </Button>
                            </Link>
                            <Link href="/verticals/food-safety/dashboard">
                                <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                    Readiness Assessment
                                </Button>
                            </Link>
                        </div>

                        <div className="flex justify-center gap-8 text-sm text-green-100">
                            <span className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4" />
                                Lot-level traceability
                            </span>
                            <span className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4" />
                                2-hour recall readiness
                            </span>
                            <span className="flex items-center gap-2">
                                <CheckCircle className="h-4 w-4" />
                                Supply chain mapping
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

            {/* Key Features */}
            <section className="py-16 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">
                            FSMA 204 Requirements
                        </h2>
                        <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
                            Meet FDA's Food Traceability List requirements with automated lot tracking and recall readiness.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-3 gap-6">
                        <Card>
                            <CardHeader>
                                <FileText className="h-10 w-10 text-green-600 mb-2" />
                                <CardTitle>Lot-Level Tracking</CardTitle>
                                <CardDescription>
                                    Track every lot from supplier to customer with complete chain of custody
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2 text-sm">
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Automated lot number generation</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Critical tracking events (CTEs)</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Key data elements (KDEs) collection</span>
                                    </li>
                                </ul>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <AlertCircle className="h-10 w-10 text-amber-600 mb-2" />
                                <CardTitle>Recall Readiness</CardTitle>
                                <CardDescription>
                                    2-hour recall response with complete traceability records
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2 text-sm">
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Instant upstream/downstream tracing</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Sortable spreadsheet format</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>FDA-ready documentation</span>
                                    </li>
                                </ul>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <TrendingUp className="h-10 w-10 text-blue-600 mb-2" />
                                <CardTitle>Supply Chain Visibility</CardTitle>
                                <CardDescription>
                                    Complete transparency from farm to fork
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2 text-sm">
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Supplier/customer mapping</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Geographic traceability</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
                                        <span>Transformation tracking</span>
                                    </li>
                                </ul>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </section>

            {/* Food Traceability List */}
            <section className="py-16 px-4 bg-muted/30">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">
                            Food Traceability List Coverage
                        </h2>
                        <p className="text-xl text-muted-foreground">
                            Pre-configured templates for all FDA-designated high-risk foods
                        </p>
                    </div>

                    <div className="grid md:grid-cols-4 gap-4">
                        {[
                            'Leafy Greens',
                            'Fresh Herbs',
                            'Cucumbers',
                            'Tomatoes',
                            'Melons',
                            'Peppers',
                            'Strawberries',
                            'Soft Cheeses',
                            'Shell Eggs',
                            'Nut Butters',
                            'Fresh-cut Fruits',
                            'Tropical Tree Fruits'
                        ].map((food) => (
                            <div key={food} className="flex items-center gap-2 p-3 rounded-lg bg-background border">
                                <Leaf className="h-4 w-4 text-green-600" />
                                <span className="text-sm font-medium">{food}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Quick Links */}
            <section className="py-16 px-4">
                <div className="max-w-4xl mx-auto">
                    <Card className="bg-gradient-to-r from-green-600 to-emerald-600 text-white border-0">
                        <CardContent className="pt-6">
                            <div className="text-center space-y-4">
                                <h2 className="text-3xl font-bold">Explore FSMA Tools</h2>
                                <p className="text-green-100 max-w-2xl mx-auto">
                                    Access readiness assessment, target market analysis, and compliance dashboard
                                </p>
                                <div className="flex justify-center gap-4 pt-4">
                                    <Link href="/fsma">
                                        <Button size="lg" variant="secondary">
                                            <PlayCircle className="mr-2 h-4 w-4" />
                                            FSMA Dashboard
                                        </Button>
                                    </Link>
                                    <Link href="/fsma/assessment">
                                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                            <ClipboardCheck className="mr-2 h-4 w-4" />
                                            Readiness Assessment
                                        </Button>
                                    </Link>
                                    <Link href="/fsma/market">
                                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                            Target Market
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
