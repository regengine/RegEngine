'use client';

import { FormEvent, ReactNode, useCallback, useEffect, useState } from 'react';
import { ArrowRight, Check, ChevronDown, Lock, Sparkles } from 'lucide-react';
import { submitAssessment, type AssessmentFormData } from '@/app/actions/submit-assessment';

/* ────────────────────────────────────────────────────────────── */
/*  Props                                                        */
/* ────────────────────────────────────────────────────────────── */
export interface LeadGateProps {
    /** Which tool triggered this gate — stored as `source` in the DB */
    source: string;
    /** Headline above the form — e.g. "Get Your Full Compliance Report" */
    headline?: string;
    /** Subheadline — e.g. "Our founder reviews every submission within 24h" */
    subheadline?: string;
    /** CTA button text — e.g. "Unlock Full Results" */
    ctaText?: string;
    /** Any tool-specific data to store (quiz answers, scores, inputs) */
    toolContext?: {
        quizScore?: number;
        quizGrade?: string;
        quizAnswers?: Record<string, unknown>;
        toolInputs?: Record<string, unknown>;
    };
    /** Content shown BEFORE unlock (teaser) */
    teaser?: ReactNode;
    /** Content shown AFTER unlock (full results) */
    children: ReactNode;
    /** Callback when lead is captured — parent can update its own state */
    onUnlock?: () => void;
}
/* ────────────────────────────────────────────────────────────── */
/*  Styles                                                       */
/* ────────────────────────────────────────────────────────────── */
const inputClass =
    'w-full px-4 py-3 rounded-xl text-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] transition-shadow';
const selectClass = inputClass;

/* ────────────────────────────────────────────────────────────── */
/*  Component                                                    */
/* ────────────────────────────────────────────────────────────── */
export function LeadGate({
    source,
    headline = 'Unlock Your Full Results',
    subheadline = 'Our founder personally reviews every submission within 24 hours.',
    ctaText = 'Unlock Full Results',
    toolContext,
    teaser,
    children,
    onUnlock,
}: LeadGateProps) {
    const [step, setStep] = useState<'gate' | 'enrich' | 'done'>('gate');
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [gateData, setGateData] = useState<Partial<AssessmentFormData>>({});
    // Capture UTM params on mount
    const [utmParams, setUtmParams] = useState<Record<string, string>>({});
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const params = new URLSearchParams(window.location.search);
        setUtmParams({
            utmSource: params.get('utm_source') || '',
            utmMedium: params.get('utm_medium') || '',
            utmCampaign: params.get('utm_campaign') || '',
            referrer: document.referrer || '',
        });
    }, []);

    // Check localStorage for returning leads (non-PII flag only — no email stored)
    useEffect(() => {
        if (typeof window === 'undefined') return;
        // Migrate: clear legacy plain-text email if present
        if (localStorage.getItem('re_lead_email')) {
            localStorage.removeItem('re_lead_email');
            localStorage.setItem('re_lead_captured', '1');
        }
        const captured = localStorage.getItem('re_lead_captured');
        if (captured) {
            setStep('done');
            onUnlock?.();
        }
    }, [onUnlock]);

    /* ── Step 1: Gate form ── */
    const handleGateSubmit = useCallback(
        async (e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            setSubmitting(true);
            setError(null);
            const fd = new FormData(e.currentTarget);
            const data: AssessmentFormData = {
                name: fd.get('name') as string,
                email: fd.get('email') as string,
                company: fd.get('company') as string,
                role: fd.get('role') as string,
                source,
                quizScore: toolContext?.quizScore,
                quizGrade: toolContext?.quizGrade,
                quizAnswers: toolContext?.quizAnswers,
                toolInputs: toolContext?.toolInputs,
                ...utmParams,
            };

            const result = await submitAssessment(data);
            setSubmitting(false);

            if (!result.success) {
                setError(result.error || 'Something went wrong.');
                return;
            }

            // Persist a non-PII flag so returning visitors bypass the gate
            try { localStorage.setItem('re_lead_captured', '1'); } catch {}
            setGateData(data);
            setStep('enrich');
        },
        [source, toolContext, utmParams],
    );
    /* ── Step 2: Enrichment form (optional, skippable) ── */
    const handleEnrichSubmit = useCallback(
        async (e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            setSubmitting(true);

            const fd = new FormData(e.currentTarget);
            const enrichData: AssessmentFormData = {
                ...gateData as AssessmentFormData,
                facilityCount: fd.get('facilityCount') as string,
                annualRevenue: fd.get('annualRevenue') as string,
                currentSystem: fd.get('currentSystem') as string,
                biggestRetailer: fd.get('biggestRetailer') as string,
                complianceDeadline: fd.get('complianceDeadline') as string,
                recentFdaInspection: fd.get('recentFdaInspection') as string,
                phone: fd.get('phone') as string,
                productCategories: fd.get('productCategories') as string,
            };

            await submitAssessment(enrichData);
            setSubmitting(false);
            setStep('done');
            onUnlock?.();
        },
        [gateData, onUnlock],
    );

    const skipEnrichment = useCallback(() => {
        setStep('done');
        onUnlock?.();
    }, [onUnlock]);
    /* ── Render ── */

    // Already unlocked — show full results
    if (step === 'done') {
        return <>{children}</>;
    }

    return (
        <div className="space-y-6">
            {/* Show teaser (blurred/partial results) */}
            {teaser && (
                <div className="relative">
                    {teaser}
                    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[var(--re-surface-card)]/60 to-[var(--re-surface-card)] pointer-events-none rounded-xl" />
                </div>
            )}

            {step === 'gate' && (
                <div className="p-6 rounded-2xl border-2 border-[var(--re-brand)] bg-[var(--re-brand)]/[0.03]">
                    <div className="text-center mb-5">
                        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--re-brand)]/10 text-[var(--re-brand)] text-xs font-bold uppercase tracking-widest mb-3">
                            <Lock className="h-3 w-3" /> Free — No Credit Card
                        </div>
                        <h3 className="text-lg font-bold text-[var(--re-text-primary)]">{headline}</h3>
                        <p className="text-sm text-[var(--re-text-muted)] mt-1">{subheadline}</p>
                    </div>
                    <form onSubmit={handleGateSubmit} className="space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <input name="name" required placeholder="Full Name" className={inputClass} />
                            <input name="email" type="email" required placeholder="Work Email" className={inputClass} />
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <input name="company" required placeholder="Company Name" className={inputClass} />
                            <select name="role" required className={selectClass}>
                                <option value="">Your Role *</option>
                                <option value="qa-food-safety">QA / Food Safety</option>
                                <option value="operations">Operations</option>
                                <option value="compliance">Compliance / Regulatory</option>
                                <option value="supply-chain">Supply Chain</option>
                                <option value="executive">Executive / Owner</option>
                                <option value="it">IT / Engineering</option>
                                <option value="consultant">Consultant / Advisor</option>
                                <option value="other">Other</option>
                            </select>
                        </div>

                        {error && (
                            <p className="text-sm text-re-danger text-center">{error}</p>
                        )}
                        <button
                            type="submit"
                            disabled={submitting}
                            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-[var(--re-brand)] text-white font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 mt-1"
                        >
                            {submitting ? 'Submitting...' : ctaText}
                            {!submitting && <ArrowRight className="h-4 w-4" />}
                        </button>
                        <p className="text-[10px] text-center text-[var(--re-text-disabled)]">
                            No spam. Your data is encrypted and never shared.
                        </p>
                    </form>
                </div>
            )}

            {step === 'enrich' && (
                <div className="p-6 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                    <div className="text-center mb-5">
                        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-re-brand-muted text-re-brand text-xs font-bold mb-3">
                            <Check className="h-3 w-3" /> Results Unlocked
                        </div>
                        <h3 className="text-lg font-bold text-[var(--re-text-primary)]">Help us personalize your report</h3>
                        <p className="text-sm text-[var(--re-text-muted)] mt-1">
                            Optional — these details help our founder tailor recommendations to your situation.
                        </p>
                    </div>
                    <form onSubmit={handleEnrichSubmit} className="space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <select name="facilityCount" className={selectClass}>
                                <option value="">Number of Facilities</option>
                                <option value="1">1 facility</option>
                                <option value="2-5">2–5 facilities</option>
                                <option value="6-20">6–20 facilities</option>
                                <option value="20+">20+ facilities</option>
                            </select>
                            <select name="annualRevenue" className={selectClass}>
                                <option value="">Annual Revenue Range</option>
                                <option value="under-1m">Under $1M</option>
                                <option value="1m-5m">$1M – $5M</option>
                                <option value="5m-25m">$5M – $25M</option>
                                <option value="25m-100m">$25M – $100M</option>
                                <option value="100m+">$100M+</option>
                            </select>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <select name="currentSystem" className={selectClass}>
                                <option value="">Current Traceability System</option>
                                <option value="spreadsheets">Spreadsheets / Paper</option>
                                <option value="wherefour">Wherefour</option>
                                <option value="foodready">FoodReady</option>
                                <option value="craftybase">Craftybase</option>
                                <option value="mrpeasy">MRPeasy</option>                                <option value="sap">SAP / Oracle</option>
                                <option value="other-erp">Other ERP</option>
                                <option value="none">Nothing yet</option>
                            </select>
                            <select name="biggestRetailer" className={selectClass}>
                                <option value="">Biggest Retailer Customer</option>
                                <option value="walmart">Walmart</option>
                                <option value="kroger">Kroger</option>
                                <option value="costco">Costco</option>
                                <option value="whole-foods">Whole Foods / Amazon</option>
                                <option value="target">Target</option>
                                <option value="publix">Publix</option>
                                <option value="aldi">ALDI</option>
                                <option value="other">Other</option>
                                <option value="none">No retail — B2B only</option>
                            </select>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <select name="complianceDeadline" className={selectClass}>
                                <option value="">FSMA 204 Deadline Awareness</option>
                                <option value="aware-on-track">Aware — working on it</option>
                                <option value="aware-behind">Aware — behind schedule</option>
                                <option value="unaware">Not sure about timeline</option>
                                <option value="not-applicable">Don&apos;t think it applies to us</option>
                            </select>
                            <select name="recentFdaInspection" className={selectClass}>
                                <option value="">Recent FDA Inspection?</option>
                                <option value="yes-12mo">Yes — within 12 months</option>
                                <option value="yes-older">Yes — more than 12 months ago</option>
                                <option value="no">No</option>
                                <option value="unsure">Not sure</option>
                            </select>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <input name="phone" type="tel" placeholder="Phone (optional)" className={inputClass} />
                            <input name="productCategories" placeholder="Main product types (e.g. leafy greens, cheese)" className={inputClass} />
                        </div>
                        <div className="flex gap-3 mt-2">
                            <button
                                type="submit"
                                disabled={submitting}
                                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-[var(--re-brand)] text-white font-semibold text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                            >
                                {submitting ? 'Saving...' : 'Submit & View Results'}
                                {!submitting && <Sparkles className="h-4 w-4" />}
                            </button>
                            <button
                                type="button"
                                onClick={skipEnrichment}
                                className="px-5 py-3 rounded-xl border border-[var(--re-surface-border)] text-sm text-[var(--re-text-muted)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-colors"
                            >
                                Skip
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
}