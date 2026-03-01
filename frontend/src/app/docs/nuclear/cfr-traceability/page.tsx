"use client";

import Link from "next/link";
import { ArrowLeft, Book } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";


export default function CfrtraceabilityDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs/nuclear" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Nuclear Docs
                </Link>

                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">CFR Traceability</h1>
                    <p className="text-muted-foreground">
                        10 CFR Part 50 requirement tracking
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Documentation Expansion in Progress</CardTitle>
                        <CardDescription>
                            Detailed documentation for cfr traceability is under development
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="p-6 bg-purple-50 dark:bg-purple-900/20 rounded-lg border">
                            <Book className="h-8 w-8 text-purple-600 mb-3" />
                            <p className="text-sm text-muted-foreground">
                                Complete API documentation and integration guides are in development.
                                Contact sales@regengine.co for early access and implementation guidance.
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>        </>
    );
}
