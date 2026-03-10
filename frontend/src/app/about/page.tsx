import type { Metadata } from 'next';

import AboutPageClient from './AboutPageClient';

export const metadata: Metadata = {
    title: 'About | RegEngine',
    description: 'Compliance infrastructure for FSMA 204, built from the ground up by a solo technical founder.',
    openGraph: {
        title: 'About | RegEngine',
        description: 'Compliance infrastructure for FSMA 204, built from the ground up by a solo technical founder.',
        url: 'https://www.regengine.co/about',
        type: 'website',
    },
};

export default function AboutPage() {
    return <AboutPageClient />;
}
