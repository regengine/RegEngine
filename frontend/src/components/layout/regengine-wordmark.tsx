import type { CSSProperties } from 'react';

type WordmarkSize = 'sm' | 'md';

const SIZE_CONFIG: Record<WordmarkSize, { mark: number; text: number; gap: number }> = {
    sm: { mark: 18, text: 18, gap: 8 },
    md: { mark: 22, text: 20, gap: 9 },
};

type RegEngineWordmarkProps = {
    size?: WordmarkSize;
    showText?: boolean;
    className?: string;
    textStyle?: CSSProperties;
};

/**
 * The RegEngine wordmark — the single source of truth for the mark.
 *
 * The mark is three stacked planes, offset, with the top plane in brand green:
 * the brand doc's "layered traceability — stacked data planes flowing through
 * the compliance stack". It replaces the 2×2 red/ink/yellow/green tile, which
 * put four signal colours in the one place that should be brand-only and read
 * as a status indicator rather than a logo.
 *
 * "Reg" is ink and "Engine" is brand green, per the brand guidelines. The
 * wordmark is one of only six places brand green is allowed to appear.
 */
export function RegEngineWordmark({
    size = 'md',
    showText = true,
    className,
    textStyle,
}: RegEngineWordmarkProps) {
    const config = SIZE_CONFIG[size];

    return (
        <span
            className={className}
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: `${config.gap}px`,
                minWidth: 0,
            }}
        >
            <svg
                aria-hidden="true"
                width={config.mark}
                height={config.mark}
                viewBox="0 0 22 22"
                fill="none"
                style={{ flexShrink: 0, display: 'block' }}
            >
                {/* Bottom and middle planes: ink. Top plane: brand. */}
                <rect x="1" y="14" width="20" height="4" rx="1" fill="var(--re-text-primary)" opacity="0.35" />
                <rect x="1" y="8.5" width="20" height="4" rx="1" fill="var(--re-text-primary)" opacity="0.7" />
                <rect x="1" y="3" width="20" height="4" rx="1" fill="var(--re-brand)" />
            </svg>
            {showText ? (
                <span
                    style={{
                        fontFamily: 'var(--re-font-sans)',
                        fontSize: `${config.text}px`,
                        lineHeight: 1,
                        letterSpacing: '-0.01em',
                        fontWeight: 600,
                        color: 'var(--re-text-primary)',
                        whiteSpace: 'nowrap',
                        ...textStyle,
                    }}
                >
                    Reg<span style={{ color: 'var(--re-brand)' }}>Engine</span>
                </span>
            ) : null}
        </span>
    );
}
