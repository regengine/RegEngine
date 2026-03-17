'use client';
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    ShieldAlert, Play, CheckCircle2, XCircle, AlertTriangle, FileText,
    ArrowRight, Clock, Loader2, Network, Upload, Download, BarChart3,
    FileWarning, ChevronDown, ChevronRight, Timer, Shield, Zap,
    TrendingUp, AlertCircle, FileCheck, RotateCcw,
} from 'lucide-react';
import {
    parseCSV, validateRecords, generateSampleCSV, getScoreColor,
    type ValidationResult, type ValidationFinding, type TraceabilityGap,
} from '../lib/record-validator';

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
    { name: 'Calculating compliance score...', duration: 500 },
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
    const [expandedFinding, setExpandedFinding] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

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

    const handleScenarioSelect = (scenarioId: string) => {
        setState({
            ...state,
            selectedScenario: scenarioId,
            phase: 'upload',
            drillStartTime: Date.now(),
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

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        const files = e.dataTransfer.files;
        if (files && files[0]) {
            processFile(files[0]);
        }
    }, []);

    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            processFile(e.target.files[0]);
        }
    };

    const processFile = (file: File) => {
        const validExtensions = ['.csv', '.tsv', '.xlsx'];
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();

        if (!validExtensions.includes(ext) || file.size > 10 * 1024 * 1024) {
            alert('Please upload a CSV, TSV, or XLSX file under 10MB');
            return;
        }

        setState({
            ...state,
            uploadedFile: file,
        });
    };

    const handleAnalyze = async () => {
        if (!state.uploadedFile) return;

        setState({ ...state, phase: 'analyzing' });
        setCurrentStage(0);

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

        const report = `FDA RECALL DRILL SIMULATOR - FULL REPORT
Generated: ${new Date().toISOString()}

SCENARIO: ${scenarioName}
RECORDS ANALYZED: ${result.totalRecords}
OVERALL SCORE: ${result.scores.overallScore.toFixed(1)}/100 (${result.scores.grade})

COMPLIANCE BREAKDOWN:
- Complete Traceability Events (CTE): ${result.scores.cteCompleteness.toFixed(1)}/100
- Key Data Elements (KDE): ${result.scores.kdeCompleteness.toFixed(1)}/100
- Chain of Custody: ${result.scores.chainIntegrity.toFixed(1)}/100
- Timeline Integrity: ${result.scores.timelineCoverage.toFixed(1)}/100
- Data Quality: ${result.scores.dataQuality.toFixed(1)}/100

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

PASS/FAIL: ${result.scores.overallScore >= 70 ? 'PASSED' : 'FAILED'}
STATUS: ${
            result.scores.overallScore >= 70
                ? 'Your traceability records meet FSMA 204 requirements'
                : 'Critical gaps detected. Recommend immediate remediation.'
        }

---
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

    const renderPhase = () => {
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

    const renderScenario = () => (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-4xl mx-auto"
        >
            <div className="text-center mb-12">
                <h1 className="text-4xl font-bold mb-3" style={{ color: 'var(--re-text-primary)' }}>
                    Can Your Records Survive an FDA Investigation?
                </h1>
                <p className="text-lg" style={{ color: 'var(--re-text-secondary)' }}>
                    Upload your actual traceability records. We'll validate them against FSMA 204
                    requirements in real-time — no data leaves your browser.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                {scenarios.map((scenario) => (
                    <motion.div
                        key={scenario.id}
                        whileHover={{ y: -4 }}
                        onClick={() => handleScenarioSelect(scenario.id)}
                    >
                        <Card
                            className="cursor-pointer transition-all hover:shadow-lg"
                            style={{ borderColor: 'var(--re-border-default)' }}
                        >
                            <CardContent className="pt-6">
                                <div className="flex items-start justify-between mb-3">
                                    <h3
                                        className="font-semibold text-lg"
                                        style={{ color: 'var(--re-text-primary)' }}
                                    >
                                        {scenario.title}
                                    </h3>
                                    <Badge variant="outline">{scenario.complexity}</Badge>
                                </div>
                                <p
                                    className="text-sm mb-4"
                                    style={{ color: 'var(--re-text-secondary)' }}
                                >
                                    {scenario.description}
                                </p>
                                <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--re-text-muted)' }}>
                                    <FileText size={14} />
                                    {scenario.recordCount} records
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                ))}
            </div>

            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                <Button size="lg" className="bg-blue-600 hover:bg-blue-700 text-white">
                    <Play size={18} className="mr-2" />
                    Start Drill — Upload Your Records
                </Button>
                <Button
                    size="lg"
                    variant="outline"
                    onClick={handleDownloadSample}
                    style={{ borderColor: 'var(--re-border-default)' }}
                >
                    <Download size={18} className="mr-2" />
                    Download Sample CSV
                </Button>
            </div>

            <div className="flex items-center justify-center gap-2 text-sm" style={{ color: 'var(--re-text-muted)' }}>
                <Shield size={16} />
                🔒 100% client-side • Your data never leaves your browser
            </div>
        </motion.div>
    );

    const renderUpload = () => (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-2xl mx-auto"
        >
            <div className="mb-8 flex items-center justify-between">
                <h2 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>
                    Upload Your Records
                </h2>
                <div className="flex items-center gap-2 text-lg font-mono" style={{ color: 'var(--re-brand)' }}>
                    <Timer size={20} />
                    {formatTime(timeRemaining)}
                </div>
            </div>

            <Card className="mb-6" style={{ borderColor: 'var(--re-border-default)' }}>
                <CardContent className="pt-6">
                    <h3 className="font-semibold mb-2" style={{ color: 'var(--re-text-primary)' }}>
                        Scenario: {scenarios.find((s) => s.id === state.selectedScenario)?.title}
                    </h3>
                    <p className="text-sm" style={{ color: 'var(--re-text-secondary)' }}>
                        {scenarios.find((s) => s.id === state.selectedScenario)?.description}
                    </p>
                </CardContent>
            </Card>

            <div
                className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-all ${
                    dragActive
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-300 hover:border-gray-400'
                }`}
                style={{
                    borderColor: dragActive ? 'var(--re-brand)' : 'var(--re-border-default)',
                    backgroundColor: dragActive ? 'rgba(59, 130, 246, 0.05)' : 'transparent',
                }}
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
                    onChange={handleFileInput}
                    className="hidden"
                />
                <Upload
                    size={48}
                    className="mx-auto mb-4"
                    style={{ color: 'var(--re-brand)' }}
                />
                <h3
                    className="text-lg font-semibold mb-2"
                    style={{ color: 'var(--re-text-primary)' }}
                >
                    {state.uploadedFile ? state.uploadedFile.name : 'Drop your file here'}
                </h3>
                <p style={{ color: 'var(--re-text-secondary)' }}>
                    {state.uploadedFile
                        ? `${(state.uploadedFile.size / 1024).toFixed(0)} KB`
                        : 'or click to browse'}
                </p>
                <p className="text-xs mt-2" style={{ color: 'var(--re-text-muted)' }}>
                    CSV, TSV, or XLSX • Max 10MB
                </p>
            </div>

            <div className="mt-6 mb-6">
                <button className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--re-brand)' }}>
                    <ChevronRight size={16} />
                    What should my file contain?
                </button>
                <div className="mt-3 p-4 bg-gray-50 rounded-lg text-sm" style={{ borderLeft: '4px solid var(--re-brand)' }}>
                    <p className="font-mono text-xs mb-2" style={{ color: 'var(--re-text-muted)' }}>
                        Required columns:
                    </p>
                    <ul className="space-y-1 text-xs" style={{ color: 'var(--re-text-secondary)' }}>
                        <li>• event_type (ship, receive, transform)</li>
                        <li>• event_date, event_time</li>
                        <li>• lot_code, product_name</li>
                        <li>• quantity, unit</li>
                        <li>• from_party, to_party</li>
                        <li>• location</li>
                    </ul>
                </div>
            </div>

            <div className="flex gap-4">
                <Button
                    size="lg"
                    onClick={handleAnalyze}
                    disabled={!state.uploadedFile}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                >
                    <Zap size={18} className="mr-2" />
                    Analyze My Records
                </Button>
                <Button
                    size="lg"
                    variant="outline"
                    onClick={handleLoadSampleData}
                    style={{ borderColor: 'var(--re-border-default)' }}
                >
                    Load Sample Data
                </Button>
            </div>
        </motion.div>
    );

    const renderAnalyzing = () => (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-2xl mx-auto"
        >
            <div className="text-center mb-12">
                <h2 className="text-2xl font-bold mb-8" style={{ color: 'var(--re-text-primary)' }}>
                    Analyzing Your Records
                </h2>

                <div className="space-y-4">
                    {analysisStages.map((stage, idx) => (
                        <div key={idx} className="flex items-center gap-4">
                            <div className="w-8 h-8 flex items-center justify-center">
                                {idx < currentStage ? (
                                    <CheckCircle2
                                        size={24}
                                        style={{ color: 'var(--re-brand)' }}
                                    />
                                ) : idx === currentStage ? (
                                    <Loader2
                                        size={24}
                                        style={{ color: 'var(--re-brand)' }}
                                        className="animate-spin"
                                    />
                                ) : (
                                    <div
                                        className="w-6 h-6 rounded-full border-2"
                                        style={{ borderColor: 'var(--re-border-default)' }}
                                    />
                                )}
                            </div>
                            <span
                                className={`text-lg font-medium ${
                                    idx < currentStage
                                        ? ''
                                        : idx === currentStage
                                          ? 'font-bold'
                                          : ''
                                }`}
                                style={{
                                    color:
                                        idx < currentStage
                                            ? 'var(--re-text-secondary)'
                                            : 'var(--re-text-primary)',
                                }}
                            >
                                {stage.name}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </motion.div>
    );

    const renderResults = () => {
        if (!state.validationResult) return null;

        const result = state.validationResult;
        const responseTime = state.uploadTime
            ? Math.round((state.uploadTime - (state.drillStartTime || 0)) / 1000)
            : 0;

        const teaser = (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="w-full max-w-4xl mx-auto"
            >
                <h2 className="text-2xl font-bold text-center mb-8" style={{ color: 'var(--re-text-primary)' }}>
                    Compliance Assessment
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    <Card style={{ borderColor: 'var(--re-border-default)' }}>
                        <CardContent className="pt-6 text-center">
                            <div className="flex justify-center mb-4">
                                <ScoreCircle score={result.scores.overallScore} />
                            </div>
                            <p className="text-4xl font-bold mb-2" style={{ color: 'var(--re-brand)' }}>
                                {result.scores.grade}
                            </p>
                            <Badge
                                className={`text-white ${
                                    result.scores.overallScore >= 70 ? 'bg-green-600' : 'bg-red-600'
                                }`}
                            >
                                {result.scores.overallScore >= 70 ? 'PASSED' : 'FAILED'}
                            </Badge>
                        </CardContent>
                    </Card>

                    <Card style={{ borderColor: 'var(--re-border-default)' }}>
                        <CardContent className="pt-6">
                            <div className="space-y-3">
                                <div>
                                    <p className="text-sm font-medium" style={{ color: 'var(--re-text-secondary)' }}>
                                        Records Analyzed
                                    </p>
                                    <p className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>
                                        {result.totalRecords}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-sm font-medium" style={{ color: 'var(--re-text-secondary)' }}>
                                        Findings Identified
                                    </p>
                                    <p className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>
                                        {result.findings.length}
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                <div className="bg-gradient-to-r from-gray-100 to-gray-50 rounded-lg p-6 mb-8">
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        {[
                            { label: 'CTE', score: result.scores.cteCompleteness },
                            { label: 'KDE', score: result.scores.kdeCompleteness },
                            { label: 'Chain', score: result.scores.chainIntegrity },
                            { label: 'Timeline', score: result.scores.timelineCoverage },
                            { label: 'Quality', score: result.scores.dataQuality },
                        ].map((item) => (
                            <div key={item.label} className="text-center">
                                <p className="text-xs font-medium mb-2" style={{ color: 'var(--re-text-secondary)' }}>
                                    {item.label}
                                </p>
                                <div className="h-2 bg-gray-300 rounded-full mb-1 opacity-40" />
                                <p className="text-sm font-bold" style={{ color: getScoreColor(item.score) }}>
                                    {item.score.toFixed(0)}%
                                </p>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="text-center">
                    <p className="text-sm mb-4" style={{ color: 'var(--re-text-secondary)' }}>
                        Ready to see full analysis and recommendations?
                    </p>
                    <Button size="lg" className="bg-blue-600 hover:bg-blue-700 text-white">
                        Unlock Full Results <ArrowRight size={18} className="ml-2" />
                    </Button>
                </div>
            </motion.div>
        );

        const fullResults = (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="w-full max-w-4xl mx-auto space-y-8"
            >
                {/* Score Overview */}
                <Card style={{ borderColor: 'var(--re-border-default)' }}>
                    <CardHeader>
                        <CardTitle>Score Overview</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div className="flex flex-col items-center justify-center">
                                <ScoreCircle score={result.scores.overallScore} />
                                <p className="text-4xl font-bold mt-4" style={{ color: 'var(--re-brand)' }}>
                                    {result.scores.grade}
                                </p>
                                <Badge
                                    className={`mt-2 text-white ${
                                        result.scores.overallScore >= 70 ? 'bg-green-600' : 'bg-red-600'
                                    }`}
                                >
                                    {result.scores.overallScore >= 70 ? 'PASSED' : 'FAILED'}
                                </Badge>
                            </div>
                            <div className="space-y-4">
                                {[
                                    { label: 'Complete Traceability Events (CTE)', score: result.scores.cteCompleteness },
                                    { label: 'Key Data Elements (KDE)', score: result.scores.kdeCompleteness },
                                    { label: 'Chain of Custody', score: result.scores.chainIntegrity },
                                    { label: 'Timeline Integrity', score: result.scores.timelineCoverage },
                                    { label: 'Data Quality', score: result.scores.dataQuality },
                                ].map((item) => (
                                    <div key={item.label}>
                                        <div className="flex justify-between mb-2">
                                            <span
                                                className="text-sm font-medium"
                                                style={{ color: 'var(--re-text-primary)' }}
                                            >
                                                {item.label}
                                            </span>
                                            <span
                                                className="text-sm font-bold"
                                                style={{ color: getScoreColor(item.score) }}
                                            >
                                                {item.score.toFixed(1)}%
                                            </span>
                                        </div>
                                        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${item.score}%` }}
                                                transition={{ duration: 0.8, ease: 'easeOut' }}
                                                className="h-full rounded-full"
                                                style={{ backgroundColor: getScoreColor(item.score) }}
                                            />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="mt-6 p-4 bg-blue-50 rounded-lg flex items-start gap-3">
                            <Clock size={18} style={{ color: 'var(--re-brand)' }} />
                            <div>
                                <p className="text-sm font-medium" style={{ color: 'var(--re-text-primary)' }}>
                                    Response Time: {responseTime} seconds
                                </p>
                                <p className="text-xs" style={{ color: 'var(--re-text-secondary)' }}>
                                    Time from drill start to upload
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Findings */}
                <Card style={{ borderColor: 'var(--re-border-default)' }}>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <AlertTriangle size={20} style={{ color: 'var(--re-brand)' }} />
                            Findings ({result.findings.length})
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {['critical', 'major', 'minor'].map((severity) => {
                                const findings = result.findings.filter(
                                    (f) => f.severity === severity
                                );
                                if (findings.length === 0) return null;

                                return (
                                    <div key={severity}>
                                        <h4
                                            className="text-sm font-semibold mb-2 uppercase"
                                            style={{
                                                color:
                                                    severity === 'critical'
                                                        ? '#dc2626'
                                                        : severity === 'major'
                                                          ? '#ea580c'
                                                          : '#f59e0b',
                                            }}
                                        >
                                            {severity} ({findings.length})
                                        </h4>
                                        <div className="space-y-2 ml-4">
                                            {findings.map((finding, idx) => (
                                                <div
                                                    key={idx}
                                                    className="p-3 bg-gray-50 rounded border-l-4"
                                                    style={{
                                                        borderLeftColor:
                                                            severity === 'critical'
                                                                ? '#dc2626'
                                                                : severity === 'major'
                                                                  ? '#ea580c'
                                                                  : '#f59e0b',
                                                    }}
                                                >
                                                    <div
                                                        className="text-sm font-medium cursor-pointer flex justify-between items-center"
                                                        onClick={() =>
                                                            setExpandedFinding(
                                                                expandedFinding === idx
                                                                    ? null
                                                                    : String(idx)
                                                            )
                                                        }
                                                    >
                                                        <span>{finding.message}</span>
                                                        <ChevronDown
                                                            size={16}
                                                            className={`transition-transform ${
                                                                expandedFinding === String(idx)
                                                                    ? 'rotate-180'
                                                                    : ''
                                                            }`}
                                                        />
                                                    </div>
                                                    {expandedFinding === String(idx) && (
                                                        <div className="mt-2 pt-2 border-t space-y-1 text-xs">
                                                            <p>
                                                                <span
                                                                    className="font-semibold"
                                                                    style={{
                                                                        color: 'var(--re-text-secondary)',
                                                                    }}
                                                                >
                                                                    Citation:
                                                                </span>{' '}
                                                                {finding.citation}
                                                            </p>
                                                            <p>
                                                                <span
                                                                    className="font-semibold"
                                                                    style={{
                                                                        color: 'var(--re-text-secondary)',
                                                                    }}
                                                                >
                                                                    Affected:
                                                                </span>{' '}
                                                                {finding.affectedRows.length} records
                                                            </p>
                                                            <p>
                                                                <span
                                                                    className="font-semibold"
                                                                    style={{
                                                                        color: 'var(--re-text-secondary)',
                                                                    }}
                                                                >
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
                    <Card style={{ borderColor: 'var(--re-border-default)' }}>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Network size={20} style={{ color: 'var(--re-brand)' }} />
                                Traceability Gaps ({result.gaps.length})
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                {result.gaps.map((gap, idx) => (
                                    <div
                                        key={idx}
                                        className="p-4 border rounded-lg"
                                        style={{ borderColor: 'var(--re-border-default)' }}
                                    >
                                        <div className="flex items-start justify-between mb-2">
                                            <h4
                                                className="font-semibold"
                                                style={{ color: 'var(--re-text-primary)' }}
                                            >
                                                {gap.gapType}
                                            </h4>
                                            <Badge
                                                variant={
                                                    gap.severity === 'critical'
                                                        ? 'destructive'
                                                        : gap.severity === 'major'
                                                          ? 'secondary'
                                                          : 'outline'
                                                }
                                            >
                                                {gap.severity}
                                            </Badge>
                                        </div>
                                        <p
                                            className="text-sm mb-3"
                                            style={{ color: 'var(--re-text-secondary)' }}
                                        >
                                            {gap.description}
                                        </p>
                                        <div className="space-y-2 text-xs">
                                            <div>
                                                <p
                                                    style={{
                                                        color: 'var(--re-text-muted)',
                                                    }}
                                                >
                                                    Details
                                                </p>
                                                <p
                                                    className="font-semibold"
                                                    style={{
                                                        color: 'var(--re-text-primary)',
                                                    }}
                                                >
                                                    {gap.details}
                                                </p>
                                            </div>
                                            <div>
                                                <p
                                                    style={{
                                                        color: 'var(--re-text-muted)',
                                                    }}
                                                >
                                                    Citation
                                                </p>
                                                <p
                                                    className="font-mono font-semibold"
                                                    style={{
                                                        color: 'var(--re-text-primary)',
                                                    }}
                                                >
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
                <div className="flex flex-col sm:flex-row gap-4">
                    <Button
                        size="lg"
                        className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                        onClick={handleDownloadReport}
                    >
                        <Download size={18} className="mr-2" />
                        Download Full Report
                    </Button>
                    <Button
                        size="lg"
                        variant="outline"
                        onClick={handleReset}
                        style={{ borderColor: 'var(--re-border-default)' }}
                    >
                        <RotateCcw size={18} className="mr-2" />
                        Run Another Drill
                    </Button>
                </div>

                <Card
                    className="bg-gradient-to-r from-blue-50 to-indigo-50"
                    style={{ borderColor: 'var(--re-brand)' }}
                >
                    <CardContent className="pt-6">
                        <div className="flex items-start gap-4">
                            <TrendingUp
                                size={24}
                                style={{ color: 'var(--re-brand)' }}
                            />
                            <div>
                                <h4
                                    className="font-semibold mb-2"
                                    style={{ color: 'var(--re-text-primary)' }}
                                >
                                    Ready to automate this?
                                </h4>
                                <p
                                    className="text-sm mb-4"
                                    style={{ color: 'var(--re-text-secondary)' }}
                                >
                                    Continuous compliance monitoring and automated remediation recommendations.
                                </p>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    style={{
                                        borderColor: 'var(--re-brand)',
                                        color: 'var(--re-brand)',
                                    }}
                                >
                                    See Pricing <ArrowRight size={14} className="ml-2" />
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        );

        return (
            <LeadGate
                source="drill-simulator"
                headline="Get Your Full Compliance Report"
                subheadline="Unlock detailed findings, gap analysis, and a downloadable audit report."
                ctaText="Unlock Full Report"
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
            title="FDA Recall Drill Simulator"
            subtitle="Real-time compliance testing for FSMA 204 traceability records"
            relatedToolIds={['ftl-checker', 'cte-mapper', 'kde-checker']}
        >
            <div className="py-8">
                <AnimatePresence mode="wait">{renderPhase()}</AnimatePresence>
            </div>
        </FreeToolPageShell>
    );
}

function ScoreCircle({ score }: { score: number }) {
    const radius = 60;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - score / 100);

    const getScoreColorHex = (s: number): string => {
        if (s >= 80) return '#10b981'; // green-500
        if (s >= 70) return '#3b82f6'; // blue-500
        if (s >= 60) return '#f59e0b'; // amber-500
        if (s >= 50) return '#ef4444'; // red-500
        return '#dc2626'; // red-600
    };

    return (
        <svg width={160} height={160} className="transform -rotate-90">
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
                stroke={getScoreColorHex(score)}
                strokeWidth={8}
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset: offset }}
                transition={{ duration: 1, ease: 'easeOut' }}
                strokeLinecap="round"
            />
            <text
                x={80}
                y={92}
                textAnchor="middle"
                fontSize={32}
                fontWeight="bold"
                fill="var(--re-text-primary)"
            >
                {Math.round(score)}
            </text>
        </svg>
    );
}