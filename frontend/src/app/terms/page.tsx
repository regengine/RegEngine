import type { Metadata } from 'next';
import TermsClient from './TermsClient';

export const metadata: Metadata = {
    title: 'Terms of Service | RegEngine',
    description: 'RegEngine terms of service. Plain language rules for using FSMA 204 compliance tools.',
    openGraph: {
        title: 'Terms of Service | RegEngine',
        description: 'Terms of service for RegEngine FSMA 204 compliance platform.',
        url: 'https://regengine.co/terms',
        type: 'website',
    },
};

export default function TermsPage() {
    return <TermsClient />;
}