import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'Support & Escalation Model';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Trust Center', title: 'Support & Escalation Model' });
}
