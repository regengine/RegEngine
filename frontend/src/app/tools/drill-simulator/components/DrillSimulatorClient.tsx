'use client';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import {
    Play, CheckCircle2, AlertTriangle, FileText,
    ArrowRight, Clock, Loader2, Network, Upload, Download,
    ChevronDown, ChevronRight, Timer, Shield, Zap,
    TrendingUp, RotateCcw,
} from 'lucide-react';
import { toast } from '@/components/ui/use-toast';
import {
    parseCSV, validateRecords, generateSampleCSV, getScoreColor,
    getSeverityColor, getSeverityBadgeColor,
    type ValidationResult,
} from '../lib/record-validator';
import { cn } from '@/lib/utils';
import { trackToolRunStarted, trackToolRunCompleted } from '@/lib/conversion-events';

type Phase = 'scenario' | 'upload' | 'analyzing' | 'results' | 'report';

interface DrillState {
    selectedScenario: string | null;
    uploadedFile: File | null;
    validationResult: ValidationResult | null;
    phase: Phase;
    drillStartTime: number | null;
    uploadTime: number | null;
}

const scenarios = [
    {
        id: 'produce',
        title: 'Fresh Produce Supplier',
        description: 'Multi-state leafy greens distributor with 500+ retail customers',
        complexity: 'High',
        recordCount: '2,000+',
    },
    {
        id: 'dairy',
        title: 'Dairy Processing Facility',
        description: 'Fluid milk processor with complex ingredients and co-packers',
        complexity: 'Medium',
        recordCount: '800+',
    },
    {
        id: 'supplements',
        title: 'Supplement Manufacturer',
        description: 'Multi-ingredient dietary supplements with international suppliers',
        complexity: 'Very High',
        recordCount: '5,000+',
    },
];

const analysisStages = [
    { name: 'Parsing records...', duration: 500 },
    { name: 'Mapping CTEs and KDEs...', duration: 800 },
    { name: 'Checking chain of custody...', duration: 600 },
    { name: 'Analyzing timeline gaps...', duration: 700 },
    { name: 'Calculating self-check score...', duration: 500 },
];

export function DrillSimulatorClient() {
    const [state, setState] = useState<DrillState>({
        selectedScenario: null,
        uploadedFile: null,
        validationResult: null,
        phase: 'scenario',
        drillStartTime: null,
        uploadTime: null,
    });

    const [dragActive, setDragActive] = useState(false);
    const [currentStage, setCurrentStage] = useState(0);
    const [expandedFinding, setExpandedFinding] = useState<number | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const analysisInFlightRef = useRef(false);

    // Timer for SLA countdown
    const [timeRemaining, setTimeRemaining] = useState(24 * 60 * 60);

    useEffect(() => {
        if (state.phase !== 'upload') return;

        const timer = setInterval(() => {
            setTimeRemaining((prev) => {
                if (prev <= 0) return 0;
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, [state.phase]);

    const formatTime = (seconds: number) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    const handleScenarioSelect = (scenarioId: string, drillStartTime: number) => {
        setState({
            ...state,
            selectedScenario: scenarioId,
            phase: 'upload',
            drillStartTime,
            uploadTime: null,
            validationResult: null,
        });
        setTimeRemaining(24 * 60 * 60);
    };

    const handleDrag = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            e.stopPropagation();
            if (e.type === 'dragenter' || e.type === 'dragover') {
                setDragActive(true);
            } else if (e.type === 'dragleave') {
                setDragActive(false);
            }
        },
        []
    );

    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            processFile(e.target.files[0]);
        }
    };

    const processFile = (file: File) => {
        const validExtensions = ['.csv', '.tsv', '.xlsx'];
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();

        if (!validExtensions.includes(ext)) {
            toast({
                variant: 'destructive',
                title: 'Invalid file type',
                description: `Only CSV, TSV, and XLSX files are supported. You uploaded a ${ext} file.`,
            });
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            toast({
                variant: 'destructive',
                title: 'File too large',
                description: `Maximum file size is 10 MB. Your file is ${(file.size / (1024 * 1024)).toFixed(1)} MB.`,
            });
            return;
        }

        setState({
            ...state,
            uploadedFile: file,
        });
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        const files = e.dataTransfer.files;
        if (files && files[0]) {
            processFile(files[0]);
        }
    };

    const handleAnalyze = async () => {
        if (!state.uploadedFile || analysisInFlightRef.current) return;
        analysisInFlightRef.current = true;
        trackToolRunStarted('drill-simulator');

        setState({ ...state, phase: 'analyzing' });
        setCurrentStage(0);

        try {
            const text = await state.uploadedFile.text();
            const records = parseCSV(text);
            const result = validateRecords(records, new Date(state.drillStartTime || Date.now()));

            for (let i = 0; i < analysisStages.length; i++) {
                await new Promise((resolve) =>
                    setTimeout(resolve, analysisStages[i].duration)
                );
                setCurrentStage(i + 1);
            }

            setState({
                ...state,
                phase: 'results',
                validationResult: result,
                uploadTime: Date.now(),
            });
            trackToolRunCompleted('drill-simulator', 'success');
        } catch {
            trackToolRunCompleted('drill-simulator', 'error');
            setState((current) => ({ ...current, phase: 'upload' }));
        } finally {
            analysisInFlightRef.current = false;
        }
    };

    const handleLoadSampleData = async () => {
        const csv = generateSampleCSV();
        const blob = new Blob([csv], { type: 'text/csv' });
        const file = new File([blob], 'sample-records.csv', { type: 'text/csv' });
        setState({ ...state, uploadedFile: file });
    };

    const handleDownloadSample = () => {
        const csv = generateSampleCSV();
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'sample-traceability-records.csv';
        a.click();
        URL.revokeObjectURL(url);
    };

    const handleDownloadReport = () => {
        if (!state.validationResult) return;

        const result = state.validationResult;
        const scenarioName =
            scenarios.find((s) => s.id === state.selectedScenario)?.title ||
            'Drill';

        const report = `FDA RECALL DRILL SIMULATOR: FULL REPORT
Generated: ${new Date().toISOString()}

SCENARIO: ${scenarioName}
RECORDS ANALYZED: ${result.totalRecords}
OVERALL SCORE: ${result.scores.overallScore.toFixed(1)}/100 (${result.scores.grade})

COMPLIANCE BREAKDOWN:
• Critical Tracking Event (CTE) Coverage: ${result.scores.cteCompleteness.toFixed(1)}/100
• Key Data Element (KDE) Completeness: ${result.scores.kdeCompleteness.toFixed(1)}/100
• Chain of Custody: ${result.scores.chainIntegrity.toFixed(1)}/100
• Timeline Integrity: ${result.scores.timelineCoverage.toFixed(1)}/100
• Data Quality: ${result.scores.dataQuality.toFixed(1)}/100

FINDINGS (${result.findings.length} total):
${result.findings
    .map(
        (f, idx) =>
            `
${idx + 1}. [${f.severity.toUpperCase()}] ${f.category}
   Message: ${f.message}
   Citation: ${f.citation}
   Affected Records: ${f.affectedRows.length}
   Recommendation: ${f.recommendation}
`
    )
    .join('')}

TRACEABILITY GAPS (${result.gaps.length} identified):
${result.gaps
    .map(
        (g, idx) =>
            `
${idx + 1}. Gap: ${g.gapType}
   Description: ${g.description}
   Details: ${g.details}
   Citation: ${g.citation}
`
    )
    .join('')}

SELF-CHECK RESULT: ${result.scores.overallScore >= 70 ? 'No gaps indicated by this check' : 'Gaps indicated. Review below'}
STATUS: ${
            result.scores.overallScore >= 70
                ? 'Self-check found no gaps in the dimensions evaluated below. This is a self-reported indicator based on the columns you uploaded; it is not an FDA determination and does not evaluate all §1.1455 KDEs or CTEs.'
                : 'Self reported gaps in the dimensions evaluated below. Review the items, then verify against the full §1.1455 record set.'
        }

100% Client-Side Analysis · No data transmitted · RegEngine Audit Trail
`;

        const blob = new Blob([report], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `drill-report-${Date.now()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const handleReset = () => {
        setState({
            selectedScenario: null,
            uploadedFile: null,
            validationResult: null,
            phase: 'scenario',
            drillStartTime: null,
            uploadTime: null,
        });
        setExpandedFinding(null);
        setCurrentStage(0);
    };

    const renderPhase = (): React.ReactNode => {
        switch (state.phase) {
            case 'scenario':
                return renderScenario();
            case 'upload':
                return renderUpload();
            case 'analyzing':
                return renderAnalyzing();
            case 'results':
                return renderResults();
            default:
                return null;
        }
    };

    const renderScenario = (): React.ReactNode => (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full"
        >
            <div className="mb-10 text-center">
                <h2 className="text-heading text-re-text-primary">
                    Rehearse Your FSMA 204 Records-on-Request Workflow
                </h2>
                <p className="mx-auto mt-3 max-w-[70ch] text-ui text-re-text-secondary">
                    Upload your traceability records. The drill checks file shape, column-level completeness,
                    Critical Tracking Event (CTE) coverage, and Key Data Element (KDE) completeness. No data leaves your browser. This is a self-paced
                    rehearsal, not an FDA simulation or compliance determination.
                </p>
            </div>

            <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
                {scenarios.map((scenario) => (
                    <button
                        key={scenario.id}
                        type="button"
                        onClick={() => handleScenarioSelect(scenario.id, Date.now())}
                        className="rounded-lg border border-re-border bg-re-surface-card p-5 text-left transition-colors duration-120 hover:border-re-border-strong hover:bg-re-surface-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-base motion-reduce:transition-none"
                    >
                        <div className="mb-3 flex items-start justify-between gap-3">
                            <h3 className="text-subheading text-re-text-primary">
                                {scenario.title}
                            </h3>
                            <Badge tone="neutral" size="sm">{scenario.complexity}</Badge>
                        </div>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            {scenario.description}
                        </p>
                        <div className="flex items-center gap-2 text-small text-re-text-muted">
                            <FileText size={14} strokeWidth={1.75} aria-hidden="true" />
                            {scenario.recordCount} records
                        </div>
                    </button>
                ))}
            </div>

            <div className="mb-8 flex flex-col justify-center gap-4 sm:flex-row">
                <Button size="lg" leadingIcon={<Play size={18} strokeWidth={1.75} aria-hidden="true" />}>
                    Start Drill: Upload Your Records
                </Button>
                <Button
                    size="lg"
                    variant="secondary"
                    onClick={handleDownloadSample}
                    leadingIcon={<Download size={18} strokeWidth={1.75} aria-hidden="true" />}
                >
                    Download Sample CSV
                </Button>
            </div>

            <div className="flex items-center justify-center gap-2 text-small text-re-text-muted">
                <Shield size={16} strokeWidth={1.75} aria-hidden="true" />
                100% client-side • Your data never leaves your browser
            </div>
        </motion.div>
    );

    const renderUpload = (): React.ReactNode => (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="mx-auto w-full max-w-2xl"
        >
            <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-heading text-re-text-primary">
                    Upload Your Records
                </h2>
                <div className="flex items-center gap-2 font-mono text-ui tabular-nums text-re-text-primary">
                    <Timer size={20} strokeWidth={1.75} aria-hidden="true" />
                    {formatTime(timeRemaining)}
                </div>
            </div>

            <Card className="mb-6" padding="compact">
                <h3 className="text-subheading text-re-text-primary">
                    Scenario: {scenarios.find((s) => s.id === state.selectedScenario)?.title}
                </h3>
                <p className="mt-1 text-ui text-re-text-secondary">
                    {scenarios.find((s) => s.id === state.selectedScenario)?.description}
                </p>
            </Card>

            <div
                className={cn(
                    'cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors duration-120 motion-reduce:transition-none sm:p-12',
                    dragActive
                        ? 'border-re-border-strong bg-re-surface-inset'
                        : 'border-re-border hover:border-re-border-strong'
                )}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.tsv,.xlsx"
                    aria-label="Upload Your Records"
                    onChange={handleFileInput}
                    className="hidden"
                />
                <Upload
                    size={24}
                    strokeWidth={1.75}
                    aria-hidden="true"
                    className="mx-auto mb-4 text-re-text-tertiary"
                />
                <h3 className="mb-2 text-subheading text-re-text-primary">
                    {state.uploadedFile ? state.uploadedFile.name : 'Drop your file here'}
                </h3>
                <p className="text-ui text-re-text-secondary">
                    {state.uploadedFile
                        ? `${(state.uploadedFile.size / 1024).toFixed(0)} KB`
                        : 'or click to browse'}
                </p>
                <p className="mt-2 text-small text-re-text-muted">
                    CSV, TSV, or XLSX • Max 10MB
                </p>
            </div>

            <div className="mb-6 mt-6">
                <button
                    type="button"
                    className="flex items-center gap-2 rounded-sm text-ui font-medium text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                >
                    <ChevronRight size={16} strokeWidth={1.75} aria-hidden="true" />
                    What should my file contain?
                </button>
                <Callout tone="neutral" role="note" className="mt-3">
                    <p className="mb-2 font-mono uppercase text-label text-re-text-muted">
                        Required columns:
                    </p>
                    <ul className="space-y-1 text-small text-re-text-secondary">
                        <li>• event_type (ship, receive, transform)</li>
                        <li>• event_date, event_time</li>
                        <li>• lot_code, product_name</li>
                        <li>• quantity, unit</li>
                        <li>• from_party, to_party</li>
                        <li>• location</li>
                    </ul>
                </Callout>
            </div>

            <div className="flex flex-col gap-4 sm:flex-row">
                <Button
                    size="lg"
                    onClick={handleAnalyze}
                    disabled={!state.uploadedFile}
                    className="flex-1"
                    leadingIcon={<Zap size={18} strokeWidth={1.75} aria-hidden="true" />}
                >
                    Analyze My Records
                </Button>
                <Button
                    size="lg"
                    variant="secondary"
                    onClick={handleLoadSampleData}
                >
                    Load Sample Data
                </Button>
            </div>
        </motion.div>
    );

    const renderAnalyzing = (): React.ReactNode => (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="mx-auto w-full max-w-2xl"
        >
            <div className="mb-12 text-center" aria-busy="true">
                <h2 className="mb-8 text-heading text-re-text-primary">
                    Analyzing Your Records
                </h2>

                <div className="space-y-4 text-left">
                    {analysisStages.map((stage, idx) => (
                        <div key={idx} className="flex items-center gap-4">
                            <div className="flex h-8 w-8 items-center justify-center">
                                {idx < currentStage ? (
                                    <CheckCircle2
                                        size={20}
                                        strokeWidth={1.75}
                                        aria-hidden="true"
                                        className="text-re-text-tertiary"
                                    />
                                ) : idx === currentStage ? (
                                    <Loader2
                                        size={20}
                                        strokeWidth={1.75}
                                        aria-hidden="true"
                                        className="animate-spin text-re-text-primary motion-reduce:animate-none"
                                    />
                                ) : (
                                    <span
                                        className="h-5 w-5 rounded-full border border-re-border"
                                        aria-hidden="true"
                                    />
                                )}
                            </div>
                            <span
                                className={cn(
                                    'text-ui',
                                    idx < currentStage
                                        ? 'text-re-text-secondary'
                                        : idx === currentStage
                                            ? 'font-medium text-re-text-primary'
                                            : 'text-re-text-primary'
                                )}
                            >
                                {stage.name}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </motion.div>
    );

    const renderResults = (): React.ReactNode => {
        if (!state.validationResult) return null;

        const result = state.validationResult;
        const responseTime = state.uploadTime
            ? Math.round((state.uploadTime - (state.drillStartTime || 0)) / 1000)
            : 0;

        const gapSummary =
            result.findings.length === 0
                ? 'No gaps indicated'
                : `${result.findings.length} gap${result.findings.length === 1 ? '' : 's'} indicated`;

        const teaser: React.ReactNode = (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="w-full"
            >
                <h2 className="mb-8 text-center text-heading text-re-text-primary">
                    Self-Check Summary
                </h2>

                <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2">
                    <Card padding="compact">
                        <div className="text-center">
                            <div className="mb-4 flex justify-center">
                                <ScoreCircle score={result.scores.overallScore} />
                            </div>
                            <Badge tone="info">{gapSummary}</Badge>
                            <p className="mt-2 text-small text-re-text-tertiary">
                                Self-check on synthetic drill data. Not a compliance verdict.
                            </p>
                        </div>
                    </Card>

                    <Card padding="compact">
                        <div className="space-y-3">
                            <div>
                                <p className="font-mono uppercase text-label text-re-text-muted">
                                    Records Analyzed
                                </p>
                                <p className="mt-1 text-title tabular-nums text-re-text-primary">
                                    {result.totalRecords}
                                </p>
                            </div>
                            <div>
                                <p className="font-mono uppercase text-label text-re-text-muted">
                                    Findings Identified
                                </p>
                                <p className="mt-1 text-title tabular-nums text-re-text-primary">
                                    {result.findings.length}
                                </p>
                            </div>
                        </div>
                    </Card>
                </div>

                <Card variant="inset" padding="spacious" className="mb-8">
                    <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
                        {[
                            { label: 'CTE', score: result.scores.cteCompleteness },
                            { label: 'KDE', score: result.scores.kdeCompleteness },
                            { label: 'Chain', score: result.scores.chainIntegrity },
                            { label: 'Timeline', score: result.scores.timelineCoverage },
                            { label: 'Quality', score: result.scores.dataQuality },
                        ].map((item) => (
                            <div key={item.label} className="text-center">
                                <p className="mb-2 font-mono uppercase text-label text-re-text-muted">
                                    {item.label}
                                </p>
                                <div className="mb-1 h-2 rounded-full bg-re-surface-card" />
                                <p className="text-ui font-medium tabular-nums text-re-text-secondary">
                                    {item.score.toFixed(0)}%
                                </p>
                            </div>
                        ))}
                    </div>
                </Card>

                <div className="text-center">
                    <p className="mb-4 text-ui text-re-text-secondary">
                        Ready to see full analysis and recommendations?
                    </p>
                    <Button size="lg" trailingIcon={<ArrowRight size={18} strokeWidth={1.75} aria-hidden="true" />}>
                        Unlock Full Results
                    </Button>
                </div>
            </motion.div>
        );

        const fullResults: React.ReactNode = (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="w-full space-y-8"
            >
                {/* Score Overview */}
                <Card>
                    <CardHeader>
                        <CardTitle>Score Overview</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
                            <div className="flex flex-col items-center justify-center">
                                <ScoreCircle score={result.scores.overallScore} />
                                <Badge tone="info" className="mt-3">{gapSummary}</Badge>
                                <p className="mt-2 text-center text-small text-re-text-tertiary">
                                    Self-check on synthetic drill data. Not a compliance verdict.
                                </p>
                            </div>
                            <div className="space-y-4">
                                {[
                                    { label: 'Critical Tracking Event (CTE) Coverage', score: result.scores.cteCompleteness },
                                    { label: 'Key Data Element (KDE) Completeness', score: result.scores.kdeCompleteness },
                                    { label: 'Chain of Custody', score: result.scores.chainIntegrity },
                                    { label: 'Timeline Integrity', score: result.scores.timelineCoverage },
                                    { label: 'Data Quality', score: result.scores.dataQuality },
                                ].map((item) => (
                                    <div key={item.label}>
                                        <div className="mb-2 flex justify-between gap-3">
                                            <span className="text-ui font-medium text-re-text-primary">
                                                {item.label}
                                            </span>
                                            <span className="text-ui font-medium tabular-nums text-re-text-secondary">
                                                {item.score.toFixed(1)}%
                                            </span>
                                        </div>
                                        <div className="h-2 overflow-hidden rounded-full bg-re-surface-inset">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${item.score}%` }}
                                                transition={{ duration: 0.8, ease: 'easeOut' }}
                                                className="h-full rounded-full bg-re-text-tertiary"
                                            />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <Callout tone="info" icon={Clock} role="note" className="mt-6" title={`Response Time: ${responseTime} seconds`}>
                            Time from drill start to upload
                        </Callout>
                    </CardContent>
                </Card>

                {/* Findings */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <AlertTriangle size={20} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" />
                            Findings ({result.findings.length})
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {(['critical', 'major', 'minor'] as const).map((severity) => {
                                const findings = result.findings.filter(
                                    (f) => f.severity === severity
                                );
                                if (findings.length === 0) return null;

                                return (
                                    <div key={severity}>
                                        <h4 className="mb-2 font-mono uppercase text-label text-re-text-muted">
                                            {severity} ({findings.length})
                                        </h4>
                                        <div className="ml-4 space-y-2">
                                            {findings.map((finding, idx) => (
                                                <div
                                                    key={idx}
                                                    className={cn(
                                                        'rounded-md border border-l-[3px] border-re-border bg-re-surface-card p-3',
                                                        getSeverityColor(severity)
                                                    )}
                                                >
                                                    <button
                                                        type="button"
                                                        aria-expanded={expandedFinding === idx}
                                                        className="flex w-full items-center justify-between gap-3 rounded-sm text-left text-ui font-medium text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
                                                        onClick={() =>
                                                            setExpandedFinding(
                                                                expandedFinding === idx
                                                                    ? null
                                                                    : idx
                                                            )
                                                        }
                                                    >
                                                        <span>{finding.message}</span>
                                                        <ChevronDown
                                                            size={16}
                                                            strokeWidth={1.75}
                                                            aria-hidden="true"
                                                            className={cn(
                                                                'shrink-0 transition-transform duration-120 motion-reduce:transition-none',
                                                                expandedFinding === idx && 'rotate-180'
                                                            )}
                                                        />
                                                    </button>
                                                    {expandedFinding === idx && (
                                                        <div className="mt-2 space-y-1 border-t border-re-border-subtle pt-2 text-small text-re-text-secondary">
                                                            <p>
                                                                <span className="font-medium text-re-text-primary">
                                                                    Citation:
                                                                </span>{' '}
                                                                {finding.citation}
                                                            </p>
                                                            <p>
                                                                <span className="font-medium text-re-text-primary">
                                                                    Affected:
                                                                </span>{' '}
                                                                {finding.affectedRows.length} records
                                                            </p>
                                                            <p>
                                                                <span className="font-medium text-re-text-primary">
                                                                    Recommendation:
                                                                </span>{' '}
                                                                {finding.recommendation}
                                                            </p>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </CardContent>
                </Card>

                {/* Gaps */}
                {result.gaps.length > 0 && (
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Network size={20} strokeWidth={1.75} aria-hidden="true" className="text-re-text-tertiary" />
                                Traceability Gaps ({result.gaps.length})
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                {result.gaps.map((gap, idx) => (
                                    <div
                                        key={idx}
                                        className="rounded-lg border border-re-border p-4"
                                    >
                                        <div className="mb-2 flex items-start justify-between gap-3">
                                            <h4 className="text-subheading text-re-text-primary">
                                                {gap.gapType}
                                            </h4>
                                            <Badge tone={getSeverityBadgeColor(gap.severity) as BadgeTone} size="sm">
                                                {gap.severity}
                                            </Badge>
                                        </div>
                                        <p className="mb-3 text-ui text-re-text-secondary">
                                            {gap.description}
                                        </p>
                                        <div className="space-y-2 text-small">
                                            <div>
                                                <p className="font-mono uppercase text-label text-re-text-muted">
                                                    Details
                                                </p>
                                                <p className="mt-0.5 font-medium text-re-text-primary">
                                                    {gap.details}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="font-mono uppercase text-label text-re-text-muted">
                                                    Citation
                                                </p>
                                                <p className="mt-0.5 font-mono text-[0.8125rem] font-medium text-re-text-primary">
                                                    {gap.citation}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Action Buttons */}
                <div className="flex flex-col gap-4 sm:flex-row">
                    <Button
                        size="lg"
                        className="flex-1"
                        onClick={handleDownloadReport}
                        leadingIcon={<Download size={18} strokeWidth={1.75} aria-hidden="true" />}
                    >
                        Download Full Report
                    </Button>
                    <Button
                        size="lg"
                        variant="secondary"
                        onClick={handleReset}
                        leadingIcon={<RotateCcw size={18} strokeWidth={1.75} aria-hidden="true" />}
                    >
                        Run Another Drill
                    </Button>
                </div>

                <Card variant="inset" padding="spacious">
                    <div className="flex items-start gap-4">
                        <TrendingUp
                            size={20}
                            strokeWidth={1.75}
                            aria-hidden="true"
                            className="mt-0.5 shrink-0 text-re-text-tertiary"
                        />
                        <div>
                            <h4 className="mb-2 text-subheading text-re-text-primary">
                                Ready to automate this?
                            </h4>
                            <p className="mb-4 text-ui text-re-text-secondary">
                                Continuous compliance monitoring and automated remediation recommendations.
                            </p>
                            <Button
                                variant="secondary"
                                size="sm"
                                trailingIcon={<ArrowRight size={14} strokeWidth={1.75} aria-hidden="true" />}
                            >
                                See Pricing
                            </Button>
                        </div>
                    </div>
                </Card>
            </motion.div>
        );

        return (
            <LeadGate
                source="drill-simulator"
                headline="Get Your Drill Findings"
                subheadline="Unlock detailed findings, gap analysis, and a downloadable self-check report."
                ctaText="Unlock Findings"
                toolContext={{ toolInputs: { score: result.scores.overallScore, grade: result.scores.grade, scenario: state.selectedScenario } }}
                teaser={teaser}
                onUnlock={() => {}}
            >
                {fullResults}
            </LeadGate>
        );
    };

    return (
        <FreeToolPageShell
            title="24 Hour Drill Simulator"
            subtitle="Self-paced rehearsal for your §1.1455(c) records-on-request workflow"
            relatedToolIds={['ftl-checker', 'cte-mapper', 'kde-checker']}
        >
            <div className="py-2">
                <AnimatePresence mode="wait">{renderPhase()}</AnimatePresence>
            </div>
        </FreeToolPageShell>
    );
}

function ScoreCircle({ score }: { score: number }): React.ReactNode {
    const radius = 60;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - score / 100);

    return (
        <svg width={160} height={160} aria-hidden="true">
            <g transform="rotate(-90 80 80)">
                <circle
                    cx={80}
                    cy={80}
                    r={radius}
                    fill="none"
                    stroke="var(--re-border-default)"
                    strokeWidth={8}
                />
                <motion.circle
                    cx={80}
                    cy={80}
                    r={radius}
                    fill="none"
                    stroke="currentColor"
                    className={getScoreColor(score)}
                    strokeWidth={8}
                    strokeDasharray={circumference}
                    initial={{ strokeDashoffset: circumference }}
                    animate={{ strokeDashoffset: offset }}
                    transition={{ duration: 1, ease: 'easeOut' }}
                    strokeLinecap="round"
                />
            </g>
            <text
                x={80}
                y={92}
                textAnchor="middle"
                fontSize={32}
                fontWeight="600"
                fill="var(--re-text-primary)"
            >
                {Math.round(score)}
            </text>
        </svg>
    );
}
