const config = {
    darkMode: "class",
    content: [
        './pages/**/*.{ts,tsx}',
        './components/**/*.{ts,tsx}',
        './app/**/*.{ts,tsx}',
        './src/**/*.{ts,tsx}',
    ],
    prefix: "",
    theme: {
        container: {
            center: true,
            padding: "2rem",
            screens: {
                "2xl": "1400px",
            },
        },
        extend: {
            fontFamily: {
                sans: ["var(--re-font-sans)"],
                display: ["var(--re-font-display)"],
                serif: ["var(--re-font-serif)"],
                mono: ["var(--re-font-mono)"],
            },
            colors: {
                border: "hsl(var(--border))",
                input: "hsl(var(--input))",
                ring: "hsl(var(--ring))",
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                primary: {
                    DEFAULT: "hsl(var(--primary))",
                    foreground: "hsl(var(--primary-foreground))",
                },
                secondary: {
                    DEFAULT: "hsl(var(--secondary))",
                    foreground: "hsl(var(--secondary-foreground))",
                },
                destructive: {
                    DEFAULT: "hsl(var(--destructive))",
                    foreground: "hsl(var(--destructive-foreground))",
                },
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                accent: {
                    DEFAULT: "hsl(var(--accent))",
                    foreground: "hsl(var(--accent-foreground))",
                },
                popover: {
                    DEFAULT: "hsl(var(--popover))",
                    foreground: "hsl(var(--popover-foreground))",
                },
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
                // RegEngine semantic tokens
                "re-brand": "var(--re-brand)",
                "re-brand-dark": "var(--re-brand-dark)",
                "re-brand-light": "var(--re-brand-light)",
                "re-success": "var(--re-success)",
                "re-success-muted": "var(--re-success-muted)",
                "re-warning": "var(--re-warning)",
                "re-warning-muted": "var(--re-warning-muted)",
                "re-danger": "var(--re-danger)",
                "re-danger-muted": "var(--re-danger-muted)",
                "re-info": "var(--re-info)",
                "re-info-muted": "var(--re-info-muted)",
                "re-surface": {
                    base: "var(--re-surface-base)",
                    card: "var(--re-surface-card)",
                    elevated: "var(--re-surface-elevated)",
                    overlay: "var(--re-surface-overlay)",
                    inset: "var(--re-surface-inset)",
                },
                "re-text": {
                    primary: "var(--re-text-primary)",
                    secondary: "var(--re-text-secondary)",
                    tertiary: "var(--re-text-tertiary)",
                    muted: "var(--re-text-muted)",
                    disabled: "var(--re-text-disabled)",
                },
                "re-border": {
                    DEFAULT: "var(--re-border-default)",
                    subtle: "var(--re-border-subtle)",
                    strong: "var(--re-border-strong)",
                },
                // Added by the redesign (SPEC §1). Every entry maps to a token
                // defined for BOTH themes in globals.css.
                "re-brand-muted": "var(--re-brand-muted)",
                "re-brand-foreground": "var(--re-brand-foreground)",
                "re-danger-foreground": "var(--re-danger-foreground)",
                "re-success-bg": "var(--re-success-bg)",
                "re-success-border": "var(--re-success-border)",
                "re-warning-bg": "var(--re-warning-bg)",
                "re-warning-border": "var(--re-warning-border)",
                "re-danger-bg": "var(--re-danger-bg)",
                "re-danger-border": "var(--re-danger-border)",
                "re-info-bg": "var(--re-info-bg)",
                "re-info-border": "var(--re-info-border)",
                "re-focus-ring": "var(--re-focus-ring)",
                "re-ring-offset": "var(--re-ring-offset)",
                // Compliance-object state vocabulary
                "re-state-corrected": "var(--re-state-corrected)",
                "re-state-corrected-bg": "var(--re-state-corrected-bg)",
                "re-state-corrected-border": "var(--re-state-corrected-border)",
                // Categorical encoding only (facility types, graph nodes) — never status.
                "re-cat-1": "var(--re-cat-1)",
                "re-cat-2": "var(--re-cat-2)",
                "re-cat-3": "var(--re-cat-3)",
                "re-cat-4": "var(--re-cat-4)",
                "re-cat-5": "var(--re-cat-5)",
                "re-cat-6": "var(--re-cat-6)",
            },
            boxShadow: {
                "re-sm": "var(--re-shadow-sm)",
                "re-md": "var(--re-shadow-md)",
                "re-lg": "var(--re-shadow-lg)",
                "re-glow": "var(--re-shadow-glow)",
                "re-glow-strong": "var(--re-shadow-glow-strong)",
            },
            // Pinned to flat values (SPEC §5.1). This REPLACES the previous
            // calc(var(--radius)) chain, moving rounded-lg from 6px to 8px —
            // intended: 8px is the card/table/tile radius. `--radius` is still
            // defined for anything reading it directly, but no longer drives
            // this scale. Defaults like rounded-full / rounded-none survive
            // because these keys sit in `extend`.
            borderRadius: {
                sm: "4px",
                md: "6px",
                lg: "8px",
                xl: "12px",
                "2xl": "12px",
            },
            // The 8-step type scale (SPEC §2.2). Declared here, in rem, so that
            // html.a11y-font-large / -xl (which scale the root font-size) keep
            // enlarging every primitive.
            fontSize: {
                display: ["clamp(2rem, 4.2vw, 2.75rem)", { lineHeight: "1.05", fontWeight: "600", letterSpacing: "-0.02em" }],
                "heading-lg": ["clamp(1.5rem, 2.6vw, 2rem)", { lineHeight: "1.2", fontWeight: "600", letterSpacing: "-0.015em" }],
                title: ["1.75rem", { lineHeight: "2.125rem", fontWeight: "600", letterSpacing: "-0.015em" }],
                heading: ["1.25rem", { lineHeight: "1.75rem", fontWeight: "600", letterSpacing: "-0.01em" }],
                subheading: ["0.9375rem", { lineHeight: "1.375rem", fontWeight: "600" }],
                body: ["1rem", { lineHeight: "1.625rem" }],
                ui: ["0.875rem", { lineHeight: "1.25rem" }],
                small: ["0.75rem", { lineHeight: "1rem" }],
                label: ["0.6875rem", { lineHeight: "1rem", fontWeight: "500", letterSpacing: "0.04em" }],
            },
            transitionDuration: {
                120: "120ms",
                180: "180ms",
                240: "240ms",
            },
            transitionTimingFunction: {
                re: "cubic-bezier(.2, 0, 0, 1)",
            },
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
}

module.exports = config
