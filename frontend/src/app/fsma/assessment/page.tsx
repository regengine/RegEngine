'use client';


import { PageContainer } from '@/components/layout/page-container';
import { FSMA204Assessment } from '@/components/fsma/readiness-assessment';
import { motion } from 'framer-motion';
import { Shield, ArrowLeft, Clock, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import Link from 'next/link';
import { FSMA_ENFORCEMENT_DATE, FSMA_ENFORCEMENT_FRAMING } from '@/lib/fsma-enforcement';

export default function FSMA204AssessmentPage() {
    // Calculate days until FDA enforcement of the Food Traceability Rule begins
    const enforcementDate = new Date(FSMA_ENFORCEMENT_DATE);
    const today = new Date();
    const daysUntilEnforcement = Math.ceil((enforcementDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    const monthsUntilEnforcement = Math.floor(daysUntilEnforcement / 30);

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-6"
                >
                    {/* Back Navigation */}
                    <Link href="/fsma">
                        <Button variant="ghost" size="sm" className="mb-4">
                            <ArrowLeft className="h-4 w-4 mr-2" />
                            Back to FSMA Dashboard
                        </Button>
                    </Link>

                    {/* Page Header */}
                    <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8">
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-lg bg-re-brand-muted dark:bg-re-brand">
                                <Shield className="h-8 w-8 text-re-brand-dark dark:text-re-brand" />
                            </div>
                            <div>
                                <h1 className="text-3xl font-bold">FSMA 204 Readiness Assessment</h1>
                                <p className="text-muted-foreground mt-1">
                                    Evaluate your compliance readiness for FDA Food Traceability requirements
                                </p>
                            </div>
                        </div>

                        {/* Enforcement Countdown */}
                        <Card className="border-primary/30 bg-primary/5">
                            <CardContent className="py-3 px-4">
                                <div className="flex items-center gap-3">
                                    <Calendar className="h-5 w-5 text-primary" />
                                    <div>
                                        <p className="text-sm font-medium">FDA enforcement horizon</p>
                                        <div className="flex items-center gap-2">
                                            <span className="text-lg font-bold text-primary">{monthsUntilEnforcement} months</span>
                                            <Badge variant="outline" className="text-xs">{FSMA_ENFORCEMENT_DATE}</Badge>
                                        </div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Assessment Info Banner */}
                    <Card className="bg-gradient-to-r from-emerald-50 to-blue-50 dark:from-emerald-900/20 dark:to-blue-900/20 border-re-brand dark:border-re-brand">
                        <CardContent className="py-4">
                            <div className="flex flex-col md:flex-row gap-4 md:gap-8">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-full bg-white dark:bg-re-surface-card">
                                        <Clock className="h-5 w-5 text-re-brand-dark" />
                                    </div>
                                    <div>
                                        <p className="font-medium">Quick Assessment</p>
                                        <p className="text-sm text-muted-foreground">5-10 minutes</p>
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <p className="text-sm">
                                        This assessment evaluates your organization&apos;s readiness for FDA FSMA Section 204
                                        Food Traceability requirements. Answer questions about your products, operations,
                                        and current traceability practices to receive a personalized readiness score.
                                    </p>
                                    <p className="text-sm text-muted-foreground mt-2">
                                        {FSMA_ENFORCEMENT_FRAMING}
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Assessment Component */}
                    <FSMA204Assessment />

                    {/* Additional Resources */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
                        <Card>
                            <CardContent className="pt-6">
                                <h3 className="font-semibold mb-2">Food Traceability List (FTL)</h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Learn which foods are covered by FSMA 204 traceability requirements.
                                </p>
                                <Link href="/tools/ftl-checker">
                                    <Button variant="outline" size="sm" className="w-full">
                                        View FTL Categories
                                    </Button>
                                </Link>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-6">
                                <h3 className="font-semibold mb-2">CTE/KDE Reference</h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Critical Tracking Events and Key Data Elements explained.
                                </p>
                                <Link href="/docs/fsma-204">
                                    <Button variant="outline" size="sm" className="w-full">
                                        View Reference Guide
                                    </Button>
                                </Link>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-6">
                                <h3 className="font-semibold mb-2">Recall Drill</h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Test your 24-hour FDA response capability with a simulation.
                                </p>
                                <Link href="/tools/drill-simulator">
                                    <Button variant="outline" size="sm" className="w-full">
                                        Start Drill
                                    </Button>
                                </Link>
                            </CardContent>
                        </Card>
                    </div>
                </motion.div>
            </PageContainer>
        </div>
    );
}
