import { Suspense } from 'react';

export const metadata = {
    title: 'System Architecture — RegEngine',
    description:
        "Interactive map of RegEngine's full FSMA 204 compliance infrastructure. See what's built, in progress, needed, and planned.",
    openGraph: {
        title: 'RegEngine System Architecture',
        description:
            'Full FSMA 204 compliance infrastructure map — 25 components across 5 layers.',
        url: 'https://regengine.co/architecture',
        siteName: 'RegEngine',
        type: 'website',
    },
};

export default function ArchitectureLayout({ children }) {
    // Suspense boundary required for useSearchParams() in page.jsx
    return <Suspense>{children}</Suspense>;
}
