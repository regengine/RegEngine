'use client';

import Link from 'next/link';
import { ArrowLeft, Users, Upload, FileSpreadsheet, CheckCircle2, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function PCOSCrewImportPage() {
    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
            <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-lg dark:bg-slate-900/80">
                <div className="container flex h-16 items-center justify-between px-6">
                    <Link href="/pcos" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
                        <ArrowLeft className="h-4 w-4" />
                        <span className="text-sm">Back to PCOS Dashboard</span>
                    </Link>
                    <Button variant="outline" disabled>
                        <Upload className="h-4 w-4 mr-2" />
                        Import Crew List
                    </Button>
                </div>
            </header>

            <main className="container px-6 py-12 max-w-5xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Crew Import</h1>
                    <p className="text-muted-foreground">
                        Bulk import crew member information to auto-generate compliance checklists
                    </p>
                </div>

                <Card className="mb-6">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <FileSpreadsheet className="h-5 w-5 text-purple-600" />
                            How It Works
                        </CardTitle>
                        <CardDescription>
                            Upload a crew list to automatically identify compliance requirements
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="grid md:grid-cols-3 gap-6">
                            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border">
                                <div className="h-8 w-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold mb-3">1</div>
                                <h3 className="font-medium mb-2">Upload Crew List</h3>
                                <p className="text-sm text-muted-foreground">Import CSV or Excel file with crew details</p>
                            </div>
                            <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg border">
                                <div className="h-8 w-8 rounded-full bg-purple-600 text-white flex items-center justify-center font-bold mb-3">2</div>
                                <h3 className="font-medium mb-2">Auto-Detect Risks</h3>
                                <p className="text-sm text-muted-foreground">System identifies minors, union members, special requirements</p>
                            </div>
                            <div className="p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border">
                                <div className="h-8 w-8 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold mb-3">3</div>
                                <h3 className="font-medium mb-2">Generate Checklist</h3>
                                <p className="text-sm text-muted-foreground">Get personalized compliance tasks</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="mb-6">
                    <CardHeader>
                        <CardTitle>Required Information</CardTitle>
                        <CardDescription>
                            Your crew list should include the following columns
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex items-start gap-3 text-sm">
                            <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5" />
                            <div>
                                <span className="font-medium">Name</span>
                                <span className="text-muted-foreground"> — First and last name of crew member</span>
                            </div>
                        </div>
                        <div className="flex items-start gap-3 text-sm">
                            <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5" />
                            <div>
                                <span className="font-medium">Role/Department</span>
                                <span className="text-muted-foreground"> — Job title (e.g., "Director", "Key Grip")</span>
                            </div>
                        </div>
                        <div className="flex items-start gap-3 text-sm">
                            <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5" />
                            <div>
                                <span className="font-medium">Age/DOB</span>
                                <span className="text-muted-foreground"> — For identifying minors (under 18)</span>
                            </div>
                        </div>
                        <div className="flex items-start gap-3 text-sm">
                            <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5" />
                            <div>
                                <span className="font-medium">Union Affiliation</span>
                                <span className="text-muted-foreground"> — Optional: SAG, DGA, IATSE, etc.</span>
                            </div>
                        </div>
                        <div className="flex items-start gap-3 text-sm">
                            <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5" />
                            <div>
                                <span className="font-medium">Start/End Dates</span>
                                <span className="text-muted-foreground"> — Optional: Work dates for scheduling</span>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <div className="p-8 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 text-center">
                    <Users className="h-12 w-12 text-purple-600 mx-auto mb-4" />
                    <h3 className="font-semibold text-lg mb-2">Feature In Development</h3>
                    <p className="text-muted-foreground max-w-2xl mx-auto mb-6">
                        The Crew Import feature is currently being built. Once available, you'll be able to upload your complete
                        crew list and automatically generate compliance requirements based on roles, ages, union status, and special conditions.
                    </p>
                    <Button asChild>
                        <Link href="/pcos">Return to Dashboard</Link>
                    </Button>
                </div>
            </main>
        </div>
    );
}
