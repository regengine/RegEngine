import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';
import { RelatedTools } from '@/components/tools/RelatedTools';

export const metadata: Metadata = {
    title: 'GS1 Barcode Scanner | Decode Food Traceability Barcodes | RegEngine',
    description: 'Scan or paste GS1 barcodes to decode GTIN, lot codes, and expiry dates into FSMA 204-compatible traceability records. Works with any food product barcode. Free.',
    alternates: {
        canonical: 'https://regengine.co/tools/scan',
    },
    openGraph: {
        title: 'GS1 Barcode Scanner — RegEngine',
        description: 'Decode GS1 barcodes into FSMA 204-compatible traceability records. Free barcode scanner tool.',
        type: 'website',
        url: 'https://regengine.co/tools/scan',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'GS1 Barcode Scanner',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'Scan or paste GS1 barcodes to extract FSMA 204-compatible traceability data including GTIN, lot code, and expiry date.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

const relatedTools = [
    { href: '/tools/label-scanner', title: 'AI Label Scanner', description: 'Upload a food label and AI extracts lot code, GTIN, expiry date, and FSMA 204 KDEs automatically.' },
    { href: '/tools/data-import', title: 'Data Import Hub', description: 'Import traceability data from CSV files, IoT temperature logs, or webhook API.' },
    { href: '/tools/tlc-validator', title: 'TLC Validator', description: 'Validate your Traceability Lot Code format against GS1 and FDA FSMA 204 requirements.' },
];

export default function ScanLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <JSONLD data={jsonLd} />
            {children}
            <RelatedTools tools={relatedTools} />
        </>
    );
}
