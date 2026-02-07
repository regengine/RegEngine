'use client';

import Link from 'next/link';
import { ArrowLeft, ClipboardCheck, AlertTriangle, FileText, CheckCircle2, Clock } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export default function PCOSAssessmentPage() {
    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
            <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-lg dark:bg-slate-900/80">
                <div className="container flex h-16 items-center justify-between px-6">
                    <Link href="/pcos" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
                        <ArrowLeft className="h-4 w-4" />
                        <span className="text-sm">Back to PCOS Dashboard</span>
                    </Link>
                    <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200">
                        Assessment Tool
                    </Badge>
                </div>
            </header>

            <main className="container px-6 py-12 max-w-4xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Compliance Assessment</h1>
                    <p className="text-muted-foreground">
                        Evaluate your production's compliance readiness across all critical categories
                    </p>
                </div>

                <Card className="mb-6">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <ClipboardCheck className="h-5 w-5 text-purple-600" />
                            Assessment Overview
                        </CardTitle>
                        <CardDescription>
                            Answer questions about your production to receive personalized compliance guidance
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid md:grid-cols-3 gap-4">
                            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200">
                                <FileText className="h-8 w-8 text-blue-600 mb-2" />
                                <h3 className="font-medium mb-1">Project Details</h3>
                                <p className="text-sm text-muted-foreground">Basic production information</p>
                            </div>
                            <div className="p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200">
                                <AlertTriangle className="h-8 w-8 text-amber-600 mb-2" />
                                <h3 className="font-medium mb-1">Risk Factors</h3>
                                <p className="text-sm text-muted-foreground">Identify compliance risks</p>
                            </div>
                            <div className="p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-200">
                                <CheckCircle2 className="h-8 w-8 text-emerald-600 mb-2" />
                                <h3 className="font-medium mb-1">Action Plan</h3>
                                <p className="text-sm text-muted-foreground">Get your compliance roadmap</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <div className="p-8 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200">
                    <div className="flex items-start gap-4">
                        <Clock className="h-6 w-6 text-purple-600 mt-1" />
                        <div>
                            <h3 className="font-semibold text-lg mb-2">Coming Soon</h3>
                            <p className="text-muted-foreground mb-4">
                                The PCOS Assessment Tool is currently under development. This feature will provide:
                            </p>
                            <ul className="space-y-2 text-sm">
                                <li className="flex items-center gap-2">
                                    <CheckCircle2 className="h-4 w-4 text-purple-600" />
                                    Interactive questionnaire for production details
                                </li>
                                <li className="flex items-center gap-2">
                                    <CheckCircle2 className="h-4 w-4 text-purple-600" />
                                    Automated risk scoring across 6 compliance categories
                                </li>
                                <li className="flex items-center gap-2">
                                    <CheckCircle2 className="h-4 w-4 text-purple-600" />
                                    Personalized compliance checklist generation
                                </li>
                                <li className="flex items-center gap-2">
                                    <CheckCircle2 className="h-4 w-4 text-purple-600" />
                                    Timeline recommendations based on shoot dates
                                </li>
                            </ul>
                            <div className="mt-6">
                                <Button asChild>
                                    <Link href="/pcos">Return to Dashboard</Link>
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
