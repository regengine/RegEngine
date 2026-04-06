/**
 * RegEngine Design Tokens — TypeScript Constants
 *
 * Auto-generated from design-tokens.json
 * Usage: import { colors, spacing, typography } from '@/design-system/tokens'
 */

// ─── Colors ─────────────────────────────────────────────────────────────────

export const colors = {
    brand: {
        emerald: '#10b981',
        emeraldDark: '#059669',
        emeraldLight: '#34d399',
    },
    bg: {
        base: '#06090f',
        surface: '#0c1017',
        elevated: '#111827',
        overlay: 'rgba(6, 9, 15, 0.80)',
    },
    text: {
        primary: '#f8fafc',
        secondary: '#c8d1dc',
        tertiary: '#94a3b8',
        muted: '#64748b',
        disabled: '#475569',
    },
    border: {
        default: '#1e293b',
        subtle: '#334155',
        strong: '#475569',
    },
    status: {
        success: '#22c55e',
        successMuted: 'rgba(34, 197, 94, 0.15)',
        warning: '#f59e0b',
        warningMuted: 'rgba(245, 158, 11, 0.15)',
        danger: '#ef4444',
        dangerMuted: 'rgba(239, 68, 68, 0.15)',
        info: '#60a5fa',
        infoMuted: 'rgba(96, 165, 250, 0.15)',
    },
    accent: {
        blue: '#3b82f6',
        purple: '#a855f7',
        cyan: '#06b6d4',
        pink: '#ec4899',
        amber: '#fbbf24',
    },
} as const

// ─── Spacing ────────────────────────────────────────────────────────────────

export const spacing = {
    0: '0',
    px: '1px',
    0.5: '0.125rem',
    1: '0.25rem',
    1.5: '0.375rem',
    2: '0.5rem',
    3: '0.75rem',
    4: '1rem',
    5: '1.25rem',
    6: '1.5rem',
    8: '2rem',
    10: '2.5rem',
    12: '3rem',
    16: '4rem',
    20: '5rem',
    24: '6rem',
} as const

// ─── Typography ─────────────────────────────────────────────────────────────

export const typography = {
    fontFamily: {
        sans: "'Instrument Sans', system-ui, -apple-system, sans-serif",
        mono: "'JetBrains Mono', 'Fira Code', monospace",
    },
    fontSize: {
        xs: '0.75rem',
        sm: '0.875rem',
        base: '1rem',
        lg: '1.125rem',
        xl: '1.25rem',
        '2xl': '1.5rem',
        '3xl': '1.875rem',
        '4xl': '2.25rem',
        '5xl': '3rem',
        '6xl': '3.75rem',
    },
    fontWeight: {
        normal: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
    },
} as const

// ─── Shadows ────────────────────────────────────────────────────────────────

export const shadows = {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.3)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.4)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4)',
    glow: '0 0 20px rgba(16, 185, 129, 0.15)',
    glowStrong: '0 0 40px rgba(16, 185, 129, 0.25)',
} as const

// ─── Radii ──────────────────────────────────────────────────────────────────

export const radii = {
    none: '0',
    sm: '0.25rem',
    md: '0.5rem',
    lg: '0.75rem',
    xl: '1rem',
    '2xl': '1.5rem',
    full: '9999px',
} as const

// ─── Transitions ────────────────────────────────────────────────────────────

export const transitions = {
    fast: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
    normal: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow: '300ms cubic-bezier(0.4, 0, 0.2, 1)',
    spring: '500ms cubic-bezier(0.34, 1.56, 0.64, 1)',
} as const

// ─── Vertical Brand Colors ─────────────────────────────────────────────────

export const verticalColors = {
    aerospace: { primary: '#60a5fa', gradient: 'from-blue-500 to-sky-400' },
    automotive: { primary: '#f59e0b', gradient: 'from-amber-500 to-orange-400' },
    construction: { primary: '#f97316', gradient: 'from-orange-500 to-amber-400' },
    energy: { primary: '#3b82f6', gradient: 'from-blue-600 to-cyan-400' },
    entertainment: { primary: '#a855f7', gradient: 'from-purple-500 to-pink-400' },
    finance: { primary: '#10b981', gradient: 'from-emerald-500 to-teal-400' },
    foodSafety: { primary: '#22c55e', gradient: 'from-green-500 to-emerald-400' },
    gaming: { primary: '#ec4899', gradient: 'from-pink-500 to-rose-400' },
    healthcare: { primary: '#06b6d4', gradient: 'from-cyan-500 to-blue-400' },
    manufacturing: { primary: '#fbbf24', gradient: 'from-amber-400 to-yellow-300' },
    technology: { primary: '#3b82f6', gradient: 'from-blue-500 to-indigo-400' },
} as const

// ─── Type Helpers ───────────────────────────────────────────────────────────

export type StatusColor = keyof typeof colors.status
export type AccentColor = keyof typeof colors.accent
export type VerticalKey = keyof typeof verticalColors
export type FontSize = keyof typeof typography.fontSize
