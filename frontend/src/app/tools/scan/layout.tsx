import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'GS1 Barcode Scanner | Scan & Ingest Traceability Data | RegEngine',
    description: 'Scan GS1 barcodes with your camera or paste barcode strings. Extract FSMA-compatible traceability data instantly.',
    openGraph: {
        title: 'GS1 Barcode Scanner — RegEngine',
        description: 'Scan GS1 barcodes with your camera or paste barcode strings. Extract FSMA-compatible traceability data instantly.',
        type: 'website',
        url: 'https://www.regengine.co/tools/scan',
    },
};

export default function ScanLayout({ children }: { children: React.ReactNode }) {
    return children;
}
