import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Retailer Supplier FSMA 204 Compliance | RegEngine — FDA-Ready Export in 48 Hours',
    description:
        'Meet major retailer traceability requirements before their internal deadlines. API-first FSMA 204 compliance for food suppliers — automated CTEs, 5-second trace, and FDA-ready exports. Free assessment available.',
    keywords: [
        'retailer FSMA 204 compliance',
        'food supplier traceability',
        'FSMA 204 software',
        'food traceability API',
        'retailer food safety requirements',
        'FDA traceability rule',
        'supply chain compliance',
        'CTE KDE traceability',
    ],
    openGraph: {
        title: 'FDA-Ready Export in 48 Hours | RegEngine FSMA 204 Compliance',
        description:
            'API-first traceability for food suppliers. Automated CTEs, 5-second trace, FDA-ready exports. Free assessment.',
        type: 'website',
        url: 'https://regengine.co/retailer-readiness',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'FDA-Ready Export in 48 Hours | RegEngine',
        description:
            'Meet major retailer FSMA 204 requirements before their internal deadlines. Free compliance assessment.',
    },
    robots: {
        index: true,
        follow: true,
    },
    alternates: {
        canonical: 'https://regengine.co/retailer-readiness',
    },
};

export default function RetailerSuppliersLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <>{children}</>;
}
