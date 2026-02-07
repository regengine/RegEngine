"use client";

import Link from "next/link";
import { ArrowLeft, Settings } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";


export default function ConfigManagementDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs/aerospace" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Aerospace Docs
                </Link>

                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Configuration Management (AS9145)</h1>
                    <p className="text-muted-foreground">
                        Immutable change control and configuration baseline tracking
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Configuration Management System</CardTitle>
                        <CardDescription>
                            Track engineering changes with cryptographic audit trails
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <p className="text-muted-foreground mb-4">
                            RegEngine's configuration management system provides full traceability for engineering changes,
                            ensuring compliance with AS9145 and customer-specific requirements.
                        </p>
                        <div className="p-6 bg-sky-50 dark:bg-sky-900/20 rounded-lg border">
                            <Settings className="h-8 w-8 text-sky-600 mb-3" />
                            <p className="text-sm text-muted-foreground">
                                Complete configuration management documentation is under development. Contact sales@regengine.co for details.
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>        </>
    );
}
