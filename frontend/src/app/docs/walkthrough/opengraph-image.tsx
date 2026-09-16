import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'End-to-end FSMA 204 flow in 15 minutes';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Documentation', title: 'End-to-end FSMA 204 flow in 15 minutes' });
}
