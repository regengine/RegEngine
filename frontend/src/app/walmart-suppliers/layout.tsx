import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Walmart Supplier FSMA 204 Compliance | RegEngine — Walmart-Ready in 30 Days',
    description:
        'Meet Walmart\'s internal traceability requirements before their Q1 2027 deadline. API-first FSMA 204 compliance for Walmart suppliers — automated CTEs, 5-second trace, and FDA-ready exports. Free assessment available.',
    keywords: [
        'Walmart FSMA 204 compliance',
        'Walmart supplier traceability',
        'FSMA 204 software',
        'food traceability API',
        'Walmart food safety requirements',
        'FDA traceability rule',
        'supply chain compliance',
        'CTE KDE traceability',
    ],
    openGraph: {
        title: 'Walmart-Ready in 30 Days | RegEngine FSMA 204 Compliance',
        description:
            'API-first traceability for Walmart suppliers. Automated CTEs, 5-second trace, FDA-ready exports. Free assessment.',
        type: 'website',
        url: 'https://regengine.co/walmart-suppliers',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Walmart-Ready in 30 Days | RegEngine',
        description:
            'Meet Walmart\'s FSMA 204 requirements before their internal deadline. Free compliance assessment.',
    },
    robots: {
        index: true,
        follow: true,
    },
    alternates: {
        canonical: 'https://regengine.co/walmart-suppliers',
    },
};

export default function WalmartSuppliersLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <>{children}</>;
}
