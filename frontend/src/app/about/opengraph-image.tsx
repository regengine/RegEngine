import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'FSMA 204 compliance infrastructure for food supply chains';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'RegEngine', title: 'FSMA 204 compliance infrastructure for food supply chains' });
}
