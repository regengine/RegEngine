'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { EmailGate } from '@/components/tools/EmailGate';
import {
    ArrowLeft,
    ArrowRight,
    Camera,
    Check,
    ChevronDown,
    ClipboardList,
    Loader2,
    Package,
    Scan,
    ScanLine,
    ShieldCheck,
    Sparkles,
    Upload,
    X,
    Zap,
} from 'lucide-react';
import { getServiceURL } from '@/lib/api-config';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { useAuth } from '@/lib/auth-context';

/* ────────────────────────────────────────────────────────────── */
/*  Types                                                        */
/* ────────────────────────────────────────────────────────────── */interface ExtractedKDE {
    field: string;
    value: string | null;
    confidence: number;
}

interface LabelResult {
    product_name: string | null;
    brand: string | null;
    gtin: string | null;
    lot_code: string | null;
    serial_number: string | null;
    expiry_date: string | null;
    pack_date: string | null;
    net_weight: string | null;
    unit_of_measure: string | null;
    facility_name: string | null;
    facility_address: string | null;
    country_of_origin: string | null;
    ingredients: string | null;
    allergens: string[];
    certifications: string[];
    fsma_kdes: ExtractedKDE[];
    fsma_compatible: boolean;
    raw_text: string | null;
    analysis_engine: string;
}

/* ────────────────────────────────────────────────────────────── */
/*  Constants                                                    */
/* ────────────────────────────────────────────────────────────── */const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';

const DEMO_FIELDS: { key: keyof LabelResult; label: string; icon: typeof Package }[] = [
    { key: 'product_name', label: 'Product Name', icon: Package },
    { key: 'brand', label: 'Brand', icon: ScanLine },
    { key: 'gtin', label: 'GTIN', icon: ScanLine },
    { key: 'lot_code', label: 'Lot / Batch Code', icon: ClipboardList },
    { key: 'expiry_date', label: 'Expiry Date', icon: ClipboardList },
    { key: 'pack_date', label: 'Pack Date', icon: ClipboardList },
    { key: 'net_weight', label: 'Net Weight', icon: Package },
    { key: 'facility_name', label: 'Facility', icon: ShieldCheck },
    { key: 'country_of_origin', label: 'Country of Origin', icon: ShieldCheck },
];

/* ────────────────────────────────────────────────────────────── */
/*  Page component                                               */
/* ────────────────────────────────────────────────────────────── */
export default function LabelScannerPage() {
    const [image, setImage] = useState<string | null>(null);
    const [imageFile, setImageFile] = useState<File | null>(null);
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState<LabelResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showRawText, setShowRawText] = useState(false);
    const [editedFields, setEditedFields] = useState<Record<string, string>>({});
    const [ingesting, setIngesting] = useState(false);
    const [ingested, setIngested] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const cameraInputRef = useRef<HTMLInputElement>(null);
    const { apiKey, tenantId } = useAuth();
    const handleFile = useCallback((file: File) => {
        if (!file.type.startsWith('image/')) {
            setError('Please upload an image file (JPEG, PNG, etc.)');
            return;
        }
        if (file.size > 10 * 1024 * 1024) {
            setError('Image must be under 10 MB');
            return;
        }
        setError(null);
        setResult(null);
        setImageFile(file);
        const reader = new FileReader();
        reader.onload = (e) => setImage(e.target?.result as string);
        reader.readAsDataURL(file);
    }, []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
        },
        [handleFile],
    );

    const analyze = useCallback(async () => {
        if (!imageFile) return;
        setAnalyzing(true);
        setError(null);
        setResult(null);
        try {
            const formData = new FormData();
            formData.append('file', imageFile);

            const res = await fetchWithCsrf('/api/ingestion/api/v1/vision/analyze-label', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const body = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(body.detail || `Analysis failed (${res.status})`);
            }

            const data: LabelResult = await res.json();
            setResult(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Analysis failed');
        } finally {
            setAnalyzing(false);
        }
    }, [imageFile]);

    const reset = useCallback(() => {
        setImage(null);
        setImageFile(null);
        setResult(null);
        setError(null);
        setShowRawText(false);
        setEditedFields({});
        setIngested(false);
    }, []);

    /** Get the current value of a field — edited version takes priority */
    const getFieldValue = useCallback((key: string): string => {
        if (editedFields[key] !== undefined) return editedFields[key];
        if (!result) return '';
        const val = result[key as keyof LabelResult];
        if (typeof val === 'string') return val;
        if (val === null || val === undefined) return '';
        return String(val);
    }, [editedFields, result]);

    const updateField = useCallback((key: string, value: string) => {
        setEditedFields((prev) => ({ ...prev, [key]: value }));
        setIngested(false);
    }, []);

    /** Push corrected data into the trace pipeline */
    const confirmAndIngest = useCallback(async () => {
        if (!result) return;
        setIngesting(true);
        setError(null);
        try {
            const lotCode = getFieldValue('lot_code') || getFieldValue('gtin') || `LABEL-${Date.now()}`;
            const payload = {
                source: 'label_scanner_free_tool',
                tenant_id: tenantId || undefined,
                events: [{
                    cte_type: 'receiving',
                    traceability_lot_code: lotCode,
                    product_description: getFieldValue('product_name') || 'Label scan',
                    quantity: 1,
                    unit_of_measure: 'cases',
                    timestamp: new Date().toISOString(),
                    location_name: 'Label Scanner Tool',
                    kdes: {
                        gtin: getFieldValue('gtin') || undefined,
                        lot_code: getFieldValue('lot_code') || undefined,
                        serial_number: getFieldValue('serial_number') || undefined,
                        expiry_date: getFieldValue('expiry_date') || undefined,
                        pack_date: getFieldValue('pack_date') || undefined,
                        net_weight: getFieldValue('net_weight') || undefined,
                        facility_name: getFieldValue('facility_name') || undefined,
                        country_of_origin: getFieldValue('country_of_origin') || undefined,
                        brand: getFieldValue('brand') || undefined,
                    },
                }],
            };
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (apiKey) headers['X-RegEngine-API-Key'] = apiKey;
            if (tenantId) headers['X-Tenant-ID'] = tenantId;

            const res = await fetchWithCsrf(`${getServiceURL('ingestion')}/api/v1/webhooks/ingest`, {
                method: 'POST',
                headers,
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(body.detail || `Ingest failed (${res.status})`);
            }
            setIngested(true);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Ingest failed — are you logged in?');
        } finally {
            setIngesting(false);
        }
    }, [result, getFieldValue, apiKey, tenantId]);

    // Auto-analyze when image is loaded
    useEffect(() => {
        if (imageFile && !result && !analyzing) {
            analyze();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [imageFile]);
    return (
        <EmailGate toolName="label-scanner">
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <section className="relative z-[2] max-w-[860px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-8">
                <Link
                    href="/tools"
                    className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors mb-6"
                >
                    <ArrowLeft className="h-3.5 w-3.5" />
                    All Tools
                </Link>
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 rounded-xl bg-[var(--re-brand)]/10 flex items-center justify-center">
                        <ScanLine className="h-6 w-6 text-[var(--re-brand)]" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold text-[var(--re-text-primary)]">Label Scanner</h1>
                        <p className="text-sm text-[var(--re-text-muted)]">NLP-based food label extraction</p>
                    </div>
                </div>
                <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[640px]">
                    Upload or photograph a food product label. Computer vision extracts product name, lot code, GTIN, expiry date,
                    allergens, and maps everything to FSMA 204 Key Data Elements automatically.
                </p>
            </section>

            <section className="relative z-[2] max-w-[980px] mx-auto px-4 sm:px-6 pb-16">
                <div className="grid gap-6 md:grid-cols-2">
                    {/* Left: Upload area */}
                    <div className={`${card} p-6`}>                        {!image ? (
                            <div
                                onDrop={handleDrop}
                                onDragOver={(e) => e.preventDefault()}
                                className="flex flex-col items-center justify-center gap-4 p-10 rounded-xl border-2 border-dashed border-[var(--re-surface-border)] hover:border-[var(--re-brand)]/40 transition-colors cursor-pointer min-h-[320px]"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <div className="w-16 h-16 rounded-2xl bg-[var(--re-brand)]/10 flex items-center justify-center">
                                    <Upload className="h-8 w-8 text-[var(--re-brand)]" />
                                </div>
                                <div className="text-center">
                                    <p className="text-sm font-medium text-[var(--re-text-primary)]">
                                        Drop an image here or click to upload
                                    </p>
                                    <p className="text-xs text-[var(--re-text-muted)] mt-1">
                                        JPEG, PNG, WebP — max 10 MB
                                    </p>
                                </div>
                                <div className="flex gap-2 mt-2">
                                    <button
                                        onClick={(e) => { e.stopPropagation(); cameraInputRef.current?.click(); }}
                                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--re-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
                                    >
                                        <Camera className="h-4 w-4" />
                                        Take Photo
                                    </button>
                                    <button
                                        onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--re-surface-border)] text-sm font-medium text-[var(--re-text-muted)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-colors"
                                    >
                                        <Upload className="h-4 w-4" />
                                        Upload File
                                    </button>
                                </div>
                            </div>
                        ) : (                            <div className="space-y-4">
                                <div className="relative rounded-xl overflow-hidden border border-[var(--re-surface-border)]">
                                    <img src={image} alt="Uploaded label" className="w-full max-h-[400px] object-contain bg-black/5" />
                                    <button
                                        onClick={reset}
                                        className="absolute top-2 right-2 w-8 h-8 rounded-full bg-black/60 hover:bg-black/80 flex items-center justify-center text-white transition-colors"
                                    >
                                        <X className="h-4 w-4" />
                                    </button>
                                </div>
                                {analyzing && (
                                    <div className="flex items-center justify-center gap-2 py-4 text-sm text-[var(--re-brand)]">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        <span>Analyzing label with computer vision...</span>
                                    </div>
                                )}
                                {!analyzing && result && (
                                    <button
                                        onClick={analyze}
                                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--re-surface-border)] text-sm font-medium text-[var(--re-text-muted)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-colors"
                                    >
                                        <Sparkles className="h-4 w-4" />
                                        Re-analyze
                                    </button>
                                )}
                            </div>
                        )}
                        {error && (
                            <div className="mt-4 p-3 rounded-lg bg-re-danger-muted0/10 border border-re-danger/20 text-sm text-re-danger">
                                {error}
                            </div>
                        )}
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                        />
                        <input
                            ref={cameraInputRef}
                            type="file"
                            accept="image/*"
                            capture="environment"
                            className="hidden"
                            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                        />
                    </div>

                    {/* Right: Results */}
                    <div className={`${card} p-6`}>                        {!result && !analyzing && (
                            <div className="flex flex-col items-center justify-center min-h-[320px] text-center gap-3">
                                <Scan className="h-10 w-10 text-[var(--re-text-disabled)]" />
                                <p className="text-sm text-[var(--re-text-muted)]">
                                    Upload a food label to see extracted data
                                </p>
                            </div>
                        )}

                        {analyzing && (
                            <div className="flex flex-col items-center justify-center min-h-[320px] gap-3">
                                <Loader2 className="h-8 w-8 text-[var(--re-brand)] animate-spin" />
                                <p className="text-sm text-[var(--re-text-muted)]">Extracting traceability data...</p>
                            </div>
                        )}

                        {result && (
                            <LeadGate
                                source="label-scanner"
                                headline="See Your Full Label Analysis"
                                subheadline="Unlock allergen list, ingredient extraction, FSMA 204 KDE mapping with confidence scores, and raw OCR text."
                                ctaText="Unlock Full Analysis"
                                toolContext={{ toolInputs: { product_name: result.product_name, fsma_compatible: result.fsma_compatible, kdes_found: result.fsma_kdes.length } }}
                                teaser={
                                    <div className="space-y-3 pb-6">
                                        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${result.fsma_compatible ? 'bg-re-brand-muted border border-re-brand/20' : 'bg-re-warning-muted0/10 border border-re-warning/20'}`}>
                                            {result.fsma_compatible ? <Check className="h-4 w-4 text-re-brand" /> : <Zap className="h-4 w-4 text-re-warning" />}
                                            <span className={`text-sm font-medium ${result.fsma_compatible ? 'text-re-brand' : 'text-re-warning'}`}>
                                                {result.fsma_compatible ? 'FSMA 204 Compatible' : 'Partial KDE Coverage'}
                                            </span>
                                        </div>                                        {result.product_name && (
                                            <div className="flex items-start justify-between gap-3 py-1.5">
                                                <span className="text-xs text-[var(--re-text-muted)] uppercase tracking-wider">Product</span>
                                                <span className="text-sm text-[var(--re-text-primary)] font-medium text-right">{result.product_name}</span>
                                            </div>
                                        )}
                                        <p className="text-xs text-[var(--re-text-disabled)] text-center">
                                            {result.fsma_kdes.length} KDEs extracted · {result.allergens.length} allergens detected
                                        </p>
                                    </div>
                                }
                            >
                                <div className="space-y-4">
                                    {/* FSMA badge */}
                                    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${result.fsma_compatible ? 'bg-re-brand-muted border border-re-brand/20' : 'bg-re-warning-muted0/10 border border-re-warning/20'}`}>
                                        {result.fsma_compatible ? (
                                            <Check className="h-4 w-4 text-re-brand" />
                                        ) : (
                                            <Zap className="h-4 w-4 text-re-warning" />
                                        )}
                                        <span className={`text-sm font-medium ${result.fsma_compatible ? 'text-re-brand' : 'text-re-warning'}`}>
                                            {result.fsma_compatible ? 'FSMA 204 Compatible' : 'Partial KDE Coverage'}
                                        </span>
                                    </div>

                                    {/* Editable extracted fields */}
                                    <div className="space-y-2">
                                        <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">Extracted Fields <span className="text-xs font-normal text-[var(--re-text-muted)]">— click to edit</span></h3>
                                        {DEMO_FIELDS.map(({ key, label }) => {
                                            const value = getFieldValue(key);
                                            if (!value && !editedFields[key]) return null;
                                            return (
                                                <div key={key} className="flex items-center gap-3 py-1 border-b border-[var(--re-surface-border)] last:border-0">
                                                    <span className="text-xs text-[var(--re-text-muted)] uppercase tracking-wider min-w-[100px]">{label}</span>
                                                    <input
                                                        type="text"
                                                        value={value}
                                                        onChange={(e) => updateField(key, e.target.value)}
                                                        className="flex-1 text-sm text-[var(--re-text-primary)] font-medium text-right bg-transparent border-none outline-none focus:ring-1 focus:ring-[var(--re-brand)] rounded px-1 py-0.5 transition-shadow"
                                                    />
                                                    {editedFields[key] !== undefined && (
                                                        <span className="text-[10px] text-[var(--re-brand)] font-bold">EDITED</span>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>

                                    {/* Confirm & Ingest */}
                                    <div className="pt-2">
                                        {ingested ? (
                                            <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-re-brand-muted border border-re-brand/20">
                                                <Check className="h-4 w-4 text-re-brand" />
                                                <span className="text-sm font-medium text-re-brand">Ingested into trace pipeline</span>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={confirmAndIngest}
                                                disabled={ingesting}
                                                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--re-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
                                            >
                                                {ingesting ? (
                                                    <><Loader2 className="h-4 w-4 animate-spin" /> Ingesting...</>
                                                ) : (
                                                    <><ArrowRight className="h-4 w-4" /> Confirm &amp; Ingest</>
                                                )}
                                            </button>
                                        )}
                                        {!apiKey && !ingested && (
                                            <p className="text-xs text-[var(--re-text-muted)] text-center mt-2">
                                                <Link href="/login" className="text-[var(--re-brand)] hover:underline">Log in</Link> to ingest into your workspace
                                            </p>
                                        )}
                                    </div>
                                    {/* Allergens */}
                                    {result.allergens.length > 0 && (
                                        <div>
                                            <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">Allergens</h3>
                                            <div className="flex flex-wrap gap-1.5">
                                                {result.allergens.map((a) => (
                                                    <span key={a} className="px-2 py-0.5 rounded-md bg-re-danger-muted0/10 border border-re-danger/20 text-xs text-re-danger font-medium">
                                                        {a}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Certifications */}
                                    {result.certifications.length > 0 && (
                                        <div>
                                            <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">Certifications</h3>
                                            <div className="flex flex-wrap gap-1.5">
                                                {result.certifications.map((c) => (
                                                    <span key={c} className="px-2 py-0.5 rounded-md bg-re-brand-muted border border-re-brand/20 text-xs text-re-brand font-medium">
                                                        {c}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Ingredients */}
                                    {result.ingredients && (
                                        <div>
                                            <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">Ingredients</h3>
                                            <p className="text-xs text-[var(--re-text-muted)] leading-relaxed">{result.ingredients}</p>
                                        </div>
                                    )}
                                    {/* FSMA KDEs */}
                                    {result.fsma_kdes.length > 0 && (
                                        <div>
                                            <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">FSMA 204 KDE Mapping</h3>
                                            <div className="space-y-1.5">
                                                {result.fsma_kdes.map((kde, i) => (
                                                    <div key={i} className="flex items-center gap-2 text-xs">
                                                        <span className="text-[var(--re-text-muted)] min-w-[120px]">{kde.field}</span>
                                                        <span className="text-[var(--re-text-primary)] font-mono flex-1 truncate">{kde.value || '—'}</span>
                                                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${kde.confidence >= 0.8 ? 'bg-re-brand-muted text-re-brand' : kde.confidence >= 0.5 ? 'bg-re-warning-muted0/10 text-re-warning' : 'bg-re-danger-muted0/10 text-re-danger'}`}>
                                                            {Math.round(kde.confidence * 100)}%
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Raw text toggle */}
                                    {result.raw_text && (
                                        <div>
                                            <button
                                                onClick={() => setShowRawText(!showRawText)}
                                                className="flex items-center gap-1.5 text-xs text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors"
                                            >
                                                <ChevronDown className={`h-3 w-3 transition-transform ${showRawText ? 'rotate-180' : ''}`} />
                                                {showRawText ? 'Hide' : 'Show'} raw text
                                            </button>
                                            {showRawText && (
                                                <pre className="mt-2 p-3 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[10px] text-[var(--re-text-muted)] overflow-x-auto whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                                                    {result.raw_text}
                                                </pre>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </LeadGate>
                        )}
                    </div>
                </div>

                {/* CTA */}
                <div className="mt-8 text-center">
                    <p className="text-sm text-[var(--re-text-muted)] mb-3">
                        Want this running on every receiving dock? Field Capture sends scans straight into your compliance pipeline.
                    </p>
                    <div className="flex flex-wrap gap-3 justify-center">
                        <Link href="/alpha">
                            <span className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-[var(--re-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity">
                                Become a Design Partner <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                        <Link href="/tools">
                            <span className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl border border-[var(--re-surface-border)] text-sm font-medium text-[var(--re-text-muted)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-colors">
                                All Free Tools
                            </span>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
        </EmailGate>
    );
}