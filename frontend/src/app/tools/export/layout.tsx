import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';
import { RelatedTools } from '@/components/tools/RelatedTools';

export const metadata: Metadata = {
    title: 'FDA Export Package Generator | FSMA 204 21 CFR 1.1455 Compliance | RegEngine',
    description: 'Generate a cryptographically verifiable FDA compliance package for FSMA 204 records. SHA-256 chain verification meets 21 CFR 1.1455 requirements. Try free.',
    alternates: {
        canonical: 'https://www.regengine.co/tools/export',
    },
    openGraph: {
        title: 'FDA Export Package Generator — RegEngine',
        description: 'Generate verifiable FSMA 204 compliance packages with SHA-256 chain verification meeting 21 CFR 1.1455 requirements. Free.',
        type: 'website',
        url: 'https://www.regengine.co/tools/export',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'FDA Export Package Generator',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'Generate SHA-256 chain-verified FDA compliance packages for FSMA 204 traceability records per 21 CFR 1.1455.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

const relatedTools = [
    { href: '/tools/data-import', title: 'Data Import Hub', description: 'Import traceability data via CSV, IoT temperature logs, or webhook API before exporting.' },
    { href: '/tools/notice-validator', title: 'FDA Request Validator', description: 'Validate your draft FDA response against FSMA 204 record requirements before submission.' },
    { href: '/tools/recall-readiness', title: 'Recall Readiness Score', description: 'Grade your ability to meet the FDA 24-hour records retrieval mandate.' },
];

export default function ExportLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <JSONLD data={jsonLd} />
            {children}
            <RelatedTools tools={relatedTools} />
        </>
    );
}
