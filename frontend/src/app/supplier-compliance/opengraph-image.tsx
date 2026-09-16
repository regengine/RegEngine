import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'Your buyer asked about FSMA 204 traceability';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Supplier Compliance', title: 'Your buyer asked about FSMA 204 traceability' });
}
