import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'Build FSMA 204 traceability on RegEngine APIs';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Developer Guide', title: 'Build FSMA 204 traceability on RegEngine APIs' });
}
