import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Contact Us | RegEngine',
    description: 'Get in touch with the RegEngine team. Ask about FSMA 204 compliance, request a demo, or discuss your traceability needs.',
    openGraph: {
        title: 'Contact Us — RegEngine',
        description: 'Get in touch with the RegEngine team. Ask about FSMA 204 compliance, request a demo, or discuss your traceability needs.',
        type: 'website',
        url: 'https://regengine.co/contact',
    },
};

export default function ContactLayout({ children }: { children: React.ReactNode }) {
    return children;
}
