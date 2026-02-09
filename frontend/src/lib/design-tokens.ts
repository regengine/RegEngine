/* ─────────────────────────────────────────────────────────────
   REGENGINE DESIGN TOKENS
   Unified design system for all marketing pages
   ───────────────────────────────────────────────────────────── */

export const tokens = {
    // ─── BACKGROUNDS ───
    bg: '#06090f',                              // Primary dark background
    surface: 'rgba(255,255,255,0.02)',          // Card/section surfaces
    surfaceHover: 'rgba(255,255,255,0.04)',     // Hover state for surfaces
    surfaceActive: 'rgba(255,255,255,0.06)',    // Active/pressed state

    // ─── BORDERS ───
    border: 'rgba(255,255,255,0.06)',           // Standard border
    borderSubtle: 'rgba(255,255,255,0.03)',     // Subtle dividers
    borderStrong: 'rgba(255,255,255,0.10)',     // Emphasized borders

    // ─── TEXT COLORS ───
    text: '#c8d1dc',                            // Primary text
    textMuted: '#64748b',                       // Secondary/muted text
    textDim: '#475569',                         // Tertiary/dimmed text
    heading: '#e2e8f0',                         // Headings and emphasis

    // ─── ACCENT COLORS ───
    accent: '#10b981',                          // Primary emerald accent
    accentHover: '#059669',                     // Accent hover state
    accentBg: 'rgba(16,185,129,0.1)',           // Accent background/badge
    accentBorder: 'rgba(16,185,129,0.2)',       // Accent borders

    // ─── STATUS COLORS ───
    warning: '#f59e0b',                         // Amber warning
    warningBg: 'rgba(245,158,11,0.1)',          // Warning background
    warningBorder: 'rgba(245,158,11,0.2)',      // Warning border
    danger: '#ef4444',                          // Red danger/error
    dangerBg: 'rgba(239,68,68,0.1)',            // Danger background
    success: '#10b981',                         // Green success (same as accent)
    successBg: 'rgba(16,185,129,0.1)',          // Success background

    // ─── TYPOGRAPHY ───
    fontSans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    fontMono: "'JetBrains Mono', monospace",

    // ─── SPACING ───
    maxWidth: '1120px',                         // Standard content max-width
    sectionPadding: '60px 24px',                // Standard section padding
    cardPadding: '24px',                        // Standard card padding
    cardRadius: '12px',                         // Standard card border radius
} as const;

// Type export for TypeScript consumers
export type Tokens = typeof tokens;

// Commonly used style objects
export const noiseOverlay = {
    position: 'fixed' as const,
    inset: 0,
    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
    opacity: 0.015,
    pointerEvents: 'none' as const,
    zIndex: 1,
};

export const accentGlow = {
    position: 'absolute' as const,
    top: '-60px',
    left: '50%',
    transform: 'translateX(-50%)',
    width: '600px',
    height: '400px',
    background: `radial-gradient(ellipse, ${tokens.accent}08 0%, transparent 70%)`,
    pointerEvents: 'none' as const,
};

// Shorthand alias
export const T = tokens;
