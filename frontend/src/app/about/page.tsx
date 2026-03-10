import type { Metadata } from 'next';

import AboutPageClient from './AboutPageClient';

export const metadata: Metadata = {
    title: 'About | RegEngine',
    description: 'Meet the founder of RegEngine. 20 years in federal compliance, disaster response, and food safety tech.',
    openGraph: {
        title: 'About | RegEngine',
        description: 'Meet the founder of RegEngine. 20 years in federal compliance, disaster response, and food safety tech.',
        url: 'https://www.regengine.co/about',
        type: 'website',
    },
};

export default function AboutPage() {
    return <AboutPageClient />;
}
