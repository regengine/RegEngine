import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'Extract FSMA 204 Key Data Element (KDE) fields from product labels';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Free Tool', title: 'Extract FSMA 204 Key Data Element (KDE) fields from product labels' });
}
