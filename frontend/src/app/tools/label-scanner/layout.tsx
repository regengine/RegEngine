import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'AI Label Scanner | Food Label Data Extraction | RegEngine',
    description: 'Upload or photograph a food label. AI extracts product name, lot code, GTIN, expiry, and maps to FSMA 204 KDEs automatically.',
    openGraph: {
        title: 'AI Label Scanner — RegEngine',
        description: 'Upload or photograph a food label. AI extracts product name, lot code, GTIN, expiry, and maps to FSMA 204 KDEs automatically.',
        type: 'website',
        url: 'https://www.regengine.co/tools/label-scanner',
    },
};

export default function LabelScannerLayout({ children }: { children: React.ReactNode }) {
    return children;
}
