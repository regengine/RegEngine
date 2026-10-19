import type { Metadata } from 'next';
import { JSONLD } from '@/components/seo/json-ld';

export const metadata: Metadata = {
    title: 'FSMA Request Validator | Check Your Draft FDA 24 Hour Response | RegEngine',
    description: 'Validate your draft FDA records request response against FSMA 204 requirements. Checks Critical Tracking Event (CTE) references, Key Data Element (KDE) coverage, and 24 hour retrieval signals. Free.',
    alternates: {
        canonical: 'https://regengine.co/tools/notice-validator',
    },
    openGraph: {
        title: 'FSMA Request Validator | RegEngine',
        description: 'Check if your draft FDA response covers required FSMA 204 Critical Tracking Event (CTE), Key Data Element (KDE), and 24 hour retrieval elements. Free heuristic checker.',
        type: 'website',
        url: 'https://regengine.co/tools/notice-validator',
    },
};

const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'FSMA Request Validator',
    operatingSystem: 'All',
    applicationCategory: 'BusinessApplication',
    description: 'Heuristic checker that validates draft FDA records request responses against FSMA 204 Critical Tracking Event (CTE), Key Data Element (KDE), and retrieval requirements.',
    publisher: { '@type': 'Organization', name: 'RegEngine' },
};

export default function NoticeValidatorLayout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <JSONLD data={jsonLd} />
            {children}
        </>
    );
}
