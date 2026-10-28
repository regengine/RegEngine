import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'Supplier FSMA 204 checklist for retailer expectations';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Supplier checklist', title: 'Supplier FSMA 204 checklist for retailer expectations' });
}
