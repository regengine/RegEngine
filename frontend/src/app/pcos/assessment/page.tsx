'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ClipboardCheck, AlertTriangle, FileText, CheckCircle2, Clock, ChevronRight, Shield, BarChart3 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

/* ─────────────────────────────────────────────────────────────
   TYPES & DATA
   ───────────────────────────────────────────────────────────── */

interface AssessmentQuestion {
    id: string;
    category: string;
    question: string;
    options: { label: string; score: number }[];
}

const CATEGORIES = [
    { id: 'permits', label: 'Permits & Licensing', icon: FileText, color: 'text-blue-600' },
    { id: 'safety', label: 'Safety & Insurance', icon: Shield, color: 'text-amber-600' },
    { id: 'labor', label: 'Labor & Union', icon: ClipboardCheck, color: 'text-emerald-600' },
    { id: 'locations', label: 'Location Compliance', icon: AlertTriangle, color: 'text-purple-600' },
];

const QUESTIONS: AssessmentQuestion[] = [
    {
        id: 'q1', category: 'permits',
        question: 'Do you have a current FilmLA or equivalent local film permit?',
        options: [
            { label: 'Yes — current and verified', score: 100 },
            { label: 'Applied — pending approval', score: 60 },
            { label: 'Not yet applied', score: 20 },
            { label: 'Not sure what\'s required', score: 0 },
        ],
    },
    {
        id: 'q2', category: 'permits',
        question: 'Are all required fire/safety permits obtained for your shooting locations?',
        options: [
            { label: 'Yes — all locations covered', score: 100 },
            { label: 'Partially — some locations still pending', score: 50 },
            { label: 'No — not yet obtained', score: 10 },
        ],
    },
    {
        id: 'q3', category: 'safety',
        question: 'Do you have a Certificate of Insurance (COI) covering all production activities?',
        options: [
            { label: 'Yes — comprehensive coverage', score: 100 },
            { label: 'Yes — basic coverage only', score: 60 },
            { label: 'In process of obtaining', score: 30 },
            { label: 'No insurance obtained', score: 0 },
        ],
    },
    {
        id: 'q4', category: 'safety',
        question: 'Is there a designated safety coordinator or medic on set?',
        options: [
            { label: 'Yes — full-time safety team', score: 100 },
            { label: 'Yes — part-time or on-call', score: 70 },
            { label: 'No — but planned', score: 30 },
            { label: 'No safety personnel assigned', score: 0 },
        ],
    },
    {
        id: 'q5', category: 'labor',
        question: 'Are all cast/crew contracts compliant with SAG-AFTRA or applicable union agreements?',
        options: [
            { label: 'Yes — fully compliant', score: 100 },
            { label: 'Mixed — some non-union crew', score: 60 },
            { label: 'Non-union production', score: 40 },
            { label: 'Unsure of requirements', score: 10 },
        ],
    },
    {
        id: 'q6', category: 'labor',
        question: 'Are I-9 employment verification forms completed for all crew?',
        options: [
            { label: 'Yes — 100% completed and filed', score: 100 },
            { label: 'Mostly — a few pending', score: 60 },
            { label: 'Not yet started', score: 0 },
        ],
    },
    {
        id: 'q7', category: 'locations',
        question: 'Have all locations been assessed for environmental and noise compliance?',
        options: [
            { label: 'Yes — all assessed and cleared', score: 100 },
            { label: 'Partially assessed', score: 50 },
            { label: 'No assessment conducted', score: 0 },
        ],
    },
    {
        id: 'q8', category: 'locations',
        question: 'Do you have signed location agreements for all shoot sites?',
        options: [
            { label: 'Yes — all signed and filed', score: 100 },
            { label: 'Some verbal agreements only', score: 40 },
            { label: 'No agreements in place', score: 0 },
        ],
    },
];

function getRiskLevel(score: number): { label: string; color: string; bgColor: string } {
    if (score >= 80) return { label: 'Low Risk', color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' };
    if (score >= 60) return { label: 'Moderate Risk', color: 'text-amber-400', bgColor: 'bg-amber-500/10' };
    if (score >= 40) return { label: 'High Risk', color: 'text-orange-400', bgColor: 'bg-orange-500/10' };
    return { label: 'Critical Risk', color: 'text-red-400', bgColor: 'bg-red-500/10' };
}

/* ─────────────────────────────────────────────────────────────
   COMPONENT
   ───────────────────────────────────────────────────────────── */

export default function PCOSAssessmentPage() {
    const [answers, setAnswers] = useState<Record<string, number>>({});
    const [showResults, setShowResults] = useState(false);

    const totalQuestions = QUESTIONS.length;
    const answeredCount = Object.keys(answers).length;
    const progress = Math.round((answeredCount / totalQuestions) * 100);

    const handleAnswer = (questionId: string, score: number) => {
        setAnswers(prev => ({ ...prev, [questionId]: score }));
    };

    const categoryScores = CATEGORIES.map(cat => {
        const catQuestions = QUESTIONS.filter(q => q.category === cat.id);
        const catAnswers = catQuestions.filter(q => answers[q.id] !== undefined);
        const avg = catAnswers.length > 0
            ? Math.round(catAnswers.reduce((sum, q) => sum + (answers[q.id] ?? 0), 0) / catAnswers.length)
            : 0;
        return { ...cat, score: avg, answered: catAnswers.length, total: catQuestions.length };
    });

    const overallScore = answeredCount > 0
        ? Math.round(Object.values(answers).reduce((a, b) => a + b, 0) / answeredCount)
        : 0;

    const risk = getRiskLevel(overallScore);

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
            <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-lg dark:bg-slate-900/80">
                <div className="container flex h-16 items-center justify-between px-6">
                    <Link href="/pcos" className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors">
                        <ArrowLeft className="h-4 w-4" />
                        <span className="text-sm">Back to PCOS Dashboard</span>
                    </Link>
                    <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200">
                        Assessment Tool
                    </Badge>
                </div>
            </header>

            <main className="container px-6 py-12 max-w-4xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Compliance Assessment</h1>
                    <p className="text-muted-foreground">
                        Evaluate your production's compliance readiness across all critical categories
                    </p>
                </div>

                {/* Progress Bar */}
                <Card className="mb-6">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Progress</span>
                            <span className="text-sm text-muted-foreground">{answeredCount}/{totalQuestions} questions</span>
                        </div>
                        <div className="w-full bg-muted rounded-full h-2.5">
                            <div
                                className="bg-purple-600 h-2.5 rounded-full transition-all duration-500"
                                style={{ width: `${progress}%` }}
                            />
                        </div>
                    </CardContent>
                </Card>

                {/* Category Overview */}
                <div className="grid md:grid-cols-4 gap-3 mb-8">
                    {categoryScores.map(cat => {
                        const Icon = cat.icon;
                        return (
                            <Card key={cat.id} className="text-center">
                                <CardContent className="pt-4 pb-3">
                                    <Icon className={`h-6 w-6 mx-auto mb-1 ${cat.color}`} />
                                    <p className="text-xs font-medium mb-1">{cat.label}</p>
                                    <p className="text-lg font-bold">{cat.answered > 0 ? `${cat.score}%` : '—'}</p>
                                </CardContent>
                            </Card>
                        );
                    })}
                </div>

                {/* Questions */}
                {!showResults && (
                    <div className="space-y-4">
                        {QUESTIONS.map((q, idx) => {
                            const cat = CATEGORIES.find(c => c.id === q.category);
                            return (
                                <Card key={q.id}>
                                    <CardHeader className="pb-3">
                                        <div className="flex items-center gap-2 mb-1">
                                            <Badge variant="outline" className="text-xs">{cat?.label}</Badge>
                                            <span className="text-xs text-muted-foreground">Question {idx + 1}</span>
                                        </div>
                                        <CardTitle className="text-base">{q.question}</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="grid gap-2">
                                            {q.options.map((opt, oi) => (
                                                <button
                                                    key={oi}
                                                    onClick={() => handleAnswer(q.id, opt.score)}
                                                    className={`text-left px-4 py-3 rounded-lg border transition-all text-sm ${answers[q.id] === opt.score
                                                            ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                                                            : 'border-border hover:border-purple-300 hover:bg-muted/50'
                                                        }`}
                                                >
                                                    {opt.label}
                                                </button>
                                            ))}
                                        </div>
                                    </CardContent>
                                </Card>
                            );
                        })}

                        {answeredCount === totalQuestions && (
                            <div className="text-center py-6">
                                <Button size="lg" onClick={() => setShowResults(true)}>
                                    <BarChart3 className="h-4 w-4 mr-2" />
                                    View Results
                                    <ChevronRight className="h-4 w-4 ml-1" />
                                </Button>
                            </div>
                        )}
                    </div>
                )}

                {/* Results */}
                {showResults && (
                    <div className="space-y-6">
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <BarChart3 className="h-5 w-5 text-purple-600" />
                                    Assessment Results
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-center mb-6">
                                    <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${risk.bgColor}`}>
                                        <span className={`text-3xl font-bold ${risk.color}`}>{overallScore}%</span>
                                    </div>
                                    <p className={`text-lg font-semibold mt-2 ${risk.color}`}>{risk.label}</p>
                                </div>

                                <div className="space-y-4">
                                    {categoryScores.map(cat => {
                                        const catRisk = getRiskLevel(cat.score);
                                        const Icon = cat.icon;
                                        return (
                                            <div key={cat.id} className="flex items-center gap-4">
                                                <Icon className={`h-5 w-5 ${cat.color} shrink-0`} />
                                                <div className="flex-1">
                                                    <div className="flex justify-between text-sm mb-1">
                                                        <span className="font-medium">{cat.label}</span>
                                                        <span className={catRisk.color}>{cat.score}%</span>
                                                    </div>
                                                    <div className="w-full bg-muted rounded-full h-2">
                                                        <div
                                                            className="bg-purple-600 h-2 rounded-full transition-all"
                                                            style={{ width: `${cat.score}%` }}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Recommendations */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                                    Recommended Actions
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-3">
                                    {categoryScores
                                        .filter(c => c.score < 80)
                                        .map(cat => (
                                            <li key={cat.id} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                                                <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                                                <div>
                                                    <p className="font-medium text-sm">{cat.label} — needs attention</p>
                                                    <p className="text-xs text-muted-foreground mt-0.5">
                                                        Score: {cat.score}% — review and address gaps before production begins
                                                    </p>
                                                </div>
                                            </li>
                                        ))}
                                    {categoryScores.every(c => c.score >= 80) && (
                                        <li className="flex items-start gap-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20">
                                            <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5" />
                                            <p className="text-sm">All categories are in good standing. Continue monitoring.</p>
                                        </li>
                                    )}
                                </ul>
                            </CardContent>
                        </Card>

                        <div className="flex justify-center gap-3">
                            <Button variant="outline" onClick={() => { setShowResults(false); setAnswers({}); }}>
                                <Clock className="h-4 w-4 mr-2" />
                                Retake Assessment
                            </Button>
                            <Button asChild>
                                <Link href="/pcos">Return to Dashboard</Link>
                            </Button>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
