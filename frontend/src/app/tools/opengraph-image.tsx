import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

// Inherited by every /tools/* page that does not ship its own card.
export const runtime = 'edge';
export const alt = 'RegEngine free FSMA 204 tools';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({
        eyebrow: 'Free Tool',
        title: 'Free tools for FSMA 204 list checks and field checks',
    });
}
