import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Supplier FSMA 204 Checklist for Retailer Expectations | RegEngine',
    description:
        'Major retailers are signaling traceability expectations to suppliers ahead of the federal enforcement date; confirm directly with your buyer. Use RegEngine buyer-program pages and gap checklists to review supplier FSMA 204 CTE/KDE and export expectations. Free self-check available.',
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
        title: 'Supplier FSMA 204 Checklist for Retailer Expectations | RegEngine',
        description:
            'Gap and checklist framing for supplier FSMA 204 CTE/KDE and export expectations that retailers may ask about. Free self-check.',
        type: 'website',
        url: 'https://regengine.co/retailer-readiness',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Supplier FSMA 204 Checklist for Retailer Expectations | RegEngine',
        description:
            'Review supplier FSMA 204 checklist gaps against retailer traceability expectations. Free self-check.',
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
