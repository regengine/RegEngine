import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Sign In | RegEngine',
    description: 'Sign in to your RegEngine workspace to manage FSMA 204 compliance, traceability records, and audit-ready exports.',
    openGraph: {
        title: 'Sign In — RegEngine',
        description: 'Sign in to your RegEngine workspace to manage FSMA 204 compliance, traceability records, and audit-ready exports.',
        type: 'website',
        url: 'https://regengine.co/login',
    },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
    return children;
}
