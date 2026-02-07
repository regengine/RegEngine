"use client";

import Link from "next/link";
import { ArrowLeft, Book } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";


export default function NerccipDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs/energy" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Energy Docs
                </Link>

                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">NERC CIP Compliance</h1>
                    <p className="text-muted-foreground">
                        Critical Infrastructure Protection standards
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Documentation Coming Soon</CardTitle>
                        <CardDescription>
                            Detailed documentation for nerc cip compliance is under development
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="p-6 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border">
                            <Book className="h-8 w-8 text-emerald-600 mb-3" />
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
