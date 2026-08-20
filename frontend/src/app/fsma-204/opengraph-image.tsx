import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'What the FDA Food Traceability Rule requires of your operation';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'FSMA 204 Guide', title: 'What the FDA Food Traceability Rule requires of your operation' });
}
