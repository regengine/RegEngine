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
                router.push(signupHref);
                return;
            }

            // Redirect to Stripe Checkout
            if (data.checkout_url) {
                window.location.href = data.checkout_url;
            } else {
                // Fallback: go to signup with plan context
                router.push(signupHref);
            }
        } catch {
            // Network error or Stripe not configured — fall through to signup
            router.push(signupHref);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div>
            <Button
                asChild
                style={{
                    width: '100%',
                    marginTop: '24px',
                    fontWeight: 600,
                    borderRadius: '10px',
                    padding: '12px 20px',
                    transition: 'all 0.2s',
                    ...style,
                }}
            >
                <Link
                    href={signupHref}
                    onClick={handleCheckout}
                    aria-disabled={isLoading}
                    data-cta-target={signupHref}
                >
                    {isLoading ? (
                        <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Redirecting to checkout...
                        </>
                    ) : (
                        <>
                            {label}
                            <ArrowRight className="ml-2 w-4 h-4" />
                        </>
                    )}
                </Link>
            </Button>
            {error && (
                <p className="text-red-500 text-xs mt-2 text-center">
                    {error}
                </p>
            )}
        </div>
    );
}
