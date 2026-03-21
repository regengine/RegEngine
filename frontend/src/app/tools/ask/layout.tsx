import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Traceability Query Engine | Natural Language Supply Chain Search | RegEngine',
    description: 'Ask questions about your supply chain in plain English. Get traced results with evidence and confidence scores.',
    openGraph: {
        title: 'Traceability Query Engine — RegEngine',
        description: 'Ask questions about your supply chain in plain English. Get traced results with evidence and confidence scores.',
        type: 'website',
        url: 'https://www.regengine.co/tools/ask',
    },
};

export default function AskLayout({ children }: { children: React.ReactNode }) {
    return children;
}
