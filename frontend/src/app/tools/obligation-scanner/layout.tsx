import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';

export const metadata: Metadata = {
    title: 'FSMA 204 Obligation Scanner | Map Your Compliance Controls | RegEngine',
    description: 'Scan your FSMA 204 compliance obligations across CTE capture, KDE completeness, supplier onboarding, and 2-year record retention. Free compliance mapper.',
    alternates: {
        canonical: 'https://www.regengine.co/tools/obligation-scanner',
    },
    openGraph: {
        title: 'FSMA 204 Obligation Scanner — RegEngine',
        description: 'Map your FSMA 204 compliance obligations across CTE capture, KDE completeness, supplier onboarding, and record retention. Free.',
        type: 'website',
        url: 'https://www.regengine.co/tools/obligation-scanner',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'FSMA 204 Obligation Scanner',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'Maps FSMA 204 compliance obligations across CTE capture, KDE completeness, supplier onboarding, and 2-year record retention.',
    offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

export default function ObligationScannerLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <JSONLD data={jsonLd} />
            {children}
        </>
    );
}
