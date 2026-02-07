'use client';

import Link from 'next/link';
import { ArrowLeft, FileText, Upload, FolderOpen, Shield } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function PCOSDocumentsPage() {
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
                        Upload Documents
                    </Button>
                </div>
            </header>

            <main className="container px-6 py-12 max-w-6xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Document Management</h1>
                    <p className="text-muted-foreground">
                        Centralized storage for all production compliance documents
                    </p>
                </div>

                <div className="grid md:grid-cols-3 gap-6 mb-6">
                    <Card>
                        <CardContent className="pt-6">
                            <FolderOpen className="h-10 w-10 text-blue-600 mb-3" />
                            <h3 className="font-semibold mb-1">Permits & Licenses</h3>
                            <p className="text-sm text-muted-foreground">FilmLA, fire safety, location permits</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <Shield className="h-10 w-10 text-emerald-600 mb-3" />
                            <h3 className="font-semibold mb-1">Insurance Documents</h3>
                            <p className="text-sm text-muted-foreground">COI, workers comp, liability insurance</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <FileText className="h-10 w-10 text-purple-600 mb-3" />
                            <h3 className="font-semibold mb-1">Union & Labor Forms</h3>
                            <p className="text-sm text-muted-foreground">SAG contracts, I-9s, timecards</p>
                        </CardContent>
                    </Card>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Evidence Locker</CardTitle>
                        <CardDescription>
                            Immutable document storage with cryptographic verification
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="p-12 bg-muted/50 rounded-lg border-2 border-dashed text-center">
                            <Upload className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                            <h3 className="font-semibold mb-2">Coming Soon</h3>
                            <p className="text-sm text-muted-foreground max-w-md mx-auto mb-6">
                                The PCOS Document Management system is under development. Upload, organize, and verify
                                all production compliance documents with blockchain-anchored proof of authenticity.
                            </p>
                            <div className="flex justify-center gap-3">
                                <Button asChild>
                                    <Link href="/pcos">Return to Dashboard</Link>
                                </Button>
                                <Button variant="outline" disabled>
                                    Upload Documents
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </main>
        </div>
    );
}
