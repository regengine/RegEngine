'use client';

import { useState } from 'react';
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

    const handleCheckout = async () => {
        // Premium tier → contact sales
        if (tierId === 'premium') {
            router.push('/contact?plan=premium');
            return;
        }

        const backendPlanId = PLAN_ID_MAP[tierId] || tierId;

        setIsLoading(true);
        setError(null);

        try {
            const response = await fetch('/api/billing/checkout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plan_id: backendPlanId,
                    billing_period: billingPeriod,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                // If Stripe isn't configured, fall through to signup
                if (response.status === 502 || response.status === 500) {
                    router.push(`/signup?plan=${tierId}`);
                    return;
                }
                setError(data.error || 'Checkout failed');
                return;
            }

            // Redirect to Stripe Checkout
            if (data.checkout_url) {
                window.location.href = data.checkout_url;
            } else {
                // Fallback: go to signup with plan context
                router.push(`/signup?plan=${tierId}`);
            }
        } catch {
            // Network error or Stripe not configured — fall through to signup
            router.push(`/signup?plan=${tierId}`);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div>
            <Button
                onClick={handleCheckout}
                disabled={isLoading}
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
            </Button>
            {error && (
                <p style={{ color: '#ef4444', fontSize: '12px', marginTop: '8px', textAlign: 'center' }}>
                    {error}
                </p>
            )}
        </div>
    );
}
