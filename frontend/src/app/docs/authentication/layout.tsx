import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'API Authentication | RegEngine',
    description: 'Authenticate to the RegEngine API with the X-RegEngine-API-Key header: scopes, and what a key can reach. RegEngine issues keys on request.',
    openGraph: {
        title: 'API Authentication',
        description: 'Authenticate to the RegEngine API with the X-RegEngine-API-Key header: scopes, and what a key can reach. RegEngine issues keys on request.',
        url: 'https://regengine.co/docs/authentication',
        type: 'website',
    },
};

export default function Layout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
