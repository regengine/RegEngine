'use client';

import { T } from './constants';

export default function UrgencyBanner() {
    return (
        <div style={{
            background: `linear-gradient(90deg, ${T.dangerBg}, ${T.warningBg}, ${T.dangerBg})`,
            borderBottom: `1px solid ${T.warningBorder}`,
            padding: '10px clamp(12px, 4vw, 24px)',
            position: 'relative', zIndex: 10,
        }}>
            <div style={{
                maxWidth: 1120, margin: '0 auto',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
            }}>
                <span style={{ fontSize: 16 }}>⚠️</span>
                <span style={{ fontSize: 'clamp(12px, 2.5vw, 14px)', color: T.warning, fontWeight: 500, lineHeight: 1.4 }}>
                    Major retailers are evaluating suppliers <strong>now</strong>. Their internal deadlines are earlier than FDA&apos;s July 2028.
                </span>
            </div>
        </div>
    );
}
