import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'API Authentication | RegEngine',
    description: 'Authenticate to the RegEngine API with scoped API keys: header format, key rotation, and least-privilege scopes.',
    openGraph: {
        title: 'API Authentication',
        description: 'Authenticate to the RegEngine API with scoped API keys: header format, key rotation, and least-privilege scopes.',
        url: 'https://regengine.co/docs/authentication',
        type: 'website',
    },
};

export default function Layout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
