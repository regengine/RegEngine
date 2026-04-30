'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
    Package, Truck, CheckCircle2, AlertTriangle, Loader2,
    ArrowRight, ShieldCheck, Clock, FileCheck,
} from 'lucide-react';
import axios from 'axios';
import { getServiceURL } from '@/lib/api-config';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PortalDetails {
    portal_id: string;
    supplier_name: string;
    allowed_cte_types: string[];
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

        axios.get(`${baseUrl}/api/v1/portal/${portalId}`)
            .then((res) => {
                setPortal(res.data);
                setPortalError(null);
            })
            .catch((err) => {
                const msg = err.response?.data?.detail || 'This portal link is not found or has expired.';
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
            const { data } = await axios.post<SupplierPreflightResult>(
                `${baseUrl}/api/v1/portal/${portalId}/preflight`,
                submissionPayload(),
            );
            setPreflight(data);
            return data;
        } catch (err: unknown) {
            if (axios.isAxiosError(err)) {
                setSubmitError(err.response?.data?.detail || 'Preflight failed. Please try again.');
            } else {
                setSubmitError('Preflight failed. Please try again.');
            }
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
            const preflightResult = preflight?.status === 'ready' ? preflight : await runPreflight();
            if (!preflightResult || preflightResult.status !== 'ready') {
                setSubmitError(preflightResult?.message || 'Preflight must pass before submission.');
                return;
            }
            const { data } = await axios.post<SubmissionResult>(
                `${baseUrl}/api/v1/portal/${portalId}/submit`,
                submissionPayload(),
            );
            setResult(data);
        } catch (err: unknown) {
            if (axios.isAxiosError(err)) {
                setSubmitError(err.response?.data?.detail || 'Submission failed. Please try again.');
            } else {
                setSubmitError('Submission failed. Please try again.');
            }
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
            <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin text-[var(--re-brand)] mx-auto mb-4" />
                    <p className="text-[var(--re-text-muted)]">Loading portal...</p>
                </div>
            </div>
        );
    }

    if (portalError || !portal) {
        return (
            <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center px-4">
                <div className="max-w-md text-center">
                    <AlertTriangle className="h-12 w-12 text-re-warning mx-auto mb-4" />
                    <h1 className="text-xl font-bold text-[var(--re-text-primary)] mb-2">
                        Portal Link Unavailable
                    </h1>
                    <p className="text-[var(--re-text-muted)] mb-6">
                        {portalError || 'This portal link is not found or has expired.'}
                    </p>
                    <p className="text-sm text-[var(--re-text-disabled)]">
                        Contact your buyer for a new portal link, or{' '}
                        <Link href="/supplier-compliance" className="text-[var(--re-brand)] underline">
                            learn about FSMA 204 compliance
                        </Link>.
                    </p>
                </div>
            </div>
        );
    }

    /* ---------- Success state --------------------------------------- */

    if (result && result.status === 'accepted') {
        return (
            <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center px-4">
                <div className="max-w-lg w-full">
                    <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-2xl p-8 text-center shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                        <CheckCircle2 className="h-16 w-16 text-[var(--re-brand)] mx-auto mb-4" />
                        <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">
                            Shipment Data Received
                        </h1>
                        <p className="text-[var(--re-text-muted)] mb-6">
                            Your traceability data has been verified and recorded.
                        </p>

                        <div className="bg-[var(--re-surface-elevated)] rounded-xl p-4 text-left space-y-2 mb-6">
                            <div className="flex justify-between text-sm">
                                <span className="text-[var(--re-text-muted)]">Event ID</span>
                                <span className="font-mono text-xs text-[var(--re-text-secondary)]">{result.event_id}</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-[var(--re-text-muted)]">SHA-256 Hash</span>
                                <span className="font-mono text-[10px] text-[var(--re-text-secondary)] max-w-[200px] truncate">
                                    {result.sha256_hash}
                                </span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-[var(--re-text-muted)]">Submitted</span>
                                <span className="text-[var(--re-text-secondary)]">
                                    {new Date(result.submitted_at).toLocaleString()}
                                </span>
                            </div>
                        </div>

                        <div className="flex items-center justify-center gap-2 text-xs text-[var(--re-text-disabled)] mb-6">
                            <ShieldCheck className="h-3.5 w-3.5" />
                            <span>Cryptographically verified and chain-linked</span>
                        </div>

                        <button
                            onClick={handleSubmitAnother}
                            className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-3 rounded-xl text-sm font-semibold hover:brightness-110 transition-all active:scale-[0.97]"
                        >
                            Submit Another Shipment <ArrowRight className="h-4 w-4" />
                        </button>
                    </div>

                    <p className="text-center text-xs text-[var(--re-text-disabled)] mt-4">
                        Powered by <Link href="/" className="text-[var(--re-brand)] underline">RegEngine</Link> — FSMA 204 Compliance
                    </p>
                </div>
            </div>
        );
    }

    /* ---------- Submission form -------------------------------------- */

    const UOM_OPTIONS = ['cases', 'lbs', 'kg', 'pallets', 'each', 'cartons', 'bags'];

    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] py-8 px-4">
            <div className="max-w-2xl mx-auto">
                {/* Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center gap-2 bg-[var(--re-brand-muted)] text-[var(--re-brand)] px-3 py-1.5 rounded-lg text-xs font-semibold mb-4">
                        <Truck className="h-3.5 w-3.5" />
                        Supplier Portal
                    </div>
                    <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">
                        Submit Shipment Data
                    </h1>
                    <p className="text-[var(--re-text-muted)]">
                        Submitting for <span className="font-semibold text-[var(--re-text-primary)]">{portal.supplier_name}</span>
                    </p>
                </div>

                {/* Trust badges */}
                <div className="flex items-center justify-center gap-4 mb-6 flex-wrap">
                    {[
                        { icon: ShieldCheck, label: 'SHA-256 verified' },
                        { icon: Clock, label: 'FSMA 204 compliant' },
                        { icon: FileCheck, label: 'FDA-ready format' },
                    ].map((badge) => (
                        <div key={badge.label} className="flex items-center gap-1.5 text-xs text-[var(--re-text-disabled)]">
                            <badge.icon className="h-3.5 w-3.5 text-[var(--re-brand)]" />
                            {badge.label}
                        </div>
                    ))}
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit}>
                    <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] overflow-hidden">

                        {/* Required fields */}
                        <div className="p-6 space-y-4">
                            <h2 className="text-sm font-semibold text-[var(--re-text-primary)] flex items-center gap-2">
                                <Package className="h-4 w-4 text-[var(--re-brand)]" />
                                Shipment Details
                            </h2>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div className="sm:col-span-2">
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Traceability Lot Code (TLC) *
                                    </label>
                                    <input
                                        type="text"
                                        value={tlc}
                                        onChange={(e) => setTlc(e.target.value)}
                                        placeholder="e.g., LOT-2026-03-001"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                        required
                                        minLength={3}
                                    />
                                </div>

                                <div className="sm:col-span-2">
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Product Description *
                                    </label>
                                    <input
                                        type="text"
                                        value={productDescription}
                                        onChange={(e) => setProductDescription(e.target.value)}
                                        placeholder="e.g., Romaine Lettuce Hearts, 3-pack"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Quantity *
                                    </label>
                                    <input
                                        type="number"
                                        value={quantity}
                                        onChange={(e) => setQuantity(e.target.value)}
                                        placeholder="e.g., 500"
                                        min="0.01"
                                        step="any"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Unit of Measure *
                                    </label>
                                    <select
                                        value={unitOfMeasure}
                                        onChange={(e) => setUnitOfMeasure(e.target.value)}
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                    >
                                        {UOM_OPTIONS.map((uom) => (
                                            <option key={uom} value={uom}>{uom}</option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Ship Date *
                                    </label>
                                    <input
                                        type="date"
                                        value={shipDate}
                                        onChange={(e) => setShipDate(e.target.value)}
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                        required
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Location fields */}
                        <div className="p-6 border-t border-[var(--re-surface-border)] space-y-4">
                            <h2 className="text-sm font-semibold text-[var(--re-text-primary)] flex items-center gap-2">
                                <Truck className="h-4 w-4 text-[var(--re-brand)]" />
                                Origin & Destination
                            </h2>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Ship From (Facility Name) *
                                    </label>
                                    <input
                                        type="text"
                                        value={shipFromLocation}
                                        onChange={(e) => setShipFromLocation(e.target.value)}
                                        placeholder="e.g., Central Valley Farms"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Ship From GLN
                                    </label>
                                    <input
                                        type="text"
                                        value={shipFromGln}
                                        onChange={(e) => setShipFromGln(e.target.value)}
                                        placeholder="13-digit GLN (optional)"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Ship To (Facility Name) *
                                    </label>
                                    <input
                                        type="text"
                                        value={shipToLocation}
                                        onChange={(e) => setShipToLocation(e.target.value)}
                                        placeholder="e.g., Walmart DC #4523"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                        required
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Ship To GLN
                                    </label>
                                    <input
                                        type="text"
                                        value={shipToGln}
                                        onChange={(e) => setShipToGln(e.target.value)}
                                        placeholder="13-digit GLN (optional)"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Optional fields */}
                        <div className="p-6 border-t border-[var(--re-surface-border)] space-y-4">
                            <h2 className="text-sm font-semibold text-[var(--re-text-muted)]">
                                Additional Details (Optional)
                            </h2>

                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Carrier Name
                                    </label>
                                    <input
                                        type="text"
                                        value={carrierName}
                                        onChange={(e) => setCarrierName(e.target.value)}
                                        placeholder="e.g., FedEx Freight"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        PO Number
                                    </label>
                                    <input
                                        type="text"
                                        value={poNumber}
                                        onChange={(e) => setPoNumber(e.target.value)}
                                        placeholder="e.g., PO-78234"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                        Temperature (C)
                                    </label>
                                    <input
                                        type="number"
                                        value={temperatureCelsius}
                                        onChange={(e) => setTemperatureCelsius(e.target.value)}
                                        placeholder="e.g., 4"
                                        step="0.1"
                                        className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-medium text-[var(--re-text-muted)] mb-1.5">
                                    Notes
                                </label>
                                <textarea
                                    value={notes}
                                    onChange={(e) => setNotes(e.target.value)}
                                    placeholder="Any additional notes about this shipment..."
                                    rows={2}
                                    className="w-full px-3 py-2.5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent resize-none"
                                />
                            </div>
                        </div>

                        {/* Submit */}
                        <div className="p-6 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
                            {preflight && (
                                <div
                                    className={`p-3 rounded-xl text-sm mb-4 border ${
                                        preflight.status === 'ready'
                                            ? 'bg-re-success-muted border-re-success text-re-success'
                                            : 'bg-re-warning-muted border-re-warning text-re-warning'
                                    }`}
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <div className="font-semibold">
                                                Preflight {preflight.status === 'ready' ? 'passed' : 'blocked'} · {preflight.readiness.score}
                                            </div>
                                            <div className="text-xs mt-0.5 opacity-90">{preflight.message}</div>
                                        </div>
                                        <span className="text-xs font-mono">{preflight.commit_gate.next_state}</span>
                                    </div>
                                    {preflight.result.blocking_reasons.length > 0 && (
                                        <ul className="mt-2 space-y-1 text-xs">
                                            {preflight.result.blocking_reasons.slice(0, 3).map((reason) => (
                                                <li key={reason}>{reason}</li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            )}

                            {submitError && (
                                <div className="p-3 bg-re-danger-muted dark:bg-re-danger border border-re-danger dark:border-re-danger rounded-xl text-sm text-re-danger dark:text-re-danger mb-4">
                                    {submitError}
                                </div>
                            )}

                            <button
                                type="button"
                                disabled={!isValid || preflighting || submitting}
                                onClick={runPreflight}
                                className="w-full inline-flex items-center justify-center gap-2 bg-[var(--re-surface-card)] text-[var(--re-text-primary)] border border-[var(--re-surface-border)] px-6 py-3 rounded-xl text-sm font-semibold transition-all hover:border-[var(--re-brand)] disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.97] mb-2"
                            >
                                {preflighting ? (
                                    <>
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Running Preflight...
                                    </>
                                ) : (
                                    <>
                                        <ShieldCheck className="h-4 w-4 text-[var(--re-brand)]" />
                                        Preflight Check
                                    </>
                                )}
                            </button>

                            <button
                                type="submit"
                                disabled={!isValid || submitting || preflighting}
                                className="w-full inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-6 py-3.5 rounded-xl text-sm font-semibold transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.97]"
                            >
                                {submitting ? (
                                    <>
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Submitting...
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle2 className="h-4 w-4" />
                                        Submit Shipment Data
                                    </>
                                )}
                            </button>

                            <p className="text-center text-[11px] text-[var(--re-text-disabled)] mt-3">
                                Data is SHA-256 hashed and chain-linked for FSMA 204 compliance.
                                No account required.
                            </p>
                        </div>
                    </div>
                </form>

                {/* Footer */}
                <div className="text-center mt-6 space-y-2">
                    <p className="text-xs text-[var(--re-text-disabled)]">
                        Powered by <Link href="/" className="text-[var(--re-brand)] underline">RegEngine</Link> — FSMA 204 Compliance Infrastructure
                    </p>
                    <Link
                        href="/supplier-compliance"
                        className="inline-flex items-center gap-1 text-xs text-[var(--re-brand)] hover:underline"
                    >
                        Learn about FSMA 204 compliance <ArrowRight className="h-3 w-3" />
                    </Link>
                </div>
            </div>
        </div>
    );
}
