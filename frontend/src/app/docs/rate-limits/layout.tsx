import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Rate Limits | RegEngine',
    description: 'How RegEngine rate limits API requests, and what to do when you get a 429.',
    openGraph: {
        title: 'Rate Limits',
        description: 'How RegEngine rate limits API requests, and what to do when you get a 429.',
        url: 'https://regengine.co/docs/rate-limits',
        type: 'website',
    },
};

export default function Layout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
