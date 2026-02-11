'use client';

/**
 * /checkout — Enterprise Checkout Page
 *
 * Wraps the CheckoutWizard component and reads the ?plan= query param
 * from the pricing page CTAs.
 */

import { Suspense } from 'react';
import { PageContainer } from '@/components/layout/page-container';
import { CheckoutWizard } from '@/components/billing/CheckoutWizard';
import { Spinner } from '@/components/ui/spinner';

export default function CheckoutPage() {
    return (
        <div
            className="min-h-screen relative"
            style={{ background: 'var(--re-surface-base)' }}
        >
            <PageContainer>
                <Suspense
                    fallback={
                        <div className="flex items-center justify-center min-h-[60vh]">
                            <Spinner />
                        </div>
                    }
                >
                    <CheckoutWizard />
                </Suspense>
            </PageContainer>
        </div>
    );
}
