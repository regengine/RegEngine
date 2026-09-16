'use client';


import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { FSMA204Assessment } from '@/components/fsma/readiness-assessment';
import { ArrowLeft, Clock, Calendar } from 'lucide-react';
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
        <PageContainer>
            {/* Back Navigation */}
            <div className="mb-4">
                <Button variant="ghost" size="sm" asChild>
                    <Link href="/fsma">
                        <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        Back to FSMA Dashboard
                    </Link>
                </Button>
            </div>

            <PageHeader
                title="FSMA 204 Readiness Assessment"
                description="Evaluate your compliance readiness for FDA Food Traceability requirements"
                meta={
                    /* Enforcement Countdown */
                    <span className="flex items-center gap-2">
                        <Calendar className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                        <span className="text-re-text-secondary">FDA enforcement horizon</span>
                        <span className="font-medium tabular-nums text-re-text-primary">{monthsUntilEnforcement} months</span>
                        <Badge tone="neutral" size="sm" mono>{FSMA_ENFORCEMENT_DATE}</Badge>
                    </span>
                }
            />

            <div className="space-y-6">
                {/* Assessment Info Banner */}
                <Card>
                    <CardContent className="flex flex-col gap-4 md:flex-row md:gap-8">
                        <div className="flex items-center gap-3">
                            <Clock className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <div>
                                <p className="text-ui font-medium text-re-text-primary">Quick Assessment</p>
                                <p className="text-small text-re-text-tertiary">5-10 minutes</p>
                            </div>
                        </div>
                        <div className="flex-1">
                            <p className="text-ui text-re-text-secondary">
                                This assessment evaluates your organization&apos;s readiness for FDA FSMA Section 204
                                Food Traceability requirements. Answer questions about your products, operations,
                                and current traceability practices to receive a personalized readiness score.
                            </p>
                            <p className="mt-2 text-small text-re-text-tertiary">
                                {FSMA_ENFORCEMENT_FRAMING}
                            </p>
                        </div>
                    </CardContent>
                </Card>

                {/* Assessment Component */}
                <FSMA204Assessment />

                {/* Additional Resources */}
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <Card>
                        <CardContent>
                            <h3 className="mb-2 text-subheading text-re-text-primary">Food Traceability List (FTL)</h3>
                            <p className="mb-4 text-ui text-re-text-secondary">
                                Learn which foods are covered by FSMA 204 traceability requirements.
                            </p>
                            <Button variant="secondary" size="sm" className="w-full" asChild>
                                <Link href="/tools/ftl-checker">
                                    View FTL Categories
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent>
                            <h3 className="mb-2 text-subheading text-re-text-primary">CTE/KDE Reference</h3>
                            <p className="mb-4 text-ui text-re-text-secondary">
                                Critical Tracking Events and Key Data Elements explained.
                            </p>
                            <Button variant="secondary" size="sm" className="w-full" asChild>
                                <Link href="/docs/fsma-204">
                                    View Reference Guide
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent>
                            <h3 className="mb-2 text-subheading text-re-text-primary">Recall Drill</h3>
                            <p className="mb-4 text-ui text-re-text-secondary">
                                Test your 24-hour FDA response capability with a simulation.
                            </p>
                            <Button variant="secondary" size="sm" className="w-full" asChild>
                                <Link href="/tools/drill-simulator">
                                    Start Drill
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </PageContainer>
    );
}
