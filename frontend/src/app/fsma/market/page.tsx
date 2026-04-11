'use client';


import { PageContainer } from '@/components/layout/page-container';
import { TargetMarketBrowser } from '@/components/fsma/target-market-browser';
import { motion } from 'framer-motion';
import { Building2, ArrowLeft, Users, Target } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Link from 'next/link';

export default function TargetMarketPage() {
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
                    <div className="flex items-center gap-4 mb-8">
                        <div className="p-3 rounded-lg bg-re-info-muted dark:bg-blue-900">
                            <Building2 className="h-8 w-8 text-re-info dark:text-re-info" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold">FSMA 204 Target Market</h1>
                            <p className="text-muted-foreground mt-1">
                                75+ companies subject to FDA Food Traceability requirements
                            </p>
                        </div>
                    </div>

                    {/* Info Banner */}
                    <Card className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 border-blue-200 dark:border-blue-800">
                        <CardContent className="py-4">
                            <div className="flex flex-col md:flex-row gap-6">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-full bg-white dark:bg-re-surface-card">
                                        <Target className="h-5 w-5 text-re-info" />
                                    </div>
                                    <div>
                                        <p className="font-medium">Compliance Deadline</p>
                                        <p className="text-sm text-muted-foreground">July 2028</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-full bg-white dark:bg-re-surface-card">
                                        <Users className="h-5 w-5 text-purple-600" />
                                    </div>
                                    <div>
                                        <p className="font-medium">Key Personas</p>
                                        <p className="text-sm text-muted-foreground">
                                            Food Safety Managers, QA Directors, VP Compliance
                                        </p>
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <p className="text-sm">
                                        These companies handle products on the FDA Food Traceability List (FTL)
                                        and must implement end-to-end traceability including CTEs, KDEs, and
                                        24-hour FDA response capabilities.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Target Market Browser */}
                    <TargetMarketBrowser />
                </motion.div>
            </PageContainer>
        </div>
    );
}
