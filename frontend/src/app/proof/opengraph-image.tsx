import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'Verify RegEngine bundles yourself';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({
        eyebrow: 'Proof',
        title: 'Verify RegEngine bundles yourself',
    });
}
