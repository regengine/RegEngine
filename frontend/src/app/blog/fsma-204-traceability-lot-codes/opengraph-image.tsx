import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';
import { BLOG_POST_TITLES } from '@/lib/blog-posts';

export const runtime = 'edge';
export const alt = BLOG_POST_TITLES['fsma-204-traceability-lot-codes'];
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'FSMA 204 Guide', title: BLOG_POST_TITLES['fsma-204-traceability-lot-codes'] });
}
