"use client";

import Link from "next/link";
import { ArrowLeft, FileCheck, CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function FAIDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs/aerospace" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Aerospace Docs
                </Link>

                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">First Article Inspection (AS9102)</h1>
                    <p className="text-muted-foreground">
                        Generate audit-ready FAI reports with cryptographic traceability
                    </p>
                </div>

                <Card className="mb-6">
                    <CardHeader>
                        <CardTitle>FAI Report Generation</CardTitle>
                        <CardDescription>
                            Automate AS9102 Form compliance for new part qualification
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-start gap-3">
                            <CheckCircle2 className="h-5 w-5 text-sky-600 mt-0.5" />
                            <div>
                                <p className="font-medium">Form 1: Part Number Accountability</p>
                                <p className="text-sm text-muted-foreground">Automated drawing and spec extraction</p>
                            </div>
                        </div>
                        <div className="flex items-start gap-3">
                            <CheckCircle2 className="h-5 w-5 text-sky-600 mt-0.5" />
                            <div>
                                <p className="font-medium">Form 2: Product Accountability</p>
                                <p className="text-sm text-muted-foreground">Supplier traceability and certifications</p>
                            </div>
                        </div>
                        <div className="flex items-start gap-3">
                            <CheckCircle2 className="h-5 w-5 text-sky-600 mt-0.5" />
                            <div>
                                <p className="font-medium">Form 3: Characteristics Accountability</p>
                                <p className="text-sm text-muted-foreground">Inspection data and dimensional verification</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <div className="p-6 bg-blue-50 dark:bg-blue-900/20 rounded-lg border">
                    <FileCheck className="h-8 w-8 text-blue-600 mb-3" />
                    <p className="text-sm text-muted-foreground">
                        Detailed FAI documentation and API examples are in active rollout. Contact sales@regengine.co for early access.
                    </p>
                </div>
            </div>
        </div>        </>
    );
}
