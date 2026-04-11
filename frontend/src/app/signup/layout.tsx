import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Create Account | RegEngine',
    description: 'Create your RegEngine workspace to start FSMA 204 compliance tracking, traceability record management, and audit-ready exports.',
    openGraph: {
        title: 'Create Account — RegEngine',
        description: 'Create your RegEngine workspace to start FSMA 204 compliance tracking.',
        type: 'website',
        url: 'https://regengine.co/signup',
    },
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
    return children;
}
