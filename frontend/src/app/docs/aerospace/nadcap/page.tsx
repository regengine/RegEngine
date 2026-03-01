"use client";

import Link from "next/link";
import { ArrowLeft, Shield } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";


export default function NADCAPDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 py-12">
                <Link href="/docs/aerospace" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Aerospace Docs
                </Link>

                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">NADCAP Evidence Vault</h1>
                    <p className="text-muted-foreground">
                        Secure special process documentation for NADCAP audits
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>NADCAP Compliance Documentation</CardTitle>
                        <CardDescription>
                            Immutable evidence storage for special process certifications
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <p className="text-muted-foreground mb-4">
                            The NADCAP Evidence Vault provides cryptographically secured storage for heat treat charts,
                            chemical processing records, and non-destructive testing reports required for NADCAP accreditation.
                        </p>
                        <div className="p-6 bg-sky-50 dark:bg-sky-900/20 rounded-lg border">
                            <Shield className="h-8 w-8 text-sky-600 mb-3" />
                            <p className="text-sm text-muted-foreground">
                                NADCAP integration documentation is in active rollout. Contact sales@regengine.co for special process compliance.
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>        </>
    );
}
