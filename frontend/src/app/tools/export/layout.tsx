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
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

const relatedTools = [
    { href: '/tools/data-import', title: 'Data Import Hub', description: 'Import traceability data via CSV, IoT temperature logs, or webhook API before exporting.' },
    { href: '/tools/notice-validator', title: 'FDA Request Validator', description: 'Validate your draft FDA response against FSMA 204 record requirements before submission.' },
    { href: '/tools/records-request-checklist', title: 'Records Request Checklist', description: 'A self reported checklist for an FDA records request. Not a 24 hour test and not a readiness score.' },
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
