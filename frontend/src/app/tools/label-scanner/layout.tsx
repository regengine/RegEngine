import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';
import { RelatedTools } from '@/components/tools/RelatedTools';

export const metadata: Metadata = {
    title: 'AI Food Label Scanner | Extract FSMA 204 KDEs from Product Labels | RegEngine',
    description: 'Upload a food product label and AI extracts lot code, GTIN, expiry date, and FSMA 204 Key Data Elements automatically using computer vision. Free tool.',
    alternates: {
        canonical: 'https://regengine.co/tools/label-scanner',
    },
    openGraph: {
        title: 'AI Food Label Scanner — RegEngine',
        description: 'Upload a food label and AI extracts lot code, GTIN, expiry date, and FSMA 204 KDEs automatically. Free.',
        type: 'website',
        url: 'https://regengine.co/tools/label-scanner',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'AI Food Label Scanner',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'AI-powered food label extraction tool that maps product data to FSMA 204 Key Data Elements.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

const relatedTools = [
    { href: '/tools/scan', title: 'GS1 Barcode Scanner', description: 'Scan or paste GS1 barcodes to decode GTIN, lot codes, and expiry into traceability records.' },
    { href: '/tools/data-import', title: 'Data Import Hub', description: 'Import traceability data via CSV, IoT temperature logs, or webhook API.' },
    { href: '/tools/kde-checker', title: 'KDE Checker', description: 'Generate the full Key Data Element checklist required for your FTL product and CTE type.' },
];

export default function LabelScannerLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <JSONLD data={jsonLd} />
            {children}
            <RelatedTools tools={relatedTools} />
        </>
    );
}
