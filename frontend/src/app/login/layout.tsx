import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Sign In | RegEngine',
    description: 'Sign in to your RegEngine workspace to manage FSMA 204 traceability records and review-ready exports.',
    openGraph: {
        title: 'Sign In | RegEngine',
        description: 'Sign in to your RegEngine workspace to manage FSMA 204 traceability records and review-ready exports.',
        type: 'website',
        url: 'https://regengine.co/login',
    },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
    return children;
}
