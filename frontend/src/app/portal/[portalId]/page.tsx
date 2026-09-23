'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
    Truck, ArrowRight, ShieldCheck, Clock, FileCheck,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { getServiceURL } from '@/lib/api-config';
import { cn } from '@/lib/utils';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PortalDetails {
    portal_id: string;
    supplier_name: string;
    allowed_cte_types: string[];
    integration_profile_id?: string;
    integration_profile?: {
        profile_id: string;
        display_name: string;
        source_type: string;
        default_cte_type: string;
        status: string;
        confidence: number;
    } | null;
    status: string;
}

interface SubmissionResult {
    status: string;
    event_id?: string;
    sha256_hash?: string;
    message: string;
    supplier_name: string;
    submitted_at: string;
}

interface SupplierPreflightResult {
    status: string;
    message: string;
    supplier_name: string;
    readiness: {
        score: number;
        label: string;
    };
    commit_gate: {
        allowed: boolean;
        next_state: string;
        reasons: string[];
    };
    result: {
        total_kde_errors: number;
        total_rule_failures: number;
        blocking_reasons: string[];
    };
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await fetch(url, {
        ...init,
        headers: {
            ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
            ...(init?.headers || {}),
        },
    });
    const data = await response.text().then((text) => {
        if (!text) return null;
        try {
            return JSON.parse(text);
        } catch {
            return text;
        }
    });
    if (!response.ok) {
        throw { status: response.status, data };
    }
    return data as T;
}

function getRequestErrorMessage(error: unknown, fallback: string): string {
    if (error && typeof error === 'object' && 'data' in error) {
        const data = (error as { data?: unknown }).data;
        if (data && typeof data === 'object' && 'detail' in data) {
            const detail = (data as { detail?: unknown }).detail;
            if (typeof detail === 'string' && detail.trim()) return detail;
        }
    }
    return fallback;
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function PortalSubmissionPage() {
    const params = useParams();
    const portalId = params.portalId as string;

    // Portal state
    const [portal, setPortal] = useState<PortalDetails | null>(null);
    const [loadingPortal, setLoadingPortal] = useState(true);
    const [portalError, setPortalError] = useState<string | null>(null);

    // Form state
    const [tlc, setTlc] = useState('');
    const [productDescription, setProductDescription] = useState('');
    const [quantity, setQuantity] = useState('');
    const [unitOfMeasure, setUnitOfMeasure] = useState('cases');
    const [shipDate, setShipDate] = useState(new Date().toISOString().split('T')[0]);
    const [shipFromLocation, setShipFromLocation] = useState('');
    const [shipFromGln, setShipFromGln] = useState('');
    const [shipToLocation, setShipToLocation] = useState('');
    const [shipToGln, setShipToGln] = useState('');
    const [carrierName, setCarrierName] = useState('');
    const [poNumber, setPoNumber] = useState('');
    const [temperatureCelsius, setTemperatureCelsius] = useState('');
    const [notes, setNotes] = useState('');

    // Submission state
    const [preflighting, setPreflighting] = useState(false);
    const [preflight, setPreflight] = useState<SupplierPreflightResult | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState<SubmissionResult | null>(null);
    const [submitError, setSubmitError] = useState<string | null>(null);

    const baseUrl = getServiceURL('ingestion');

    // Load portal details on mount
    useEffect(() => {
        if (!portalId) return;
        setLoadingPortal(true);

        requestJson<PortalDetails>(`${baseUrl}/api/v1/portal/${portalId}`)
            .then((data) => {
                setPortal(data);
                setPortalError(null);
            })
            .catch((err) => {
                const msg = getRequestErrorMessage(err, 'This portal link is not found or has expired.');
                setPortalError(msg);
            })
            .finally(() => setLoadingPortal(false));
    }, [portalId, baseUrl]);

    // Form validation
    const isValid = tlc.trim().length >= 3
        && productDescription.trim().length > 0
        && parseFloat(quantity) > 0
        && shipDate
        && shipFromLocation.trim().length > 0
        && shipToLocation.trim().length > 0;

    const submissionPayload = () => ({
        traceability_lot_code: tlc.trim(),
        product_description: productDescription.trim(),
        quantity: parseFloat(quantity),
        unit_of_measure: unitOfMeasure,
        ship_date: shipDate,
        ship_from_location: shipFromLocation.trim(),
        ship_from_gln: shipFromGln.trim() || undefined,
        ship_to_location: shipToLocation.trim(),
        ship_to_gln: shipToGln.trim() || undefined,
        carrier_name: carrierName.trim() || undefined,
        po_number: poNumber.trim() || undefined,
        temperature_celsius: temperatureCelsius ? parseFloat(temperatureCelsius) : undefined,
        notes: notes.trim() || undefined,
    });

    const runPreflight = async () => {
        if (!isValid || preflighting) return null;
        setPreflighting(true);
        setSubmitError(null);
        try {
            const data = await requestJson<SupplierPreflightResult>(
                `${baseUrl}/api/v1/portal/${portalId}/preflight`,
                {
                    method: 'POST',
                    body: JSON.stringify(submissionPayload()),
                },
            );
            setPreflight(data);
            return data;
        } catch (err: unknown) {
            setSubmitError(getRequestErrorMessage(err, 'Preflight failed. Please try again.'));
            return null;
        } finally {
            setPreflighting(false);
        }
    };

    // Submit handler
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!isValid || submitting) return;

        setSubmitting(true);
        setSubmitError(null);

        try {
            const preflightResult = await runPreflight();
            if (!preflightResult || preflightResult.status !== 'ready') {
                setSubmitError(preflightResult?.message || 'Preflight must pass before submission.');
                return;
            }
            const data = await requestJson<SubmissionResult>(
                `${baseUrl}/api/v1/portal/${portalId}/submit`,
                {
                    method: 'POST',
                    body: JSON.stringify(submissionPayload()),
                },
            );
            if (data.status !== 'accepted') {
                setSubmitError(data.message || 'Submission did not pass final validation.');
                return;
            }
            setResult(data);
        } catch (err: unknown) {
            setSubmitError(getRequestErrorMessage(err, 'Submission failed. Please try again.'));
        } finally {
            setSubmitting(false);
        }
    };

    // Reset for another submission
    const handleSubmitAnother = () => {
        setResult(null);
        setTlc('');
        setProductDescription('');
        setQuantity('');
        setCarrierName('');
        setPoNumber('');
        setTemperatureCelsius('');
        setNotes('');
        setPreflight(null);
    };

    /* ---------- Loading / Error states ------------------------------ */

    if (loadingPortal) {
        return (
            <Container width="prose" className="py-10 sm:py-14">
                <div className="space-y-6" aria-busy="true">
                    <div className="space-y-3 border-b border-re-border-subtle pb-5">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-8 w-64" />
                        <Skeleton className="h-4 w-48" />
                    </div>
                    <p className="text-ui text-re-text-tertiary">Loading portal...</p>
                    <Skeleton className="h-96 w-full" />
                </div>
            </Container>
        );
    }

    if (portalError || !portal) {
        return (
            <Container width="prose" className="py-10 sm:py-14">
                <PageHeader title="Portal Link Unavailable" />
                <Callout tone="danger" role="alert">
                    {portalError || 'This portal link is not found or has expired.'}
                </Callout>
                <p className="mt-4 text-small text-re-text-tertiary">
                    Contact your buyer for a new portal link, or{' '}
                    <Link href="/supplier-compliance" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">
                        learn about FSMA 204 compliance
                    </Link>.
                </p>
            </Container>
        );
    }

    /* ---------- Success state --------------------------------------- */

    if (result && result.status === 'accepted') {
        return (
            <Container width="prose" className="py-10 sm:py-14">
                <PageHeader
                    title="Shipment Data Received"
                    description="Your traceability data has been validated and recorded."
                />

                <Card>
                    <CardContent className="space-y-5">
                        <dl className="divide-y divide-re-border-subtle">
                            <div className="flex items-center justify-between gap-4 py-2 first:pt-0">
                                <dt className="text-ui text-re-text-muted">Event ID</dt>
                                <dd className="font-mono text-[0.8125rem] text-re-text-secondary">{result.event_id}</dd>
                            </div>
                            <div className="flex items-center justify-between gap-4 py-2">
                                <dt className="text-ui text-re-text-muted">SHA-256 Hash</dt>
                                <dd className="max-w-[16rem] truncate font-mono text-[0.8125rem] text-re-text-secondary">
                                    {result.sha256_hash}
                                </dd>
                            </div>
                            <div className="flex items-center justify-between gap-4 py-2 last:pb-0">
                                <dt className="text-ui text-re-text-muted">Submitted</dt>
                                <dd className="text-ui text-re-text-secondary">
                                    {new Date(result.submitted_at).toLocaleString()}
                                </dd>
                            </div>
                        </dl>

                        <p className="flex items-center gap-2 text-small text-re-text-tertiary">
                            <ShieldCheck className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                            <span>Cryptographically verified and chain-linked</span>
                        </p>

                        <Button size="lg" onClick={handleSubmitAnother} trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}>
                            Submit Another Shipment
                        </Button>
                    </CardContent>
                </Card>

                <p className="mt-4 text-center text-small text-re-text-tertiary">
                    Powered by <Link href="/" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">RegEngine</Link> — FSMA 204 Compliance
                </p>
            </Container>
        );
    }

    /* ---------- Submission form -------------------------------------- */

    const UOM_OPTIONS = ['cases', 'lbs', 'kg', 'pallets', 'each', 'cartons', 'bags'];

    const TRUST_FACTS = [
        { icon: ShieldCheck, label: 'SHA-256 hash-chained' },
        { icon: Clock, label: 'FSMA 204 program' },
        { icon: FileCheck, label: '§1.1455(c) format' },
    ];

    return (
        <Container width="prose" className="py-10 sm:py-14">
            <PageHeader
                eyebrow={
                    <span className="inline-flex items-center gap-1.5">
                        <Truck className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                        Supplier Portal
                    </span>
                }
                title="Submit Shipment Data"
                description={
                    <>
                        Submitting for <span className="font-medium text-re-text-primary">{portal.supplier_name}</span>
                    </>
                }
            />

            {/* Trust facts */}
            <ul className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
                {TRUST_FACTS.map((fact, index) => (
                    <li
                        key={fact.label}
                        className={cn(
                            'flex items-center gap-1.5 text-label text-re-text-tertiary',
                            index > 0 && 'sm:border-l sm:border-re-border-subtle sm:pl-4'
                        )}
                    >
                        <fact.icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        {fact.label}
                    </li>
                ))}
            </ul>

            {portal.integration_profile && (
                <Card className="mb-6">
                    <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-start gap-3">
                            <FileCheck className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <div className="min-w-0">
                                <div className="text-ui font-medium text-re-text-primary">
                                    {portal.integration_profile.display_name}
                                </div>
                                <div className="text-small text-re-text-tertiary">
                                    {portal.integration_profile.source_type.toUpperCase()} mapping · {portal.integration_profile.default_cte_type}
                                </div>
                            </div>
                        </div>
                        <div className="text-small tabular-nums text-re-text-tertiary">
                            {Math.round(portal.integration_profile.confidence * 100)}% mapping confidence
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit}>
                <Card>
                    {/* Required fields */}
                    <div className="space-y-4 p-5">
                        <h2 className="text-subheading text-re-text-primary">
                            Shipment Details
                        </h2>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <Field
                                className="sm:col-span-2"
                                label="Traceability Lot Code (TLC)"
                                htmlFor="portal-tlc"
                                required
                            >
                                <Input
                                    type="text"
                                    size="lg"
                                    value={tlc}
                                    onChange={(e) => setTlc(e.target.value)}
                                    placeholder="e.g., LOT-2026-03-001"
                                    minLength={3}
                                    mono
                                />
                            </Field>

                            <Field
                                className="sm:col-span-2"
                                label="Product Description"
                                htmlFor="portal-product-description"
                                required
                            >
                                <Input
                                    type="text"
                                    size="lg"
                                    value={productDescription}
                                    onChange={(e) => setProductDescription(e.target.value)}
                                    placeholder="e.g., Romaine Lettuce Hearts, 3-pack"
                                />
                            </Field>

                            <Field label="Quantity" htmlFor="portal-quantity" required>
                                <Input
                                    type="number"
                                    size="lg"
                                    value={quantity}
                                    onChange={(e) => setQuantity(e.target.value)}
                                    placeholder="e.g., 500"
                                    min="0.01"
                                    step="any"
                                />
                            </Field>

                            <Field label="Unit of Measure" htmlFor="portal-uom" required>
                                <select
                                    value={unitOfMeasure}
                                    onChange={(e) => setUnitOfMeasure(e.target.value)}
                                    className={cn(fieldControlClasses, 'h-11')}
                                >
                                    {UOM_OPTIONS.map((uom) => (
                                        <option key={uom} value={uom}>{uom}</option>
                                    ))}
                                </select>
                            </Field>

                            <Field label="Ship Date" htmlFor="portal-ship-date" required>
                                <Input
                                    type="date"
                                    size="lg"
                                    value={shipDate}
                                    onChange={(e) => setShipDate(e.target.value)}
                                />
                            </Field>
                        </div>
                    </div>

                    {/* Location fields */}
                    <div className="space-y-4 border-t border-re-border-subtle p-5">
                        <h2 className="text-subheading text-re-text-primary">
                            Origin &amp; Destination
                        </h2>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <Field label="Ship From (Facility Name)" htmlFor="portal-ship-from" required>
                                <Input
                                    type="text"
                                    size="lg"
                                    value={shipFromLocation}
                                    onChange={(e) => setShipFromLocation(e.target.value)}
                                    placeholder="e.g., Central Valley Farms"
                                />
                            </Field>

                            <Field label="Ship From GLN" htmlFor="portal-ship-from-gln">
                                <Input
                                    type="text"
                                    size="lg"
                                    value={shipFromGln}
                                    onChange={(e) => setShipFromGln(e.target.value)}
                                    placeholder="13-digit GLN (optional)"
                                    mono
                                />
                            </Field>

                            <Field label="Ship To (Facility Name)" htmlFor="portal-ship-to" required>
                                <Input
                                    type="text"
                                    size="lg"
                                    value={shipToLocation}
                                    onChange={(e) => setShipToLocation(e.target.value)}
                                    placeholder="e.g., Walmart DC #4523"
                                />
                            </Field>

                            <Field label="Ship To GLN" htmlFor="portal-ship-to-gln">
                                <Input
                                    type="text"
                                    size="lg"
                                    value={shipToGln}
                                    onChange={(e) => setShipToGln(e.target.value)}
                                    placeholder="13-digit GLN (optional)"
                                    mono
                                />
                            </Field>
                        </div>
                    </div>

                    {/* Optional fields */}
                    <div className="space-y-4 border-t border-re-border-subtle p-5">
                        <h2 className="text-subheading text-re-text-primary">
                            Additional Details (Optional)
                        </h2>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                            <Field label="Carrier Name" htmlFor="portal-carrier">
                                <Input
                                    type="text"
                                    size="lg"
                                    value={carrierName}
                                    onChange={(e) => setCarrierName(e.target.value)}
                                    placeholder="e.g., FedEx Freight"
                                />
                            </Field>

                            <Field label="PO Number" htmlFor="portal-po-number">
                                <Input
                                    type="text"
                                    size="lg"
                                    value={poNumber}
                                    onChange={(e) => setPoNumber(e.target.value)}
                                    placeholder="e.g., PO-78234"
                                    mono
                                />
                            </Field>

                            <Field label="Temperature (C)" htmlFor="portal-temperature">
                                <Input
                                    type="number"
                                    size="lg"
                                    value={temperatureCelsius}
                                    onChange={(e) => setTemperatureCelsius(e.target.value)}
                                    placeholder="e.g., 4"
                                    step="0.1"
                                />
                            </Field>
                        </div>

                        <Field label="Notes" htmlFor="portal-notes">
                            <textarea
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                placeholder="Any additional notes about this shipment..."
                                rows={2}
                                className={cn(fieldControlClasses, 'h-auto resize-none py-2')}
                            />
                        </Field>
                    </div>

                    {/* Submit */}
                    <div className="space-y-3 border-t border-re-border-subtle bg-re-surface-inset p-5">
                        {preflight && (
                            <Callout tone={preflight.status === 'ready' ? 'success' : 'warning'}>
                                <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                                    <div className="min-w-0">
                                        <div className="font-medium text-re-text-primary">
                                            Preflight {preflight.status === 'ready' ? 'passed' : 'blocked'} · {preflight.readiness.score}
                                        </div>
                                        <div className="mt-0.5 text-small">{preflight.message}</div>
                                    </div>
                                    <span className="shrink-0 font-mono text-small text-re-text-tertiary">{preflight.commit_gate.next_state}</span>
                                </div>
                                {preflight.result.blocking_reasons.length > 0 && (
                                    <ul className="mt-2 space-y-1 text-small">
                                        {preflight.result.blocking_reasons.slice(0, 3).map((reason) => (
                                            <li key={reason}>{reason}</li>
                                        ))}
                                    </ul>
                                )}
                            </Callout>
                        )}

                        {submitError && (
                            <Callout tone="danger" role="alert">
                                {submitError}
                            </Callout>
                        )}

                        <Button
                            type="button"
                            variant="secondary"
                            size="lg"
                            className="w-full"
                            disabled={!isValid || preflighting || submitting}
                            onClick={runPreflight}
                            loading={preflighting}
                            leadingIcon={<ShieldCheck strokeWidth={1.75} aria-hidden="true" />}
                        >
                            {preflighting ? 'Running Preflight...' : 'Preflight Check'}
                        </Button>

                        <Button
                            type="submit"
                            size="lg"
                            className="w-full"
                            disabled={!isValid || submitting || preflighting}
                            loading={submitting}
                        >
                            {submitting ? 'Submitting...' : 'Submit Shipment Data'}
                        </Button>

                        <p className="text-center text-small text-re-text-tertiary">
                            Data is SHA-256 hashed and chain-linked for FSMA 204 compliance.
                            No account required.
                        </p>
                    </div>
                </Card>
            </form>

            {/* Footer */}
            <div className="mt-6 space-y-2 text-center">
                <p className="text-small text-re-text-tertiary">
                    Powered by <Link href="/" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">RegEngine</Link> — FSMA 204 Compliance Infrastructure
                </p>
                <Link
                    href="/supplier-compliance"
                    className="inline-flex items-center gap-1 text-small text-re-brand no-underline hover:underline"
                >
                    Learn about FSMA 204 compliance <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                </Link>
            </div>
        </Container>
    );
}
