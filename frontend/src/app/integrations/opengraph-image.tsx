import { renderOgCard, OG_SIZE, OG_CONTENT_TYPE } from '@/lib/og-image';

export const runtime = 'edge';
export const alt = 'CSV, API, webhook, EPCIS, and SFTP supplier data intake';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;

export default function Image() {
    return renderOgCard({ eyebrow: 'Integrations', title: 'CSV, API, webhook, EPCIS, and SFTP supplier data intake' });
}
