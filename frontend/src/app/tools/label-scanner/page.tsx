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
    Package,
    Scan,
    ScanLine,
    ShieldCheck,
    Sparkles,
    Upload,
    X,
} from 'lucide-react';
import { getServiceURL } from '@/lib/api-config';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { useAuth } from '@/lib/auth-context';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { isExperimentalToolEnabled } from '@/lib/experimental-features';
import { Container } from '@/components/layout/container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/ui/status-badge';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
import { trackToolRunCompleted, trackToolRunStarted } from '@/lib/conversion-events';
import { usePostHog } from '@/lib/posthog-provider';

/* ────────────────────────────────────────────────────────────── */
/*  Types                                                        */
/* ────────────────────────────────────────────────────────────── */
interface ExtractedKDE {
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
/* ────────────────────────────────────────────────────────────── */
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
    if (!isExperimentalToolEnabled('label-scanner')) {
        return (
            <FeatureNotEnabled
                featureName="AI Label Scanner"
                backHref="/tools"
                backLabel="Back to free tools"
            />
        );
    }
    return <LabelScannerContent />;
}

function LabelScannerContent() {
    const posthog = usePostHog();
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
        trackToolRunStarted('label-scanner');
        posthog?.capture('tool_started', { tool_id: 'label-scanner' });
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
            trackToolRunCompleted('label-scanner', 'success');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Analysis failed');
            trackToolRunCompleted('label-scanner', 'error');
        } finally {
            setAnalyzing(false);
        }
    }, [imageFile, posthog]);

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
            setError(err instanceof Error ? err.message : 'Ingest failed. Are you logged in?');
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

    /** The one status mark for the extracted label — icon plus label, never colour alone. */
    const fsmaBadge = (compatibleLabel: string, partialLabel: string) => result && (
        <StatusBadge
            state={result.fsma_compatible ? 'compliant' : 'at-risk'}
            label={result.fsma_compatible ? compatibleLabel : partialLabel}
        />
    );

    return (
        <EmailGate toolName="label-scanner">
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            {/* Header */}
            <Container width="tool" as="section">
                <Link
                    href="/tools"
                    className="mb-6 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                >
                    <ArrowLeft aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={1.75} />
                    All Tools
                </Link>
                <div className="border-b border-re-border-subtle pb-5">
                    <p className="mb-2 text-label text-re-text-muted">Computer-vision food-label extraction</p>
                    <h1 className="text-title text-re-text-primary">Label Scanner</h1>
                    <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                        Upload or photograph a food product label. Computer vision attempts to extract product name, lot code, GTIN,
                        expiry date, and allergens, and suggests a mapping to FSMA 204 Key Data Element (KDE) fields. Always review extracted
                        values before ingesting. OCR mistakes are common, and a label is not itself a Critical Tracking Event (CTE) record.
                    </p>
                </div>
            </Container>

            <Container width="tool" as="section" className="pb-10 pt-6">
                <div className="grid gap-6 md:grid-cols-2">
                    {/* Left: Upload area */}
                    <Card>
                        <CardContent>
                            {!image ? (
                                <div
                                    onDrop={handleDrop}
                                    onDragOver={(e) => e.preventDefault()}
                                    className="flex min-h-[320px] cursor-pointer flex-col items-center justify-center gap-4 rounded-md border border-dashed border-re-border p-8 transition-colors duration-120 hover:border-re-border-strong motion-reduce:transition-none"
                                    onClick={() => fileInputRef.current?.click()}
                                >
                                    <Upload aria-hidden="true" className="h-6 w-6 text-re-text-muted" strokeWidth={1.75} />
                                    <div className="text-center">
                                        <p className="text-ui font-medium text-re-text-primary">
                                            Drop an image here or click to upload
                                        </p>
                                        <p className="mt-1 text-small text-re-text-tertiary">
                                            JPEG, PNG, WebP. Max 10 MB
                                        </p>
                                    </div>
                                    <div className="mt-2 flex flex-wrap justify-center gap-2">
                                        <Button
                                            type="button"
                                            size="lg"
                                            onClick={(e) => { e.stopPropagation(); cameraInputRef.current?.click(); }}
                                            leadingIcon={<Camera aria-hidden="true" strokeWidth={1.75} />}
                                        >
                                            Take Photo
                                        </Button>
                                        <Button
                                            type="button"
                                            variant="secondary"
                                            size="lg"
                                            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                                            leadingIcon={<Upload aria-hidden="true" strokeWidth={1.75} />}
                                        >
                                            Upload File
                                        </Button>
                                    </div>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="relative overflow-hidden rounded-md border border-re-border bg-re-surface-inset">
                                        <img src={image} alt="Uploaded label" className="max-h-[400px] w-full object-contain" />
                                        <Button
                                            type="button"
                                            variant="secondary"
                                            size="icon"
                                            aria-label="Remove uploaded label"
                                            onClick={reset}
                                            className="absolute right-2 top-2 rounded-full"
                                        >
                                            <X aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
                                        </Button>
                                    </div>
                                    {analyzing && (
                                        <p className="flex items-center justify-center gap-2 py-4 text-ui text-re-text-tertiary" role="status" aria-live="polite">
                                            <Spinner size="sm" />
                                            <span>Analyzing label with computer vision...</span>
                                        </p>
                                    )}
                                    {!analyzing && result && (
                                        <Button
                                            type="button"
                                            variant="secondary"
                                            onClick={analyze}
                                            leadingIcon={<Sparkles aria-hidden="true" strokeWidth={1.75} />}
                                        >
                                            Re-analyze
                                        </Button>
                                    )}
                                </div>
                            )}
                            {error && (
                                <Callout tone="danger" role="alert" className="mt-4">
                                    {error}
                                </Callout>
                            )}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*"
                                className="hidden"
                                aria-label="Upload a label image"
                                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                            />
                            <input
                                ref={cameraInputRef}
                                type="file"
                                accept="image/*"
                                capture="environment"
                                className="hidden"
                                aria-label="Photograph a label"
                                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                            />
                        </CardContent>
                    </Card>

                    {/* Right: Results */}
                    <Card>
                        <CardContent>
                            {!result && !analyzing && (
                                <EmptyState
                                    bare
                                    icon={Scan}
                                    title="Upload a food label to see extracted data"
                                    className="min-h-[320px]"
                                />
                            )}

                            {analyzing && (
                                <div className="min-h-[320px] space-y-3" role="status" aria-live="polite">
                                    <Skeleton className="h-6 w-2/3" />
                                    <Skeleton className="h-4 w-full" />
                                    <Skeleton className="h-4 w-5/6" />
                                    <Skeleton className="h-4 w-4/6" />
                                    <p className="flex items-center gap-2 pt-2 text-small text-re-text-muted">
                                        <Spinner size="sm" />
                                        Extracting traceability data...
                                    </p>
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
                                            {fsmaBadge('Label contains likely-KDE fields', 'Label is missing common KDE fields')}
                                            {result.product_name && (
                                                <div className="flex items-start justify-between gap-3 py-1.5">
                                                    <span className="text-label text-re-text-muted">Product</span>
                                                    <span className="text-right text-ui font-medium text-re-text-primary">{result.product_name}</span>
                                                </div>
                                            )}
                                            <p className="text-center text-small text-re-text-tertiary">
                                                {result.fsma_kdes.length} KDEs extracted · {result.allergens.length} allergens detected
                                            </p>
                                        </div>
                                    }
                                >
                                    <div className="space-y-5">
                                        {/* FSMA badge */}
                                        <div>{fsmaBadge('FSMA 204 Compatible', 'Partial KDE Coverage')}</div>

                                        {/* Editable extracted fields */}
                                        <div className="space-y-2">
                                            <h3 className="text-subheading text-re-text-primary">Extracted Fields <span className="text-small font-normal text-re-text-tertiary">(click to edit)</span></h3>
                                            {DEMO_FIELDS.map(({ key, label }) => {
                                                const value = getFieldValue(key);
                                                if (!value && !editedFields[key]) return null;
                                                return (
                                                    <div key={key} className="flex items-center gap-3 border-b border-re-border-subtle py-1 last:border-0">
                                                        <label htmlFor={`label-field-${key}`} className="min-w-[100px] text-label text-re-text-muted">{label}</label>
                                                        <input
                                                            id={`label-field-${key}`}
                                                            type="text"
                                                            value={value}
                                                            onChange={(e) => updateField(key, e.target.value)}
                                                            className="flex-1 rounded-sm border-none bg-transparent px-1 py-0.5 text-right text-ui font-medium text-re-text-primary outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
                                                        />
                                                        {editedFields[key] !== undefined && (
                                                            <Badge tone="info" size="sm" mono>EDITED</Badge>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        {/* Confirm & Ingest */}
                                        <div className="pt-2">
                                            {ingested ? (
                                                <Callout tone="success" role="status" icon={Check}>
                                                    Ingested into trace pipeline
                                                </Callout>
                                            ) : (
                                                <Button
                                                    type="button"
                                                    size="lg"
                                                    onClick={confirmAndIngest}
                                                    loading={ingesting}
                                                    className="w-full"
                                                    leadingIcon={<ArrowRight aria-hidden="true" strokeWidth={1.75} />}
                                                >
                                                    {ingesting ? 'Ingesting...' : 'Confirm & Ingest'}
                                                </Button>
                                            )}
                                            {!apiKey && !ingested && (
                                                <p className="mt-2 text-center text-small text-re-text-tertiary">
                                                    <Link href="/login" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">Log in</Link> to ingest into your workspace
                                                </p>
                                            )}
                                        </div>
                                        {/* Allergens */}
                                        {result.allergens.length > 0 && (
                                            <div>
                                                <h3 className="mb-2 text-subheading text-re-text-primary">Allergens</h3>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {result.allergens.map((a) => (
                                                        <Badge key={a} tone="danger" size="sm">
                                                            {a}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Certifications */}
                                        {result.certifications.length > 0 && (
                                            <div>
                                                <h3 className="mb-2 text-subheading text-re-text-primary">Certifications</h3>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {result.certifications.map((c) => (
                                                        <Badge key={c} tone="neutral" size="sm">
                                                            {c}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Ingredients */}
                                        {result.ingredients && (
                                            <div>
                                                <h3 className="mb-2 text-subheading text-re-text-primary">Ingredients</h3>
                                                <p className="text-small leading-relaxed text-re-text-secondary">{result.ingredients}</p>
                                            </div>
                                        )}
                                        {/* FSMA KDEs */}
                                        {result.fsma_kdes.length > 0 && (
                                            <div>
                                                <h3 className="mb-2 text-subheading text-re-text-primary">FSMA 204 KDE Mapping</h3>
                                                <div className="space-y-1.5">
                                                    {result.fsma_kdes.map((kde, i) => (
                                                        <div key={i} className="flex items-center gap-2 text-small">
                                                            <span className="min-w-[120px] text-re-text-tertiary">{kde.field}</span>
                                                            <span className="flex-1 truncate font-mono text-[0.8125rem] text-re-text-primary">{kde.value || 'Not found'}</span>
                                                            <Badge
                                                                size="sm"
                                                                mono
                                                                tone={kde.confidence >= 0.8 ? 'neutral' : kde.confidence >= 0.5 ? 'warning' : 'danger'}
                                                            >
                                                                {Math.round(kde.confidence * 100)}%
                                                            </Badge>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Raw text toggle */}
                                        {result.raw_text && (
                                            <div>
                                                <button
                                                    type="button"
                                                    onClick={() => setShowRawText(!showRawText)}
                                                    aria-expanded={showRawText}
                                                    className="flex items-center gap-1.5 rounded-sm text-small text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                                                >
                                                    <ChevronDown aria-hidden="true" strokeWidth={1.75} className={cn('h-3.5 w-3.5 transition-transform duration-120 motion-reduce:transition-none', showRawText && 'rotate-180')} />
                                                    {showRawText ? 'Hide' : 'Show'} raw text
                                                </button>
                                                {showRawText && (
                                                    <pre className="mt-2 max-h-[200px] overflow-auto whitespace-pre-wrap rounded-md border border-re-border-subtle bg-re-surface-inset p-3 font-mono text-[0.8125rem] text-re-text-secondary">
                                                        {result.raw_text}
                                                    </pre>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </LeadGate>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* CTA */}
                <div className="mt-8 text-center">
                    <p className="mb-3 text-ui text-re-text-secondary">
                        Want this running on every receiving dock? Field Capture sends scans straight into your compliance pipeline.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/contact">
                                Become a Design Partner <ArrowRight aria-hidden="true" className="ml-2 h-3.5 w-3.5" strokeWidth={1.75} />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/tools">
                                All Free Tools
                            </Link>
                        </Button>
                    </div>
                </div>
            </Container>
        </div>
        </EmailGate>
    );
}
