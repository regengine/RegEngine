import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'RegEngine FSMA 204 sandbox';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({
        eyebrow: 'Sandbox',
        title: 'Upload a CSV, see which FSMA 204 data elements are missing',
    });
}
