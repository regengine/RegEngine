import type { Metadata } from 'next';

import DevelopersPageClient from './DevelopersPageClient';

export const metadata: Metadata = {
    title: 'Developers | RegEngine FSMA API',
    description: 'RegEngine developer docs. Node.js, Python, and cURL SDKs for FSMA 204 compliance API.',
    openGraph: {
        title: 'Developers | RegEngine FSMA API',
        description: 'RegEngine developer docs. Node.js, Python, and cURL SDKs for FSMA 204 compliance API.',
        url: 'https://www.regengine.co/developers',
        type: 'website',
    },
};

export default function DevelopersPage() {
    return <DevelopersPageClient />;
}
