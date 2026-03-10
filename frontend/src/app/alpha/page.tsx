import type { Metadata } from 'next';

import AlphaPageClient from './AlphaPageClient';

export const metadata: Metadata = {
    title: 'Design Partner Program | RegEngine Private Alpha',
    description: "Join RegEngine's private alpha. 25 spots for design partners shaping food traceability compliance.",
    openGraph: {
        title: 'Design Partner Program | RegEngine Private Alpha',
        description: "Join RegEngine's private alpha. 25 spots for design partners shaping food traceability compliance.",
        url: 'https://www.regengine.co/alpha',
        type: 'website',
    },
};

export default function AlphaPage() {
    return <AlphaPageClient />;
}
