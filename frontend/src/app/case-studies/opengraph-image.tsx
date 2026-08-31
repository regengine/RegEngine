import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = '1,200 leafy greens CTE events, 94.2% auto-normalized';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Validation', title: '1,200 leafy greens CTE events, 94.2% auto-normalized' });
}
