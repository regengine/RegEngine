import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'FSMA 204 Dashboard | Traceability & Recall Management | RegEngine',
    description: 'FSMA 204 compliance dashboard with traceability lot tracking, recall drill simulations, supplier KDE completeness, and FDA export readiness.',
    openGraph: {
        title: 'FSMA 204 Dashboard — RegEngine',
        description: 'FSMA 204 compliance dashboard with lot tracking, recall drills, and FDA export readiness.',
        url: 'https://regengine.co/fsma',
        type: 'website',
    },
};

export default function FSMALayout({ children }: { children: React.ReactNode }) {
    return children;
}
