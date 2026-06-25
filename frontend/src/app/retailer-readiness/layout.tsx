import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Retailer Supplier FSMA 204 Compliance | RegEngine — Retailer-Ready in 48 Hours',
    description:
        'Major retailers are signaling traceability expectations to suppliers ahead of the federal enforcement date — confirm directly with your buyer. API-first FSMA 204 traceability for food suppliers — automated CTEs and FDA-oriented sortable exports. Free self-check available.',
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
        title: 'Retailer-Ready in 48 Hours | RegEngine FSMA 204 Compliance',
        description:
            'API-first traceability for food suppliers. Automated CTEs and FDA-oriented sortable exports. Free self-check.',
        type: 'website',
        url: 'https://regengine.co/retailer-readiness',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Retailer-Ready in 48 Hours | RegEngine',
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
