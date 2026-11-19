import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'FSMA 204 Critical Tracking Event guide';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({
        eyebrow: 'FSMA 204 CTE',
        title: 'Critical Tracking Event requirements under the Food Traceability Rule',
    });
}
