'use client';

/**
 * CheckoutWizard — 3-step premium checkout flow
 *
 * Steps:
 * 1. Plan — Choose pricing tier with billing cycle toggle
 * 2. Payment — Credit code + Stripe Checkout redirect
 * 3. Activation — Success confirmation with onboarding CTA
 *
 * Dark glassmorphism design with animated step transitions.
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams, useRouter } from 'next/navigation';
import {
    ArrowRight,
    ArrowLeft,
    CheckCircle,
    CreditCard,
    Sparkles,
    Shield,
    Lock,
    Rocket,
    Zap,
    ExternalLink,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PlanCard, type PlanFeature } from '@/components/billing/PlanCard';
import { CreditRedemption } from '@/components/billing/CreditRedemption';
import { useCreateCheckout, usePricingTiers, type PricingTier, type RedeemResult } from '@/hooks/use-billing';

// ── Constants ─────────────────────────────────────────────────────

type WizardStep = 'plan' | 'payment' | 'activation';

const FALLBACK_PLANS = [
    {
        id: 'growth', name: 'Growth', description: 'Under $50M annual revenue',
        monthlyPrice: 1299, annualPrice: 1079, cteLimit: '10,000', highlighted: false,
        features: [
            { text: 'Up to 3 locations', included: true },
            { text: 'Supplier onboarding + FTL scoping', included: true },
            { text: 'CSV upload + API ingestion', included: true },
            { text: 'Compliance scoring + FDA-ready export', included: true },
            { text: 'Recall simulation + drill workflows', included: true },
            { text: 'Email support', included: true },
        ] as PlanFeature[],
    },
    {
        id: 'scale', name: 'Scale', description: '$50M–$200M annual revenue',
        monthlyPrice: 2499, annualPrice: 2079, cteLimit: '100,000', highlighted: true,
        features: [
            { text: 'Everything in Growth', included: true },
            { text: 'Up to 10 locations', included: true },
            { text: 'Expanded API + webhook limits', included: true },
            { text: 'Retailer-specific readiness benchmarks', included: true },
            { text: 'Priority onboarding support', included: true },
            { text: 'Priority support', included: true },
        ] as PlanFeature[],
    },
    {
        id: 'enterprise', name: 'Enterprise', description: 'Full supply chain with SSO & dedicated support',
        monthlyPrice: null, annualPrice: null, cteLimit: 'Unlimited', highlighted: false,
        features: [
            { text: 'Everything in Scale', included: true },
            { text: 'Unlimited facilities', included: true },
            { text: 'SSO / SAML integration', included: true },
            { text: 'Custom recall playbooks', included: true },
            { text: 'Dedicated account manager', included: true },
            { text: '99.9% SLA', included: true },
        ] as PlanFeature[],
    },
];

const stepsMeta: { id: WizardStep; title: string; number: number }[] = [
    { id: 'plan', title: 'Select Plan', number: 1 },
    { id: 'payment', title: 'Payment', number: 2 },
    { id: 'activation', title: 'Activation', number: 3 },
];

// ── Animation Variants ────────────────────────────────────────────

const cardVariants = {
    enter: { opacity: 0, x: 30, scale: 0.98 },
    center: { opacity: 1, x: 0, scale: 1, transition: { duration: 0.35, ease: [0.4, 0, 0.2, 1] } },
    exit: { opacity: 0, x: -30, scale: 0.98, transition: { duration: 0.25 } },
};

const staggerChildren = {
    animate: { transition: { staggerChildren: 0.06 } },
};

const fadeUp = {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

// ── Component ─────────────────────────────────────────────────────

export function CheckoutWizard() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const createCheckout = useCreateCheckout();
    const { data: tiersData } = usePricingTiers();
    const billingParam = searchParams?.get('billing');

    // Use dynamic pricing from API if available, otherwise fall back to hardcoded plans
    const PLANS = tiersData?.tiers?.length
        ? tiersData.tiers.map((t: PricingTier) => ({
            id: t.id,
            name: t.name,
            description: t.description,
            monthlyPrice: t.monthly_price,
            annualPrice: t.annual_price,
            cteLimit: t.cte_limit,
            highlighted: t.highlighted,
            features: t.features as PlanFeature[],
        }))
        : FALLBACK_PLANS;

    const [currentStep, setCurrentStep] = useState<WizardStep>('plan');
    const [selectedPlan, setSelectedPlan] = useState<string>(searchParams?.get('plan') || 'growth');
    const [isAnnual, setIsAnnual] = useState(billingParam !== 'monthly');
    const [appliedCredits, setAppliedCredits] = useState(0);
    const [checkoutError, setCheckoutError] = useState<string | null>(null);

    // Pre-select plan from URL param
    useEffect(() => {
        const planParam = searchParams?.get('plan');
        if (planParam && PLANS.find((p) => p.id === planParam)) {
            setSelectedPlan(planParam);
        }
    }, [searchParams, PLANS]);

    useEffect(() => {
        if (billingParam === 'monthly') {
            setIsAnnual(false);
        } else if (billingParam === 'annual') {
            setIsAnnual(true);
        }
    }, [billingParam]);

    const currentStepIndex = stepsMeta.findIndex((s) => s.id === currentStep);

    const handleCreditApplied = (result: RedeemResult) => {
        if (result.success) {
            setAppliedCredits((prev) => prev + result.amount_cents);
        }
    };

    const handleCheckout = async () => {
        setCheckoutError(null);
        try {
            const result = await createCheckout.mutateAsync({
                tier_id: selectedPlan,
                billing_cycle: isAnnual ? 'annual' : 'monthly',
            });
            if (result.checkout_url) {
                window.location.assign(result.checkout_url);
                return;
            }

            throw new Error('Missing checkout URL from billing API');
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Failed to create checkout session';
            setCheckoutError(message);
        }
    };

    const selectedPlanData = PLANS.find((p) => p.id === selectedPlan);
    const planPrice = selectedPlanData
        ? isAnnual
            ? selectedPlanData.annualPrice
            : selectedPlanData.monthlyPrice
        : 0;

    return (
        <div className="max-w-3xl mx-auto relative z-10">
            {/* ─── Background Orbs ─── */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
                <div
                    className="absolute -top-40 -right-40 w-96 h-96 rounded-full opacity-[0.03]"
                    style={{ background: 'radial-gradient(circle, var(--re-brand) 0%, transparent 70%)' }}
                />
                <div
                    className="absolute -bottom-60 -left-40 w-[500px] h-[500px] rounded-full opacity-[0.02]"
                    style={{ background: 'radial-gradient(circle, var(--re-info) 0%, transparent 70%)' }}
                />
            </div>

            {/* ─── Progress Indicator ─── */}
            <div className="mb-8 pt-4">
                <div className="flex items-center justify-between mb-3">
                    {stepsMeta.map((step, index) => (
                        <div key={step.id} className="flex items-center">
                            <motion.div
                                animate={{
                                    scale: index === currentStepIndex ? 1.1 : 1,
                                    boxShadow:
                                        index === currentStepIndex
                                            ? '0 0 20px rgba(16, 185, 129, 0.3)'
                                            : '0 0 0px transparent',
                                }}
                                transition={{ duration: 0.3 }}
                                className={`
                  w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-colors duration-300
                  ${index < currentStepIndex
                                        ? 'bg-re-brand text-[var(--re-surface-base)]'
                                        : index === currentStepIndex
                                            ? 'bg-re-brand text-[var(--re-surface-base)] ring-4 ring-re-brand/20'
                                            : 'bg-[var(--re-surface-elevated)] text-[var(--re-text-muted)]'
                                    }
                `}
                            >
                                {index < currentStepIndex ? (
                                    <CheckCircle className="w-4 h-4" />
                                ) : (
                                    step.number
                                )}
                            </motion.div>
                            {index < stepsMeta.length - 1 && (
                                <div
                                    className="w-10 sm:w-16 h-1 mx-1 rounded-full overflow-hidden bg-re-surface-elevated"
                                >
                                    <motion.div
                                        className="h-full rounded-full bg-re-brand"
                                        initial={{ width: '0%' }}
                                        animate={{ width: index < currentStepIndex ? '100%' : '0%' }}
                                        transition={{ duration: 0.5, ease: 'easeOut' }}
                                    />
                                </div>
                            )}
                        </div>
                    ))}
                </div>
                <p className="text-center text-sm text-re-text-muted">
                    Step {currentStepIndex + 1} of {stepsMeta.length}:{' '}
                    <span className="text-re-text-secondary">
                        {stepsMeta[currentStepIndex]?.title}
                    </span>
                </p>
            </div>

            {/* ─── Step Content ─── */}
            <AnimatePresence mode="wait">
                {/* ═══════════ Step 1: Plan Selection ═══════════ */}
                {currentStep === 'plan' && (
                    <motion.div key="plan" variants={cardVariants} initial="enter" animate="center" exit="exit">
                        <Card
                            className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card"
                        >
                            <div
                                className="h-1"
                                style={{ background: 'linear-gradient(90deg, var(--re-info), var(--re-brand))' }}
                            />
                            <CardHeader>
                                <CardTitle className="text-re-text-primary">Choose Your Plan</CardTitle>
                                <CardDescription className="text-re-text-tertiary">
                                    Growth and Scale start with a 14-day trial. Enterprise is handled separately.
                                </CardDescription>

                                {/* Billing toggle */}
                                <div className="flex items-center justify-center gap-3 mt-4">
                                    <span
                                        className="text-sm font-medium"
                                        style={{ color: !isAnnual ? 'var(--re-text-primary)' : 'var(--re-text-muted)' }}
                                    >
                                        Monthly
                                    </span>
                                    <button
                                        onClick={() => setIsAnnual(!isAnnual)}
                                        className="relative w-12 h-6 rounded-full transition-colors duration-200"
                                        style={{ background: isAnnual ? 'var(--re-brand)' : 'var(--re-surface-elevated)' }}
                                        aria-label="Toggle annual billing"
                                    >
                                        <motion.div
                                            className="absolute top-1 w-4 h-4 rounded-full bg-white"
                                            animate={{ left: isAnnual ? 28 : 4 }}
                                            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                                        />
                                    </button>
                                    <span
                                        className="text-sm font-medium"
                                        style={{ color: isAnnual ? 'var(--re-text-primary)' : 'var(--re-text-muted)' }}
                                    >
                                        Annual
                                    </span>
                                    {isAnnual && (
                                        <Badge
                                            className="text-xs"
                                            style={{ background: 'var(--re-success-muted)', color: 'var(--re-success)' }}
                                        >
                                            Save ~17%
                                        </Badge>
                                    )}
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="grid gap-4">
                                    {PLANS.map((plan) => (
                                        <PlanCard
                                            key={plan.id}
                                            id={plan.id}
                                            name={plan.name}
                                            description={plan.description}
                                            monthlyPrice={plan.monthlyPrice}
                                            annualPrice={plan.annualPrice}
                                            cteLimit={plan.cteLimit}
                                            features={plan.features}
                                            highlighted={plan.highlighted}
                                            isAnnual={isAnnual}
                                            isSelected={selectedPlan === plan.id}
                                            onSelect={setSelectedPlan}
                                            appliedCredit={appliedCredits}
                                        />
                                    ))}
                                </div>

                                {/* Enterprise CTA */}
                                <div
                                    className="mt-4 p-4 rounded-xl border text-center"
                                    style={{
                                        borderColor: 'var(--re-border-default)',
                                        background: 'var(--re-surface-elevated)',
                                    }}
                                >
                                    <p className="text-sm text-re-text-muted">
                                        Need unlimited CTEs, custom contracts, or on-premise deployment?
                                    </p>
                                    <a
                                        href="mailto:sales@regengine.co"
                                        className="inline-flex items-center gap-1 mt-1 text-sm font-medium hover:underline text-re-brand"
                                    >
                                        Contact Enterprise Sales <ExternalLink className="w-3.5 h-3.5" />
                                    </a>
                                </div>

                                <div className="flex gap-3 mt-6">
                                    <Button
                                        variant="outline"
                                        onClick={() => router.push('/pricing')}
                                        className="border-[var(--re-border-default)] text-re-text-secondary"
                                    >
                                        <ArrowLeft className="mr-2 w-4 h-4" />
                                        Back
                                    </Button>
                                    <Button
                                        className="flex-1 font-semibold bg-re-brand text-re-surface-base"
                                        onClick={() => setCurrentStep('payment')}
                                    >
                                        Continue to Payment
                                        <ArrowRight className="ml-2 w-4 h-4" />
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* ═══════════ Step 2: Payment ═══════════ */}
                {currentStep === 'payment' && (
                    <motion.div key="payment" variants={cardVariants} initial="enter" animate="center" exit="exit">
                        <Card
                            className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card"
                        >
                            <div
                                className="h-1"
                                style={{ background: 'linear-gradient(90deg, var(--re-brand-light), var(--re-brand))' }}
                            />
                            <CardHeader>
                                <CardTitle className="text-re-text-primary">
                                    <div className="flex items-center gap-2">
                                        <CreditCard className="w-5 h-5 text-re-brand" />
                                        Complete Your Purchase
                                    </div>
                                </CardTitle>
                                <CardDescription className="text-re-text-tertiary">
                                    Secure payment processing powered by Stripe
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {/* Order summary */}
                                <div
                                    className="p-5 rounded-xl border"
                                    style={{
                                        borderColor: 'var(--re-border-default)',
                                        background: 'var(--re-surface-elevated)',
                                    }}
                                >
                                    <h4 className="font-semibold mb-3 text-re-text-primary">
                                        Order Summary
                                    </h4>
                                    <div className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span className="text-re-text-secondary">
                                                {selectedPlanData?.name} Plan ({isAnnual ? 'Annual' : 'Monthly'})
                                            </span>
                                            <span className="font-semibold text-re-text-primary">
                                                ${planPrice}/mo
                                            </span>
                                        </div>
                                        {isAnnual && (
                                            <div className="flex justify-between">
                                                <span className="text-re-text-muted">Billed annually</span>
                                                <span className="text-re-text-muted">
                                                    ${(planPrice ?? 0) * 12}/yr
                                                </span>
                                            </div>
                                        )}
                                        {appliedCredits > 0 && (
                                            <div className="flex justify-between">
                                                <span className="text-re-success">Credits applied</span>
                                                <span className="font-semibold text-re-success">
                                                    -${(appliedCredits / 100).toFixed(2)}
                                                </span>
                                            </div>
                                        )}
                                        <div
                                            className="border-t pt-2 mt-2 flex justify-between"
                                            style={{ borderColor: 'var(--re-border-default)' }}
                                        >
                                            <span className="font-semibold text-re-text-primary">
                                                Today&apos;s total
                                            </span>
                                            <span className="font-bold text-lg text-re-brand">
                                                $0.00
                                            </span>
                                        </div>
                                        <p className="text-xs text-center mt-1 text-re-text-muted">
                                            14-day trial — you won&apos;t be charged until the trial ends
                                        </p>
                                    </div>
                                </div>

                                {/* Credit code input */}
                                <CreditRedemption compact onCreditApplied={handleCreditApplied} />

                                {checkoutError && (
                                    <div
                                        className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200"
                                        role="alert"
                                        aria-live="polite"
                                    >
                                        {checkoutError}
                                    </div>
                                )}

                                {/* Security badges */}
                                <div className="flex items-center justify-center gap-4 py-2">
                                    {[
                                        { icon: Lock, label: 'SSL Encrypted' },
                                        { icon: Shield, label: 'PCI Compliant' },
                                        { icon: CreditCard, label: 'Stripe Secure' },
                                    ].map((badge) => (
                                        <div key={badge.label} className="flex items-center gap-1.5 text-xs text-re-text-muted">
                                            <badge.icon className="w-3.5 h-3.5" />
                                            {badge.label}
                                        </div>
                                    ))}
                                </div>

                                <div className="flex gap-3">
                                    <Button
                                        variant="outline"
                                        onClick={() => setCurrentStep('plan')}
                                        className="border-[var(--re-border-default)] text-re-text-secondary"
                                    >
                                        <ArrowLeft className="mr-2 w-4 h-4" />
                                        Back
                                    </Button>
                                    <Button
                                        className="flex-1 font-semibold h-12 text-base bg-re-brand text-re-surface-base"
                                        onClick={handleCheckout}
                                        disabled={createCheckout.isPending}
                                    >
                                        {createCheckout.isPending ? (
                                            <>
                                                <span className="mr-2 animate-spin">⟳</span>
                                                Processing...
                                            </>
                                        ) : (
                                            <>
                                                Start 14-Day Trial
                                                <ArrowRight className="ml-2 w-4 h-4" />
                                            </>
                                        )}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* ═══════════ Step 3: Activation ═══════════ */}
                {currentStep === 'activation' && (
                    <motion.div key="activation" variants={cardVariants} initial="enter" animate="center" exit="exit">
                        <Card
                            className="overflow-hidden border-[var(--re-border-default)] bg-re-surface-card"
                        >
                            <div
                                className="h-1"
                                style={{ background: 'linear-gradient(90deg, var(--re-brand), var(--re-success))' }}
                            />
                            <CardHeader className="text-center pb-2">
                                <motion.div
                                    initial={{ scale: 0 }}
                                    animate={{ scale: 1 }}
                                    transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
                                    className="mx-auto mb-4 p-5 rounded-2xl"
                                    style={{ background: 'rgba(16, 185, 129, 0.1)', boxShadow: '0 0 40px rgba(16,185,129,0.2)' }}
                                >
                                    <Sparkles className="w-12 h-12 text-re-brand" />
                                </motion.div>
                                <CardTitle className="text-3xl font-bold text-re-text-primary">
                                    You&apos;re All Set!
                                </CardTitle>
                                <CardDescription className="text-base text-re-text-tertiary">
                                    Your {selectedPlanData?.name} trial workspace is now active
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {/* Activation stats */}
                                <motion.div
                                    className="grid grid-cols-2 gap-3"
                                    variants={staggerChildren}
                                    initial="initial"
                                    animate="animate"
                                >
                                    {[
                                        { icon: Shield, label: 'Plan', value: selectedPlanData?.name || 'Growth', color: 'var(--re-brand)' },
                                        { icon: Zap, label: 'CTE Limit', value: selectedPlanData?.cteLimit || '100,000', color: 'var(--re-info)' },
                                        { icon: CreditCard, label: 'Billing', value: isAnnual ? 'Annual' : 'Monthly', color: 'var(--re-success)' },
                                        { icon: Rocket, label: 'Trial', value: '14-day trial', color: 'var(--re-warning)' },
                                    ].map((stat) => (
                                        <motion.div
                                            key={stat.label}
                                            variants={fadeUp}
                                            className="flex items-center gap-3 p-3 rounded-lg border border-[var(--re-border-default)] bg-re-surface-elevated"
                                        >
                                            <div className="p-2 rounded-lg" style={{ background: `${stat.color}15` }}>
                                                <stat.icon className="w-4 h-4" style={{ color: stat.color }} />
                                            </div>
                                            <div>
                                                <p className="text-xs text-re-text-muted">{stat.label}</p>
                                                <p className="font-semibold text-sm text-re-text-primary">{stat.value}</p>
                                            </div>
                                        </motion.div>
                                    ))}
                                </motion.div>

                                {/* Next steps */}
                                <div
                                    className="p-4 rounded-xl border border-re-border bg-re-surface-elevated"
                                >
                                    <h4 className="font-semibold mb-3 flex items-center gap-2 text-re-text-primary">
                                        <Rocket className="w-4 h-4 text-re-brand" />
                                        Next Steps
                                    </h4>
                                    <ul className="space-y-2">
                                        {[
                                            'Set up your API credentials',
                                            'Ingest your first compliance document',
                                            'Explore the dashboard and gap analysis',
                                            'Invite your team members',
                                        ].map((step, i) => (
                                            <li key={i} className="flex items-center gap-2 text-sm">
                                                <CheckCircle className="w-4 h-4 shrink-0 text-re-text-muted" />
                                                <span className="text-re-text-secondary">{step}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>

                                <div className="flex gap-3">
                                    <Button
                                        className="flex-1 font-semibold h-12 text-base bg-re-brand text-re-surface-base"
                                        onClick={() => router.push('/onboarding')}
                                    >
                                        <Rocket className="mr-2 w-4 h-4" />
                                        Start Onboarding
                                    </Button>
                                    <Button
                                        variant="outline"
                                        onClick={() => router.push('/dashboard')}
                                        className="border-[var(--re-border-default)] text-re-text-secondary"
                                    >
                                        Go to Dashboard
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
