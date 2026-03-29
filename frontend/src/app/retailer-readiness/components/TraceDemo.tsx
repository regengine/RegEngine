'use client';

import { RefObject } from 'react';
import { T } from './constants';

interface TraceNode {
    label: string;
    sublabel: string;
    icon: string;
    kde: string;
}

export interface TraceDemoProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
    traceRef: RefObject<HTMLDivElement>;
    traceDirection: 'forward' | 'backward';
    setTraceDirection: (dir: 'forward' | 'backward') => void;
    traceNodes: TraceNode[];
    traceStep: number;
    traceComplete: boolean;
    setTraceStarted: (started: boolean) => void;
    setTraceStep: (step: number) => void;
    setTraceComplete: (complete: boolean) => void;
    startTrace: () => void;
    trackEvent: (event: string, data?: Record<string, unknown>) => void;
}

export default function TraceDemo({
    revealRef, visible, traceRef, traceDirection, setTraceDirection,
    traceNodes, traceStep, traceComplete,
    setTraceStarted, setTraceStep, setTraceComplete, startTrace, trackEvent,
}: TraceDemoProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 900, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div className="text-center mb-12">
                <p className="re-section-label">
                    Trace Demo
                </p>
                <h2 className="re-section-title">
                    {traceDirection === 'forward' ? '5-Second Trace. Farm to Store.' : '5-Second Trace. Store to Farm.'}
                </h2>
                <p style={{ fontSize: 15, color: T.textMuted, maxWidth: 520, margin: '0 auto', marginBottom: 24 }}>
                    {traceDirection === 'forward'
                        ? 'Watch a romaine lettuce lot trace across the entire supply chain in an animated walkthrough.'
                        : 'Simulate a recall investigation — trace a contaminated product back to its source in seconds.'}
                </p>

                {/* Direction toggle */}
                <div style={{
                    display: 'inline-flex', background: T.surface,
                    border: `1px solid ${T.border}`, borderRadius: 10, padding: 3,
                }}>
                    {(['forward', 'backward'] as const).map((dir) => (
                        <button
                            key={dir}
                            onClick={() => {
                                if (dir !== traceDirection) {
                                    setTraceDirection(dir);
                                    setTraceStarted(false);
                                    setTraceStep(-1);
                                    setTraceComplete(false);
                                    trackEvent('trace_direction_switch', { direction: dir });
                                }
                            }}
                            style={{
                                padding: '10px 20px', fontSize: 13, fontWeight: 600,
                                border: 'none', borderRadius: 8, cursor: 'pointer',
                                background: traceDirection === dir ? `${T.accent}15` : 'transparent',
                                color: traceDirection === dir ? T.accent : T.textDim,
                                transition: 'all 0.2s', minHeight: 44,
                            }}
                        >
                            {dir === 'forward' ? '🌱 → 🏪  Forward' : '🚨 → 🎯  Backward'}
                        </button>
                    ))}
                </div>
            </div>

            <div ref={traceRef} style={{
                background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                padding: 'clamp(1rem, 3vw, 32px) clamp(0.75rem, 2vw, 24px)', overflow: 'hidden',
                borderTop: `3px solid ${T.accent}`,
                boxShadow: `0 4px 24px rgba(0,0,0,0.12), 0 0 0 1px ${T.border}`,
            }}>
                {/* Terminal header */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24,
                    paddingBottom: 16, borderBottom: `1px solid ${T.border}`,
                }}>
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--re-danger)' }} />
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--re-warning)' }} />
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--re-success)' }} />
                    <span style={{
                        marginLeft: 12, fontSize: 12, color: T.textDim,
                        fontFamily: "'JetBrains Mono', monospace",
                    }}>
                        regengine trace --lot TLC-2026-0412 --direction {traceDirection}
                    </span>
                </div>

                {/* Trace nodes */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                    {traceNodes.map((node, i) => {
                        const active = i <= traceStep;
                        const current = i === traceStep && !traceComplete;
                        return (
                            <div key={node.label}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 'clamp(10px, 2vw, 16px)', padding: 'clamp(10px, 2vw, 14px) clamp(10px, 2vw, 16px)',
                                    borderRadius: 10,
                                    background: current ? `${T.accent}10` : active ? `${T.accent}04` : 'transparent',
                                    border: current ? `1px solid ${T.accent}30` : '1px solid transparent',
                                    opacity: active ? 1 : 0.3,
                                    transform: active ? 'translateX(0)' : 'translateX(-8px)',
                                    transition: 'all 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
                                }}>
                                    {/* Step indicator */}
                                    <div style={{
                                        width: 44, height: 44, borderRadius: 12,
                                        background: active ? `${T.accent}15` : T.surface,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        fontSize: 20, flexShrink: 0,
                                        border: current ? `1px solid ${T.accent}40` : '1px solid transparent',
                                        boxShadow: current ? `0 0 16px ${T.accent}20` : 'none',
                                    }}>
                                        {node.icon}
                                    </div>

                                    {/* Info */}
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <p style={{
                                            fontSize: 14, fontWeight: 600,
                                            color: active ? T.heading : T.textDim,
                                            transition: 'color 0.3s',
                                        }}>
                                            {node.label}
                                        </p>
                                        <p style={{ fontSize: 12, color: T.textDim }}>{node.sublabel}</p>
                                    </div>

                                    {/* KDE */}
                                    <div className="hidden sm:block" style={{
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: 11, color: active ? T.accent : T.textDim,
                                        opacity: active ? 1 : 0,
                                        transition: 'all 0.5s',
                                    }}>
                                        {node.kde}
                                    </div>

                                    {/* Status */}
                                    <div style={{
                                        fontSize: 12, fontWeight: 600,
                                        color: active ? T.accent : T.textDim,
                                        opacity: active ? 1 : 0,
                                        transition: 'opacity 0.3s',
                                    }}>
                                        ✓
                                    </div>
                                </div>

                                {/* Connector line */}
                                {i < traceNodes.length - 1 && (
                                    <div style={{
                                        width: 2, height: 12, marginLeft: 37,
                                        background: active ? `${T.accent}40` : T.border,
                                        transition: 'background 0.5s',
                                    }} />
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Completion banner */}
                <div style={{
                    marginTop: 20, padding: '14px 18px',
                    background: traceComplete ? `${T.accent}08` : 'transparent',
                    border: `1px solid ${traceComplete ? `${T.accent}20` : 'transparent'}`,
                    borderRadius: 10,
                    opacity: traceComplete ? 1 : 0,
                    transform: traceComplete ? 'translateY(0)' : 'translateY(8px)',
                    transition: 'all 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
                }}>
                    <div className="flex items-center justify-between">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{ fontSize: 16 }}>{traceDirection === 'forward' ? '⚡' : '🎯'}</span>
                            <span style={{ fontSize: 14, fontWeight: 600, color: traceDirection === 'forward' ? T.accent : T.warning }}>
                                {traceDirection === 'forward' ? 'Full trace complete' : 'Source identified'}
                            </span>
                        </div>
                        <div style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: 13, color: T.heading, fontWeight: 600,
                        }}>
                            {traceDirection === 'forward' ? '3.2 seconds' : '2.8 seconds'}
                        </div>
                    </div>
                    <p style={{ fontSize: 12, color: T.textMuted, marginTop: 6, marginLeft: 26 }}>
                        {traceDirection === 'forward'
                            ? '5 CTEs verified · All KDEs captured · SHA-256 hash chain intact'
                            : 'Source farm isolated · Lot #0412 flagged · All affected shipments identified'}
                    </p>
                </div>

                {/* Replay button */}
                <button
                    onClick={() => {
                        setTraceStarted(false);
                        setTraceStep(-1);
                        setTraceComplete(false);
                        setTimeout(() => startTrace(), 100);
                    }}
                    style={{
                        display: 'block', margin: '20px auto 0', padding: '12px 24px',
                        background: 'transparent', border: `1px solid ${T.border}`,
                        borderRadius: 10, color: T.textMuted, fontSize: 14, cursor: 'pointer',
                        transition: 'all 0.2s', minHeight: 48,
                    }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = T.borderHover; e.currentTarget.style.color = T.text; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.textMuted; }}
                >
                    ↻ Replay {traceDirection} trace
                </button>
            </div>
        </section>
    );
}
