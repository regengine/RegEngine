import type { Config } from "tailwindcss"

const config = {
    darkMode: ["class"],
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
            },
            boxShadow: {
                "re-sm": "var(--re-shadow-sm)",
                "re-md": "var(--re-shadow-md)",
                "re-lg": "var(--re-shadow-lg)",
                "re-glow": "var(--re-shadow-glow)",
                "re-glow-strong": "var(--re-shadow-glow-strong)",
            },
            borderRadius: {
                lg: "var(--radius)",
                md: "calc(var(--radius) - 2px)",
                sm: "calc(var(--radius) - 4px)",
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
} satisfies Config

export default config
