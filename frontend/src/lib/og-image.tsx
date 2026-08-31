import { ImageResponse } from 'next/og';

/**
 * Shared 1200x630 social card renderer.
 *
 * The homepage keeps its hand-designed /og-image.png; every other public page
 * used to ship no image at all, which downgraded its X/Twitter card to the
 * small `summary` form (Next derives twitter:* from openGraph, and defaults
 * the card to `summary_large_image` only when an image is present). Segment
 * `opengraph-image.tsx` files call this so those pages get a real card.
 *
 * Note: a segment file is ignored when that segment's own metadata sets
 * `openGraph.images` — Next only fills in file-based images when the field is
 * absent. Keep `images` out of page metadata that relies on this.
 */
export const OG_SIZE = { width: 1200, height: 630 } as const;
export const OG_CONTENT_TYPE = 'image/png';

type OgCardProps = {
    /** Small label above the title, e.g. "FSMA 204 Guide" or "Free Tool". */
    eyebrow: string;
    /** The page's own headline. Keep it under ~90 characters. */
    title: string;
};

export function renderOgCard({ eyebrow, title }: OgCardProps) {
    return new ImageResponse(
        (
            <div
                style={{
                    background: 'linear-gradient(135deg, #06090f 0%, #0c1017 50%, #111827 100%)',
                    width: '100%',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    padding: '72px',
                    fontFamily: 'system-ui, sans-serif',
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div
                        style={{
                            width: '52px',
                            height: '52px',
                            borderRadius: '13px',
                            background: '#10b981',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                        }}
                    >
                        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                        </svg>
                    </div>
                    <span style={{ fontSize: '38px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-1px' }}>
                        RegEngine
                    </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <div style={{ fontSize: '24px', color: '#10b981', fontWeight: 600, marginBottom: '18px' }}>
                        {eyebrow}
                    </div>
                    <div
                        style={{
                            fontSize: '58px',
                            fontWeight: 700,
                            color: '#f8fafc',
                            lineHeight: 1.15,
                            letterSpacing: '-1.5px',
                        }}
                    >
                        {title}
                    </div>
                </div>

                <div style={{ fontSize: '22px', color: '#94a3b8' }}>regengine.co</div>
            </div>
        ),
        { ...OG_SIZE }
    );
}
