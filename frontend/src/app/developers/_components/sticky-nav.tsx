'use client';

import { useState, useEffect } from 'react';
import { T, NAV_SECTIONS } from '../_data';
import { useEnv } from './env-context';

export function StickyNav() {
    const [activeSection, setActiveSection] = useState('quickstart');
    const { env, setEnv, baseUrl } = useEnv();

    /* Intersection observer for active state */
    useEffect(() => {
        const obs = new IntersectionObserver((entries) => {
            for (const e of entries) {
                if (e.isIntersecting) setActiveSection(e.target.id);
            }
        }, { rootMargin: '-20% 0px -70% 0px' });
        NAV_SECTIONS.forEach(({ id }) => {
            const el = document.getElementById(id);
            if (el) obs.observe(el);
        });
        return () => obs.disconnect();
    }, []);

    return (
        <>
            <nav className="re-sticky-nav" style={{ marginBottom: 0 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', gap: 4, overflowX: 'auto' }}>
                    {NAV_SECTIONS.map((s) => (
                        <a key={s.id} href={`#${s.id}`}
                            className={`re-nav-link ${activeSection === s.id ? 're-nav-active' : ''}`}
                            style={{ color: activeSection === s.id ? T.accent : T.textMuted }}>
                            {s.label}
                        </a>
                    ))}
                    <div style={{ flex: 1 }} />
                    {/* Env toggle */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: `1px solid ${T.border}`, overflow: 'hidden' }}>
                        {(['production', 'sandbox'] as const).map((e) => (
                            <button key={e} onClick={() => setEnv(e)} style={{
                                padding: '5px 12px', fontSize: 11, fontWeight: 600, fontFamily: T.mono,
                                border: 'none', cursor: 'pointer', textTransform: 'capitalize',
                                background: env === e ? (e === 'production' ? T.accentBg : T.amberBg) : 'transparent',
                                color: env === e ? (e === 'production' ? T.accent : T.amber) : T.textMuted,
                                transition: 'all .15s',
                            }}>{e}</button>
                        ))}
                    </div>
                </div>
            </nav>
            {/* Base URL indicator */}
            <div style={{ maxWidth: 880, margin: '0 auto', padding: '16px 24px 0' }}>
                <div className="re-base-url" style={{
                    display: 'inline-flex', alignItems: 'center', gap: 8,
                    background: env === 'production' ? T.accentBg : T.amberBg,
                    border: `1px solid ${env === 'production' ? T.accentBorder : 'rgba(251,191,36,0.2)'}`,
                    borderRadius: 6, padding: '6px 14px', fontSize: 12, fontFamily: T.mono,
                }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: env === 'production' ? '#10b981' : T.amber, animation: 're-pulse-dot 2s ease-in-out infinite' }} />
                    <span style={{ color: T.textMuted }}>Base URL:</span>
                    <span style={{ color: env === 'production' ? T.accent : T.amber, fontWeight: 600 }}>{baseUrl}</span>
                </div>
            </div>
        </>
    );
}
