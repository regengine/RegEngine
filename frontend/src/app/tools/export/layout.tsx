import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';
import { RelatedTools } from '@/components/tools/RelatedTools';

export const metadata: Metadata = {
    title: 'FDA-Oriented Export Package Generator | FSMA 204 Records | RegEngine',
    description: 'Generate a verifiable FSMA 204 records package to support 21 CFR 1.1455 record-availability workflows. SHA-256 verification supports integrity; it does not determine compliance or FDA acceptance. Try free.',
    alternates: {
        canonical: 'https://regengine.co/tools/export',
    },
    openGraph: {
        title: 'FDA Export Package Generator — RegEngine',
        description: 'Generate verifiable FSMA 204 records packages with SHA-256 chain verification to support record-availability workflows. Free.',
        type: 'website',
        url: 'https://regengine.co/tools/export',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'FDA Export Package Generator',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'Generate SHA-256 chain-verified FDA-oriented records packages for FSMA 204 traceability workflows.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

const relatedTools = [
    { href: '/tools/data-import', title: 'Data Import Hub', description: 'Import traceability data via CSV, IoT temperature logs, or webhook API before exporting.' },
    { href: '/tools/notice-validator', title: 'FDA Request Validator', description: 'Validate your draft FDA response against FSMA 204 record requirements before submission.' },
    { href: '/tools/recall-readiness', title: 'FSMA 204 Readiness Self-Check', description: 'Self-check your ability to meet the §1.1455(c) 24-hour records request obligation.' },
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
