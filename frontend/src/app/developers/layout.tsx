import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Developers | RegEngine FSMA 204 API',
    description: 'RegEngine REST API for FSMA 204 compliance. Record CTEs, run recall simulations, and export FDA packages programmatically.',
    openGraph: {
        title: 'Developers | RegEngine FSMA 204 API',
        description: 'RegEngine REST API for FSMA 204 compliance. Record CTEs, run recall simulations, and export FDA packages programmatically.',
        url: 'https://www.regengine.co/developers',
        type: 'website',
    },
};

export default function DevelopersLayout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}