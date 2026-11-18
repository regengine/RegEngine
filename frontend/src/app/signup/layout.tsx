import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Request access | RegEngine',
    description: 'Request a RegEngine workspace. C.Lee reviews each request and replies by email. Already invited users sign in.',
    robots: { index: false, follow: false },
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
    return children;
}
