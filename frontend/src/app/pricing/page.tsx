import type { Metadata } from 'next';

import PricingPageClient from './PricingPageClient';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: 'FSMA 204 compliance pricing. Plans from $999/mo. Free traceability tools included.',
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: 'FSMA 204 compliance pricing. Plans from $999/mo. Free traceability tools included.',
        url: 'https://www.regengine.co/pricing',
        type: 'website',
    },
};

export default function PricingPage() {
    return <PricingPageClient />;
}
