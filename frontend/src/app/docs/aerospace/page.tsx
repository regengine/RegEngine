"use client";

import Link from "next/link";
import { Book, ArrowLeft, FileText, Code, Rocket } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function AerospaceDocsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-6xl mx-auto px-4 py-12">
                <Link href="/verticals/aerospace" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Aerospace Vertical
                </Link>

                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Aerospace Documentation</h1>
                    <p className="text-muted-foreground">
                        AS9100 & FAI Compliance - Complete API reference and guides
                    </p>
                </div>

                <div className="grid md:grid-cols-3 gap-6 mb-8">
                    <Card>
                        <CardContent className="pt-6">
                            <Book className="h-10 w-10 text-sky-600 mb-3" />
                            <h3 className="font-semibold mb-2">Getting Started</h3>
                            <p className="text-sm text-muted-foreground mb-4">Learn the basics and setup your integration</p>
                            <Button variant="outline" size="sm" disabled>View Guide</Button>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <Code className="h-10 w-10 text-sky-600 mb-3" />
                            <h3 className="font-semibold mb-2">API Reference</h3>
                            <p className="text-sm text-muted-foreground mb-4">Complete API endpoint documentation</p>
                            <Button variant="outline" size="sm" disabled>View API Docs</Button>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <Rocket className="h-10 w-10 text-sky-600 mb-3" />
                            <h3 className="font-semibold mb-2">Examples</h3>
                            <p className="text-sm text-muted-foreground mb-4">Code samples and use cases</p>
                            <Button variant="outline" size="sm" disabled>View Examples</Button>
                        </CardContent>
                    </Card>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Documentation Coming Soon</CardTitle>
                        <CardDescription>
                            We're building comprehensive documentation for the Aerospace vertical
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <p className="text-muted-foreground mb-4">
                            Complete API documentation, integration guides, and code examples are currently in development.
                            In the meantime, you can:
                        </p>
                        <ul className="space-y-2 mb-6">
                            <li className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-sky-600" />
                                <Link href="/verticals/aerospace" className="text-sky-600 hover:underline">
                                    View the Aerospace Vertical Overview
                                </Link>
                            </li>
                            <li className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-sky-600" />
                                <span className="text-muted-foreground">Contact sales@regengine.co for API access</span>
                            </li>
                        </ul>
                        <Button asChild>
                            <Link href="/verticals/aerospace">Back to Aerospace Overview</Link>
                        </Button>
                    </CardContent>
                </Card>
            </div>
        </div>        </>
    );
}
