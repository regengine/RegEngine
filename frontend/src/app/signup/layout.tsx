import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Request access | RegEngine',
    description: 'Request a RegEngine workspace. The team sets up access, usually within one business day. Already invited users sign in.',
    robots: { index: false, follow: false },
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
    return children;
}
