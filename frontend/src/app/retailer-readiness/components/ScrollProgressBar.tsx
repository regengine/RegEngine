'use client';

import { T } from './constants';

export interface ScrollProgressBarProps {
    scrollProgress: number;
}

export default function ScrollProgressBar({ scrollProgress }: ScrollProgressBarProps) {
    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, height: 3, zIndex: 9999,
            width: `${scrollProgress}%`,
            background: `linear-gradient(90deg, ${T.accent}, #34d399)`,
            transition: 'width 0.1s linear',
            boxShadow: `0 0 8px ${T.accent}60`,
        }} />
    );
}
