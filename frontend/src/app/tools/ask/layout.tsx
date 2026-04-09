import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';
import { RelatedTools } from '@/components/tools/RelatedTools';

export const metadata: Metadata = {
    title: 'Traceability Query Engine | Natural Language FSMA 204 Search | RegEngine',
    description: 'Ask plain English questions about your food supply chain. Get FSMA 204-traced answers with cryptographic evidence and confidence scores. Free query tool.',
    alternates: {
        canonical: 'https://www.regengine.co/tools/ask',
    },
    openGraph: {
        title: 'Traceability Query Engine — RegEngine',
        description: 'Ask natural language questions about your supply chain and get FSMA 204-traced answers with cryptographic evidence. Free.',
        type: 'website',
        url: 'https://www.regengine.co/tools/ask',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Traceability Query Engine',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'Natural language query tool for FSMA 204 supply chain traceability data with cryptographic evidence and confidence scores.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

const relatedTools = [
    { href: '/tools/knowledge-graph', title: 'Knowledge Graph', description: 'Visually map your FSMA 204 supply chain nodes and identify CTE and KDE coverage gaps.' },
    { href: '/tools/export', title: 'FDA Export Generator', description: 'Generate a verifiable SHA-256 compliance package from your traceability records.' },
    { href: '/tools/ftl-checker', title: 'FTL Checker', description: 'Check which food products in your supply chain are on the FDA Traceability List.' },
];

export default function AskLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <JSONLD data={jsonLd} />
            {children}
            <RelatedTools tools={relatedTools} />
        </>
    );
}
