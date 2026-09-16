import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Rate Limits | RegEngine',
    description: 'RegEngine API rate limits, per-response limit headers, and back-off guidance for 429 responses.',
    openGraph: {
        title: 'Rate Limits',
        description: 'RegEngine API rate limits, per-response limit headers, and back-off guidance for 429 responses.',
        url: 'https://regengine.co/docs/rate-limits',
        type: 'website',
    },
};

export default function Layout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
