import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'CSV upload and JSON events API supplier data intake';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Integrations', title: 'CSV upload and JSON events API supplier data intake' });
}
