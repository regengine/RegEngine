import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'How to build the FSMA 204 sortable spreadsheet';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'FSMA 204 Guide', title: 'How to build the FSMA 204 sortable spreadsheet' });
}
