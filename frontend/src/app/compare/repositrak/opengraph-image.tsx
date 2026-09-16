import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'RegEngine vs ReposiTrak for FSMA 204 compliance';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Comparison', title: 'RegEngine vs ReposiTrak for FSMA 204 compliance' });
}
