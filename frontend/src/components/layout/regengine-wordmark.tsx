import type { CSSProperties } from 'react';
import Image from 'next/image';

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
            <Image
                src="/icon.png"
                alt=""
                aria-hidden
                width={config.icon}
                height={config.icon}
                style={{
                    width: `${config.icon}px`,
                    height: `${config.icon}px`,
                    objectFit: 'contain',
                    display: 'block',
                }}
            />
            {showText ? (
                <span
                    style={{
                        fontFamily: "var(--re-font-display)",
                        fontSize: `${config.text}px`,
                        lineHeight: 1,
                        letterSpacing: 0,
                        fontWeight: 700,
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
