'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import type { MouseEvent } from 'react';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { ArrowRight, Loader2 } from 'lucide-react';

// Map frontend tier IDs to backend plan IDs
const PLAN_ID_MAP: Record<string, string> = {
    base: 'growth',
    standard: 'scale',
};

interface PricingCheckoutButtonProps {
    tierId: string;
    label: string;
    highlighted?: boolean;
    billingPeriod?: 'monthly' | 'annual';
    style?: React.CSSProperties;
}

export function PricingCheckoutButton({
    tierId,
    label,
    highlighted = false,
    billingPeriod = 'annual',
    style,
}: PricingCheckoutButtonProps) {
    const router = useRouter();
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const signupHref = `/signup?plan=${encodeURIComponent(tierId)}&billing=${billingPeriod}`;

    const handleCheckout = async (event: MouseEvent<HTMLAnchorElement>) => {
        event.preventDefault();

        // Premium has the same no-JS signup fallback, but no Stripe checkout yet.
        if (tierId === 'premium') {
            router.push(signupHref);
            return;
        }

        const backendPlanId = PLAN_ID_MAP[tierId] || tierId;

        setIsLoading(true);
        setError(null);

        try {
            const response = await fetchWithCsrf('/api/billing/checkout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plan_id: backendPlanId,
                    billing_period: billingPeriod,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                setError('Stripe checkout was unavailable. You can continue to signup; billing happens from inside the app.');
                return;
            }

            // Redirect to Stripe Checkout
            if (data.checkout_url) {
                window.location.href = data.checkout_url;
            } else {
                setError('Stripe checkout was unavailable. You can continue to signup; billing happens from inside the app.');
            }
        } catch {
            setError('Stripe checkout was unavailable. You can continue to signup; billing happens from inside the app.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div>
            {/* `highlighted` is what makes exactly one card in the tier grid carry
                the primary action; the other two are secondary (SPEC §4). */}
            <Button
                asChild
                variant={highlighted ? 'primary' : 'secondary'}
                size="lg"
                className="mb-5 mt-6 w-full"
                style={style}
            >
                <Link
                    href={signupHref}
                    onClick={handleCheckout}
                    aria-disabled={isLoading}
                    data-cta-target={signupHref}
                    className="no-underline"
                >
                    {isLoading ? (
                        <>
                            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
                            Redirecting to checkout...
                        </>
                    ) : (
                        <>
                            {label}
                            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        </>
                    )}
                </Link>
            </Button>
            {error && (
                <>
                    <p className="mt-2 text-center text-small text-re-danger" role="alert">
                        {error}
                    </p>
                    <button
                        type="button"
                        onClick={() => router.push(signupHref)}
                        className="mt-2 w-full text-center text-small text-re-text-secondary underline underline-offset-[3px] transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        Continue to signup
                    </button>
                </>
            )}
        </div>
    );
}
