'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
    Shield,
    FileText,
    Users,
    Clock,
    AlertTriangle,
    CheckCircle2,
    ChevronRight,
    Upload,
    Calendar,
    MapPin,
    DollarSign,
    Baby,
    Building2,
    FileCheck,
    ExternalLink,
    ArrowLeft,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { RiskHeatMap } from '@/components/pcos/RiskHeatMap';
import { HowToGuide } from '@/components/pcos/HowToGuide';
import { ComplianceTimeline } from '@/components/pcos/ComplianceTimeline';
import { DocumentUploadModal, DocumentCategory } from '@/components/pcos/DocumentUploadModal';

// Mock data for demonstration
const mockProject = {
    name: 'Sunset Boulevard Short Film',
    type: 'Narrative Short',
    status: 'Pre-Production',
    shootStart: '2026-02-05',
    shootEnd: '2026-02-08',
    locations: ['LA City', 'Burbank'],
    crewCount: 15,
    unionStatus: 'SAG-AFTRA',
    hasMinors: true,
    budget: '$250K - $500K',
};

const mockRiskCategories = [
    { id: 'labor', name: 'Labor & Classification', score: 35, tasks: 2, status: 'medium' as const },
    { id: 'permits', name: 'Permits & Locations', score: 65, tasks: 3, status: 'high' as const },
    { id: 'insurance', name: 'Insurance & Liability', score: 20, tasks: 1, status: 'low' as const },
    { id: 'union', name: 'Union Compliance', score: 15, tasks: 0, status: 'low' as const },
    { id: 'minors', name: 'Minor Protection', score: 80, tasks: 4, status: 'critical' as const },
    { id: 'safety', name: 'Safety & IIPP', score: 40, tasks: 2, status: 'medium' as const },
];

const mockGuidance = [
    {
        id: 'minor-permit',
        title: 'Minor Work Permit (Form B1-4)',
        category: 'minors',
        priority: 'critical' as const,
        deadline: '2026-01-29',
        daysUntil: 7,
        steps: [
            { id: 1, text: 'Parent/guardian completes Section A of Form B1-4', completed: false },
            { id: 2, text: 'Production company completes Section B', completed: false },
            { id: 3, text: 'Submit to CA Labor Commissioner', completed: false, link: 'https://dir.ca.gov/dlse/permit.html' },
        ],
        documentsRequired: ['Birth certificate or passport', 'School enrollment verification'],
        estimatedTime: '5-7 business days',
    },
    {
        id: 'filmla-permit',
        title: 'FilmLA Permit Application',
        category: 'permits',
        priority: 'high' as const,
        deadline: '2026-01-28',
        daysUntil: 6,
        steps: [
            { id: 1, text: 'Create FilmLA account', completed: true },
            { id: 2, text: 'Complete online permit application', completed: true },
            { id: 3, text: 'Upload insurance certificate (COI)', completed: false },
            { id: 4, text: 'Pay permit fee', completed: false },
            { id: 5, text: 'Await approval (2-3 days)', completed: false },
        ],
        documentsRequired: ['Certificate of Insurance', 'Location agreement'],
        estimatedTime: '2-3 business days',
    },
    {
        id: 'workers-comp',
        title: 'Workers\' Compensation Verification',
        category: 'insurance',
        priority: 'medium' as const,
        deadline: '2026-02-01',
        daysUntil: 10,
        steps: [
            { id: 1, text: 'Obtain WC policy from insurance broker', completed: true },
            { id: 2, text: 'Verify coverage includes all crew classifications', completed: true },
            { id: 3, text: 'Upload policy to evidence locker', completed: false },
        ],
        documentsRequired: ['Workers\' Comp Policy Declaration Page'],
        estimatedTime: '1 day',
    },
    {
        id: 'studio-teacher',
        title: 'Studio Teacher Confirmation',
        category: 'minors',
        priority: 'critical' as const,
        deadline: '2026-01-30',
        daysUntil: 8,
        steps: [
            { id: 1, text: 'Identify certified studio teacher', completed: false },
            { id: 2, text: 'Confirm availability for all minor shoot days', completed: false },
            { id: 3, text: 'Execute deal memo', completed: false },
        ],
        documentsRequired: ['Studio teacher certification', 'Deal memo'],
        estimatedTime: '1-2 days',
    },
];

const mockTimeline: { date: string; label: string; category: string; status: 'pending' | 'completed' | 'upcoming' }[] = [
    { date: '2026-01-28', label: 'FilmLA Permit Due', category: 'permits', status: 'pending' },
    { date: '2026-01-29', label: 'Minor Permit Due', category: 'minors', status: 'pending' },
    { date: '2026-01-30', label: 'Studio Teacher Confirmed', category: 'minors', status: 'pending' },
    { date: '2026-02-01', label: 'Insurance Verified', category: 'insurance', status: 'pending' },
    { date: '2026-02-03', label: 'Greenlight Review', category: 'gate', status: 'pending' },
    { date: '2026-02-05', label: 'First Shoot Day', category: 'production', status: 'upcoming' },
];

export default function PCOSDashboard() {
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [uploadModalOpen, setUploadModalOpen] = useState(false);
    const [preselectedCategory, setPreselectedCategory] = useState<DocumentCategory | undefined>();
    const overallRisk = Math.round(mockRiskCategories.reduce((sum, c) => sum + c.score, 0) / mockRiskCategories.length);
    const completedTasks = 5;
    const totalTasks = 12;
    const completionPercent = Math.round((completedTasks / totalTasks) * 100);

    const filteredGuidance = selectedCategory
        ? mockGuidance.filter(g => g.category === selectedCategory)
        : mockGuidance;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
            {/* Header */}
            <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-lg dark:bg-slate-900/80">
                <div className="container flex h-16 items-center justify-between px-6">
                    <div className="flex items-center gap-4">
                        <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
                            <ArrowLeft className="h-4 w-4" />
                            <span className="text-sm">RegEngine</span>
                        </Link>
                        <div className="h-6 w-px bg-border" />
                        <div className="flex items-center gap-2">
                            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
                                <Shield className="h-4 w-4 text-white" />
                            </div>
                            <div>
                                <h1 className="font-semibold text-sm">Production Compliance OS</h1>
                                <p className="text-xs text-muted-foreground">{mockProject.name}</p>
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200">
                            {mockProject.status}
                        </Badge>
                        <Button size="sm" onClick={() => setUploadModalOpen(true)}>
                            <Upload className="h-4 w-4 mr-2" />
                            Upload Documents
                        </Button>
                    </div>
                </div>
            </header>

            <main className="container px-6 py-8 space-y-8">
                {/* Project Overview Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-lg bg-blue-100 flex items-center justify-center">
                                    <Calendar className="h-5 w-5 text-blue-600" />
                                </div>
                                <div>
                                    <p className="text-sm text-muted-foreground">Shoot Dates</p>
                                    <p className="font-semibold">Feb 5-8, 2026</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-lg bg-emerald-100 flex items-center justify-center">
                                    <Users className="h-5 w-5 text-emerald-600" />
                                </div>
                                <div>
                                    <p className="text-sm text-muted-foreground">Crew Size</p>
                                    <p className="font-semibold">{mockProject.crewCount} people</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-lg bg-amber-100 flex items-center justify-center">
                                    <MapPin className="h-5 w-5 text-amber-600" />
                                </div>
                                <div>
                                    <p className="text-sm text-muted-foreground">Locations</p>
                                    <p className="font-semibold">{mockProject.locations.join(', ')}</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-3">
                                <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${mockProject.hasMinors ? 'bg-red-100' : 'bg-slate-100'}`}>
                                    <Baby className={`h-5 w-5 ${mockProject.hasMinors ? 'text-red-600' : 'text-slate-600'}`} />
                                </div>
                                <div>
                                    <p className="text-sm text-muted-foreground">Minors</p>
                                    <p className="font-semibold">{mockProject.hasMinors ? 'Yes — Extra Requirements' : 'None'}</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Main Dashboard Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left Column - Risk & Progress */}
                    <div className="space-y-6">
                        {/* Overall Status */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                                    Greenlight Status
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-muted-foreground">Overall Risk Score</span>
                                    <Badge variant={overallRisk > 50 ? 'destructive' : overallRisk > 30 ? 'secondary' : 'default'}>
                                        {overallRisk}/100
                                    </Badge>
                                </div>
                                <Progress value={100 - overallRisk} className="h-3" />
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-muted-foreground">Tasks Completed</span>
                                    <span className="font-medium">{completedTasks}/{totalTasks} ({completionPercent}%)</span>
                                </div>
                                <Progress value={completionPercent} className="h-2" />
                                <div className="pt-2 border-t">
                                    <p className="text-sm text-amber-600 flex items-center gap-2">
                                        <Clock className="h-4 w-4" />
                                        {totalTasks - completedTasks} blocking items remain
                                    </p>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Risk Heat Map */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg">Risk Assessment</CardTitle>
                                <CardDescription>Click a category to filter guidance</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <RiskHeatMap
                                    categories={mockRiskCategories}
                                    selectedCategory={selectedCategory}
                                    onSelectCategory={setSelectedCategory}
                                />
                            </CardContent>
                        </Card>
                    </div>

                    {/* Center Column - How-To Guides */}
                    <div className="lg:col-span-2 space-y-6">
                        {/* Timeline */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <Calendar className="h-5 w-5 text-blue-500" />
                                    Compliance Timeline
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ComplianceTimeline events={mockTimeline} />
                            </CardContent>
                        </Card>

                        {/* How-To Guides */}
                        <Card>
                            <CardHeader>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <CardTitle className="text-lg flex items-center gap-2">
                                            <FileCheck className="h-5 w-5 text-emerald-500" />
                                            How-To Guides
                                        </CardTitle>
                                        <CardDescription>
                                            {selectedCategory
                                                ? `Showing ${filteredGuidance.length} items for ${mockRiskCategories.find(c => c.id === selectedCategory)?.name}`
                                                : `${mockGuidance.length} action items`
                                            }
                                        </CardDescription>
                                    </div>
                                    {selectedCategory && (
                                        <Button variant="ghost" size="sm" onClick={() => setSelectedCategory(null)}>
                                            Clear filter
                                        </Button>
                                    )}
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {filteredGuidance.map((guide) => (
                                    <HowToGuide
                                        key={guide.id}
                                        guide={guide}
                                        onUpload={() => {
                                            setPreselectedCategory(guide.category as DocumentCategory);
                                            setUploadModalOpen(true);
                                        }}
                                    />
                                ))}
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </main>

            {/* Upload Modal */}
            <DocumentUploadModal
                open={uploadModalOpen}
                onOpenChange={(open) => {
                    setUploadModalOpen(open);
                    if (!open) setPreselectedCategory(undefined);
                }}
                preselectedCategory={preselectedCategory}
                onUploadComplete={(files, category) => {
                    // TODO: Integrate with backend API when available
                }}
            />
        </div>
    );
}
