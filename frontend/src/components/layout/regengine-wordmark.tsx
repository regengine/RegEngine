import type { CSSProperties } from 'react';

type WordmarkSize = 'sm' | 'md';

const SIZE_CONFIG: Record<WordmarkSize, { icon: number; text: number; gap: number }> = {
    sm: { icon: 18, text: 18, gap: 7 },
    md: { icon: 22, text: 20, gap: 8 },
};

type RegEngineWordmarkProps = {
    size?: WordmarkSize;
    showText?: boolean;
    className?: string;
    textStyle?: CSSProperties;
};

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
            <span
                aria-hidden
                style={{
                    width: `${config.icon}px`,
                    height: `${config.icon}px`,
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gridTemplateRows: '1fr 1fr',
                    gap: 2,
                    border: '1px solid var(--re-text-primary)',
                    padding: 2,
                    background: 'var(--re-surface-base)',
                }}
            >
                <span style={{ background: 'var(--re-signal-red)' }} />
                <span style={{ background: 'var(--re-text-primary)' }} />
                <span style={{ background: 'var(--re-signal-yellow)' }} />
                <span style={{ background: 'var(--re-signal-green)' }} />
            </span>
            {showText ? (
                <span
                    style={{
                        fontFamily: "var(--re-font-display)",
                        fontSize: `${config.text}px`,
                        lineHeight: 1,
                        letterSpacing: 0,
                        fontWeight: 650,
                        color: 'var(--re-text-primary)',
                        ...textStyle,
                    }}
                >
                    RegEngine
                </span>
            ) : null}
        </span>
    );
}
