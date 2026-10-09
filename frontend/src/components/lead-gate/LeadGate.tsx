'use client';

import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, Lock, Sparkles } from 'lucide-react';
import { submitAssessment, type AssessmentFormData } from '@/app/actions/submit-assessment';
import { useAuth } from '@/lib/auth-context';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { fieldControlClasses } from '@/components/ui/field-control';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

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
/** Native <select> shares the Input recipe (SPEC §4) — the form posts FormData,
 *  so these stay real form controls rather than Radix listboxes. */
const selectClass = cn(fieldControlClasses, 'pr-2');

/* ────────────────────────────────────────────────────────────── */
/*  Component                                                    */
/* ────────────────────────────────────────────────────────────── */
export function LeadGate({
    source,
    headline = 'Unlock Your Full Results',
    subheadline = 'The founder personally reviews every submission — typically within one business day.',
    ctaText = 'Unlock Full Results',
    toolContext,
    teaser,
    children,
    onUnlock,
}: LeadGateProps) {
    const { user } = useAuth();

    // Authenticated users bypass the lead gate — they already provided their info at signup
    const authenticatedBypass = !!user;

    const [step, setStep] = useState<'gate' | 'enrich' | 'done'>(authenticatedBypass ? 'done' : 'gate');
    const [submitting, setSubmitting] = useState(false);
    // Synchronous double-submit guard. `submitting` state alone is not
    // enough: state updates flush on re-render, so two submit events fired
    // before the next render would both pass a state check and post twice.
    const submittingRef = useRef(false);
    const [error, setError] = useState<string | null>(null);
    const [gateData, setGateData] = useState<Partial<AssessmentFormData>>({});
    // Capture UTM params on mount
    const [utmParams, setUtmParams] = useState<Record<string, string>>({});
    // window.location is browser-only, so UTM capture cannot happen during
    // render without breaking SSR.
    useEffect(() => {
        if (typeof window === 'undefined') return;
        const params = new URLSearchParams(window.location.search);
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setUtmParams({
            utmSource: params.get('utm_source') || '',
            utmMedium: params.get('utm_medium') || '',
            utmCampaign: params.get('utm_campaign') || '',
            referrer: document.referrer || '',
        });
    }, []);

    // Check localStorage for returning leads (non-PII flag only — no email stored)
    // localStorage is browser-only; this also performs a one-time migration of
    // the legacy plain-text key, which must not run during render.
    useEffect(() => {
        if (typeof window === 'undefined') return;
        // Migrate: clear legacy plain-text email if present
        if (localStorage.getItem('re_lead_email')) {
            localStorage.removeItem('re_lead_email');
            localStorage.setItem('re_lead_captured', '1');
        }
        const captured = localStorage.getItem('re_lead_captured');
        if (captured) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setStep('done');
            onUnlock?.();
        }
    }, [onUnlock]);

    /* ── Step 1: Gate form ── */
    const handleGateSubmit = useCallback(
        async (e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            if (submittingRef.current) return;
            submittingRef.current = true;
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

            try {
                const result = await submitAssessment(data);

                if (!result.success) {
                    setError(result.error || 'Something went wrong.');
                    return;
                }

                // Persist a non-PII flag so returning visitors bypass the gate
                try { localStorage.setItem('re_lead_captured', '1'); } catch {}
                setGateData(data);
                setStep('enrich');
            } finally {
                submittingRef.current = false;
                setSubmitting(false);
            }
        },
        [source, toolContext, utmParams],
    );
    /* ── Step 2: Enrichment form (optional, skippable) ── */
    const handleEnrichSubmit = useCallback(
        async (e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            if (submittingRef.current) return;
            submittingRef.current = true;
            setSubmitting(true);

            try {
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
                setStep('done');
                onUnlock?.();
            } finally {
                submittingRef.current = false;
                setSubmitting(false);
            }
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
            {/* Show teaser (partial results, held back behind the gate) */}
            {teaser && (
                <div className="relative">
                    {teaser}
                    <div
                        className="pointer-events-none absolute inset-0 rounded-lg bg-re-surface-base/60"
                        aria-hidden="true"
                    />
                </div>
            )}

            {step === 'gate' && (
                <Card padding="spacious">
                    <div className="mb-5 text-center">
                        <Badge tone="brand" className="mb-3">
                            <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> Free — No Credit Card
                        </Badge>
                        <h3 className="text-subheading text-re-text-primary">{headline}</h3>
                        <p className="mt-1 text-ui text-re-text-secondary">{subheadline}</p>
                    </div>
                    <form onSubmit={handleGateSubmit} className="space-y-3">
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <Field label="Full Name" htmlFor="lead-gate-name" required>
                                <Input name="name" size="lg" required placeholder="Full Name" />
                            </Field>
                            <Field label="Work Email" htmlFor="lead-gate-email" required>
                                <Input name="email" type="email" size="lg" required placeholder="Work Email" />
                            </Field>
                        </div>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <Field label="Company Name" htmlFor="lead-gate-company" required>
                                <Input name="company" size="lg" required placeholder="Company Name" />
                            </Field>
                            <Field label="Your Role" htmlFor="lead-gate-role" required>
                                <select id="lead-gate-role" name="role" required className={cn(selectClass, 'h-11')}>
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
                            </Field>
                        </div>

                        {error && (
                            <Callout tone="danger" role="alert">
                                {error}
                            </Callout>
                        )}
                        <Button
                            type="submit"
                            size="lg"
                            className="mt-1 w-full"
                            disabled={submitting}
                            trailingIcon={submitting ? undefined : <ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                        >
                            {submitting ? 'Submitting...' : ctaText}
                        </Button>
                        <p className="text-center text-small text-re-text-muted">
                            We'll only use your details for this tool.
                        </p>
                    </form>
                </Card>
            )}

            {step === 'enrich' && (
                <Card padding="spacious">
                    <div className="mb-5 text-center">
                        <Badge tone="success" className="mb-3">
                            <Check className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> Results Unlocked
                        </Badge>
                        <h3 className="text-subheading text-re-text-primary">Help us personalize your report</h3>
                        <p className="mt-1 text-ui text-re-text-secondary">
                            Optional — these details help our founder tailor recommendations to your situation.
                        </p>
                    </div>
                    <form onSubmit={handleEnrichSubmit} className="space-y-3">
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <Field label="Number of Facilities" htmlFor="lead-gate-facility-count">
                                <select id="lead-gate-facility-count" name="facilityCount" className={selectClass}>
                                    <option value="">Number of Facilities</option>
                                    <option value="1">1 facility</option>
                                    <option value="2-5">2–5 facilities</option>
                                    <option value="6-20">6–20 facilities</option>
                                    <option value="20+">20+ facilities</option>
                                </select>
                            </Field>
                            <Field label="Annual Revenue Range" htmlFor="lead-gate-annual-revenue">
                                <select id="lead-gate-annual-revenue" name="annualRevenue" className={selectClass}>
                                    <option value="">Annual Revenue Range</option>
                                    <option value="under-1m">Under $1M</option>
                                    <option value="1m-5m">$1M – $5M</option>
                                    <option value="5m-25m">$5M – $25M</option>
                                    <option value="25m-100m">$25M – $100M</option>
                                    <option value="100m+">$100M+</option>
                                </select>
                            </Field>
                        </div>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <Field label="Current Traceability System" htmlFor="lead-gate-current-system">
                                <select id="lead-gate-current-system" name="currentSystem" className={selectClass}>
                                    <option value="">Current Traceability System</option>
                                    <option value="spreadsheets">Spreadsheets / Paper</option>
                                    <option value="wherefour">Wherefour</option>
                                    <option value="foodready">FoodReady</option>
                                    <option value="craftybase">Craftybase</option>
                                    <option value="mrpeasy">MRPeasy</option>                                <option value="sap">SAP / Oracle</option>
                                    <option value="other-erp">Other ERP</option>
                                    <option value="none">Nothing yet</option>
                                </select>
                            </Field>
                            <Field label="Biggest Retailer Customer" htmlFor="lead-gate-biggest-retailer">
                                <select id="lead-gate-biggest-retailer" name="biggestRetailer" className={selectClass}>
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
                            </Field>
                        </div>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <Field label="FSMA 204 Deadline Awareness" htmlFor="lead-gate-compliance-deadline">
                                <select id="lead-gate-compliance-deadline" name="complianceDeadline" className={selectClass}>
                                    <option value="">FSMA 204 Deadline Awareness</option>
                                    <option value="aware-on-track">Aware — working on it</option>
                                    <option value="aware-behind">Aware — behind schedule</option>
                                    <option value="unaware">Not sure about timeline</option>
                                    <option value="not-applicable">Don&apos;t think it applies to us</option>
                                </select>
                            </Field>
                            <Field label="Recent FDA Inspection?" htmlFor="lead-gate-recent-fda-inspection">
                                <select id="lead-gate-recent-fda-inspection" name="recentFdaInspection" className={selectClass}>
                                    <option value="">Recent FDA Inspection?</option>
                                    <option value="yes-12mo">Yes — within 12 months</option>
                                    <option value="yes-older">Yes — more than 12 months ago</option>
                                    <option value="no">No</option>
                                    <option value="unsure">Not sure</option>
                                </select>
                            </Field>
                        </div>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <Field label="Phone (optional)" htmlFor="lead-gate-phone">
                                <Input name="phone" type="tel" placeholder="Phone (optional)" />
                            </Field>
                            <Field label="Main product types (e.g. leafy greens, cheese)" htmlFor="lead-gate-product-categories">
                                <Input name="productCategories" placeholder="Main product types (e.g. leafy greens, cheese)" />
                            </Field>
                        </div>
                        <div className="mt-2 flex gap-3">
                            <Button
                                type="submit"
                                size="lg"
                                className="flex-1"
                                disabled={submitting}
                                trailingIcon={submitting ? undefined : <Sparkles strokeWidth={1.75} aria-hidden="true" />}
                            >
                                {submitting ? 'Saving...' : 'Submit & View Results'}
                            </Button>
                            <Button
                                type="button"
                                variant="secondary"
                                size="lg"
                                onClick={skipEnrichment}
                            >
                                Skip
                            </Button>
                        </div>
                    </form>
                </Card>
            )}
        </div>
    );
}
