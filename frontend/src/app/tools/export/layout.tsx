import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'FDA Export Package Generator | 21 CFR 1.1455 Compliance | RegEngine',
    description: 'Generate a verifiable FDA compliance package with SHA-256 chain verification for FSMA 204 traceability records.',
    openGraph: {
        title: 'FDA Export Package Generator — RegEngine',
        description: 'Generate a verifiable FDA compliance package with SHA-256 chain verification for FSMA 204 traceability records.',
        type: 'website',
        url: 'https://www.regengine.co/tools/export',
    },
};

export default function ExportLayout({ children }: { children: React.ReactNode }) {
    return children;
}
