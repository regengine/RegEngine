'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, FileText, Upload, FolderOpen, Shield, Search, Filter, Clock, CheckCircle2, AlertCircle, Download, Eye, Trash2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

/* ─────────────────────────────────────────────────────────────
   TYPES & MOCK DATA
   ───────────────────────────────────────────────────────────── */

interface ProductionDocument {
    id: string;
    name: string;
    category: 'permits' | 'insurance' | 'labor' | 'location' | 'safety';
    status: 'verified' | 'pending' | 'expired' | 'draft';
    uploadedAt: string;
    expiresAt: string | null;
    fileSize: string;
}

const CATEGORY_META: Record<string, { label: string; icon: typeof FileText; color: string }> = {
    permits: { label: 'Permits & Licenses', icon: FolderOpen, color: 'text-blue-600' },
    insurance: { label: 'Insurance', icon: Shield, color: 'text-emerald-600' },
    labor: { label: 'Union & Labor', icon: FileText, color: 'text-purple-600' },
    location: { label: 'Location', icon: FolderOpen, color: 'text-amber-600' },
    safety: { label: 'Safety', icon: AlertCircle, color: 'text-red-600' },
};

const MOCK_DOCS: ProductionDocument[] = [
    { id: '1', name: 'FilmLA Permit — Downtown Block A', category: 'permits', status: 'verified', uploadedAt: '2026-02-01', expiresAt: '2026-06-01', fileSize: '2.4 MB' },
    { id: '2', name: 'Certificate of Insurance (COI)', category: 'insurance', status: 'verified', uploadedAt: '2026-01-28', expiresAt: '2026-12-31', fileSize: '1.1 MB' },
    { id: '3', name: 'Workers Compensation Policy', category: 'insurance', status: 'pending', uploadedAt: '2026-02-05', expiresAt: null, fileSize: '3.2 MB' },
    { id: '4', name: 'SAG-AFTRA Modified Low Budget Agreement', category: 'labor', status: 'verified', uploadedAt: '2026-01-20', expiresAt: null, fileSize: '890 KB' },
    { id: '5', name: 'Fire Safety Permit — Stage 12', category: 'safety', status: 'expired', uploadedAt: '2025-11-15', expiresAt: '2026-01-15', fileSize: '450 KB' },
    { id: '6', name: 'Location Agreement — Griffith Park', category: 'location', status: 'draft', uploadedAt: '2026-02-08', expiresAt: null, fileSize: '1.7 MB' },
    { id: '7', name: 'I-9 Employment Verification Bundle', category: 'labor', status: 'verified', uploadedAt: '2026-02-03', expiresAt: null, fileSize: '5.8 MB' },
    { id: '8', name: 'Noise Variance Permit — Night Shoots', category: 'permits', status: 'pending', uploadedAt: '2026-02-10', expiresAt: '2026-04-30', fileSize: '320 KB' },
];

const STATUS_STYLES: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    verified: { label: 'Verified', variant: 'default' },
    pending: { label: 'Pending Review', variant: 'secondary' },
    expired: { label: 'Expired', variant: 'destructive' },
    draft: { label: 'Draft', variant: 'outline' },
};

/* ─────────────────────────────────────────────────────────────
   COMPONENT
   ───────────────────────────────────────────────────────────── */

export default function PCOSDocumentsPage() {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [showUploadZone, setShowUploadZone] = useState(false);

    const filteredDocs = MOCK_DOCS.filter(doc => {
        const matchesSearch = doc.name.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesCategory = !selectedCategory || doc.category === selectedCategory;
        return matchesSearch && matchesCategory;
    });

    const stats = {
        total: MOCK_DOCS.length,
        verified: MOCK_DOCS.filter(d => d.status === 'verified').length,
        pending: MOCK_DOCS.filter(d => d.status === 'pending').length,
        expired: MOCK_DOCS.filter(d => d.status === 'expired').length,
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
            <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-lg dark:bg-slate-900/80">
                <div className="container flex h-16 items-center justify-between px-6">
                    <Link href="/pcos" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
                        <ArrowLeft className="h-4 w-4" />
                        <span className="text-sm">Back to PCOS Dashboard</span>
                    </Link>
                    <Button onClick={() => setShowUploadZone(!showUploadZone)}>
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

                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    <Card>
                        <CardContent className="pt-4 pb-3 text-center">
                            <p className="text-2xl font-bold">{stats.total}</p>
                            <p className="text-xs text-muted-foreground">Total Documents</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 pb-3 text-center">
                            <p className="text-2xl font-bold text-emerald-600">{stats.verified}</p>
                            <p className="text-xs text-muted-foreground">Verified</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 pb-3 text-center">
                            <p className="text-2xl font-bold text-amber-600">{stats.pending}</p>
                            <p className="text-xs text-muted-foreground">Pending Review</p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-4 pb-3 text-center">
                            <p className="text-2xl font-bold text-red-600">{stats.expired}</p>
                            <p className="text-xs text-muted-foreground">Expired</p>
                        </CardContent>
                    </Card>
                </div>

                {/* Category Cards */}
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

                {/* Upload Zone */}
                {showUploadZone && (
                    <Card className="mb-6 border-dashed border-2 border-purple-300">
                        <CardContent className="py-12 text-center">
                            <Upload className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                            <h3 className="font-semibold mb-2">Drop files here or click to browse</h3>
                            <p className="text-sm text-muted-foreground mb-4">
                                Supports PDF, DOCX, JPG, PNG — Max 25 MB per file
                            </p>
                            <Button variant="outline">
                                <Upload className="h-4 w-4 mr-2" />
                                Choose Files
                            </Button>
                        </CardContent>
                    </Card>
                )}

                {/* Evidence Locker */}
                <Card>
                    <CardHeader>
                        <CardTitle>Evidence Locker</CardTitle>
                        <CardDescription>
                            Immutable document storage with cryptographic verification
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {/* Search & Filter */}
                        <div className="flex flex-col sm:flex-row gap-3 mb-4">
                            <div className="flex-1 relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <input
                                    type="text"
                                    placeholder="Search documents..."
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    className="w-full pl-10 pr-4 py-2 rounded-lg border bg-background text-sm"
                                />
                            </div>
                            <div className="flex gap-2 flex-wrap">
                                <Button
                                    variant={selectedCategory === null ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => setSelectedCategory(null)}
                                >
                                    <Filter className="h-3 w-3 mr-1" /> All
                                </Button>
                                {Object.entries(CATEGORY_META).map(([key, meta]) => (
                                    <Button
                                        key={key}
                                        variant={selectedCategory === key ? 'default' : 'outline'}
                                        size="sm"
                                        onClick={() => setSelectedCategory(selectedCategory === key ? null : key)}
                                    >
                                        {meta.label}
                                    </Button>
                                ))}
                            </div>
                        </div>

                        {/* Document List */}
                        <div className="divide-y">
                            {filteredDocs.map(doc => {
                                const catMeta = CATEGORY_META[doc.category];
                                const statusStyle = STATUS_STYLES[doc.status];
                                const CatIcon = catMeta.icon;
                                return (
                                    <div key={doc.id} className="flex items-center gap-4 py-3">
                                        <CatIcon className={`h-5 w-5 ${catMeta.color} shrink-0`} />
                                        <div className="flex-1 min-w-0">
                                            <p className="font-medium text-sm truncate">{doc.name}</p>
                                            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                                                <Clock className="h-3 w-3" />
                                                <span>{doc.uploadedAt}</span>
                                                <span>·</span>
                                                <span>{doc.fileSize}</span>
                                                {doc.expiresAt && (
                                                    <>
                                                        <span>·</span>
                                                        <span>Expires {doc.expiresAt}</span>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                        <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
                                        <div className="flex gap-1">
                                            <Button variant="ghost" size="sm">
                                                <Eye className="h-3.5 w-3.5" />
                                            </Button>
                                            <Button variant="ghost" size="sm">
                                                <Download className="h-3.5 w-3.5" />
                                            </Button>
                                        </div>
                                    </div>
                                );
                            })}
                            {filteredDocs.length === 0 && (
                                <div className="py-8 text-center text-muted-foreground text-sm">
                                    No documents match your search.
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </main>
        </div>
    );
}
