import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Obligation Scanner | FSMA 204 Compliance Controls | RegEngine',
    description: 'Map your FSMA 204 compliance obligations across CTE capture, KDE completeness, supplier onboarding, and record retention.',
    openGraph: {
        title: 'Obligation Scanner — RegEngine',
        description: 'Map your FSMA 204 compliance obligations across CTE capture, KDE completeness, supplier onboarding, and record retention.',
        type: 'website',
        url: 'https://www.regengine.co/tools/obligation-scanner',
    },
};

export default function ObligationScannerLayout({ children }: { children: React.ReactNode }) {
    return children;
}
