# RegEngine Design System

> Canonical reference. Every page should look like it was designed by one person in one sitting.
> Stripe-inspired developer documentation meets Linear product feel. Dark mode default, emerald accent.

---

## Colors

All colors use CSS custom properties defined in `globals.css` and mapped to Tailwind via `tailwind.config.ts`.
**Never use hardcoded hex, rgb, or raw Tailwind color names** (e.g. `text-emerald-500`). Always use the semantic tokens.

### Brand

| Token                   | Tailwind Class          | Dark Value   | Light Value  | Use For                        |
|-------------------------|-------------------------|--------------|--------------|--------------------------------|
| `--re-brand`            | `text-re-brand`         | `#10b981`    | `#047857`    | Primary accent, CTAs, links    |
| `--re-brand-dark`       | `text-re-brand-dark`    | `#059669`    | `#065f46`    | Hover states                   |
| `--re-brand-light`      | `text-re-brand-light`   | `#34d399`    | `#059669`    | Highlights, badges             |
| `--re-brand-muted`      | `bg-re-brand-muted`     | `rgba(16,185,129,0.1)` | `rgba(4,120,87,0.08)` | Subtle backgrounds |

### Surfaces

| Token                   | Tailwind Class            | Dark Value   | Light Value  | Use For                        |
|-------------------------|---------------------------|--------------|--------------|--------------------------------|
| `--re-surface-base`     | `bg-re-surface-base`      | `#06090f`    | `#ffffff`    | Page background                |
| `--re-surface-card`     | `bg-re-surface-card`      | `#0c1017`    | `#f8fafc`    | Card backgrounds               |
| `--re-surface-elevated` | `bg-re-surface-elevated`  | `#111827`    | `#f1f5f9`    | Elevated panels, nav dropdowns |
| `--re-surface-overlay`  | `bg-re-surface-overlay`   | `rgba(6,9,15,0.80)` | `rgba(255,255,255,0.90)` | Modal overlays |

### Text

| Token                   | Tailwind Class            | Dark Value   | Light Value  | Use For                        |
|-------------------------|---------------------------|--------------|--------------|--------------------------------|
| `--re-text-primary`     | `text-re-text-primary`    | `#f8fafc`    | `#0f172a`    | Headings, primary content      |
| `--re-text-secondary`   | `text-re-text-secondary`  | `#c8d1dc`    | `#1e293b`    | Body text                      |
| `--re-text-tertiary`    | `text-re-text-tertiary`   | `#94a3b8`    | `#475569`    | Supporting text                |
| `--re-text-muted`       | `text-re-text-muted`      | `#8b9bb5`    | `#64748b`    | Captions, timestamps           |
| `--re-text-disabled`    | `text-re-text-disabled`   | `#6b7a8d`    | `#94a3b8`    | Disabled elements              |

### Borders

| Token                   | Tailwind Class            | Dark Value   | Light Value  | Use For                        |
|-------------------------|---------------------------|--------------|--------------|--------------------------------|
| `--re-border-default`   | `border-re-border`        | `#1e293b`    | `#cbd5e1`    | Card borders, dividers         |
| `--re-border-subtle`    | `border-re-border-subtle` | `#334155`    | `#e2e8f0`    | Subtle separators              |
| `--re-border-strong`    | `border-re-border-strong` | `#475569`    | `#64748b`    | Emphasized borders             |

### Status

| Token                   | Tailwind Class          | Use For                          |
|-------------------------|-------------------------|----------------------------------|
| `--re-success`          | `text-re-success`       | Success states, verified badges  |
| `--re-success-muted`    | `bg-re-success-muted`   | Success background tint          |
| `--re-warning`          | `text-re-warning`       | Warnings, pending states         |
| `--re-warning-muted`    | `bg-re-warning-muted`   | Warning background tint          |
| `--re-danger`           | `text-re-danger`        | Errors, destructive actions      |
| `--re-danger-muted`     | `bg-re-danger-muted`    | Error background tint            |
| `--re-info`             | `text-re-info`          | Informational, neutral highlights|
| `--re-info-muted`       | `bg-re-info-muted`      | Info background tint             |

### Stage Colors (Pipeline)

| Token                   | Value        | Stage          |
|-------------------------|--------------|----------------|
| `--re-discovery`        | `#3b82f6`    | Discovery      |
| `--re-decomposition`    | `#10b981`    | Decomposition  |
| `--re-linkage`          | `#a855f7`    | Linkage        |
| `--re-evidence`         | `#f59e0b`    | Evidence       |

---

## Typography

### Font Families

| Class          | Font        | Use For                                    |
|----------------|-------------|--------------------------------------------|
| `font-display` | Outfit      | All headings (h1-h4), hero text            |
| `font-sans`    | Inter       | Body text, UI labels, descriptions (default) |
| `font-serif`   | Fraunces    | Accent quotes, testimonials                |
| `font-mono`    | JetBrains Mono | Code, technical values, API references  |

### Heading Scale

| Level | Class Pattern                                           |
|-------|---------------------------------------------------------|
| h1    | `font-display text-[clamp(2rem,5vw,3.25rem)] font-bold text-[var(--re-text-primary)] leading-[1.1] tracking-tight` |
| h2    | `font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight` |
| h3    | `font-display text-lg font-semibold text-[var(--re-text-primary)]` |
| h4    | `font-display text-sm font-semibold text-[var(--re-text-primary)]` |

### Body Text

| Context   | Size      | Weight          | Color                   |
|-----------|-----------|-----------------|-------------------------|
| Primary   | `text-base` or `text-lg` | `font-normal` | `text-[var(--re-text-secondary)]` |
| Secondary | `text-sm`  | `font-normal`   | `text-[var(--re-text-tertiary)]`  |
| Caption   | `text-xs`  | `font-medium`   | `text-[var(--re-text-muted)]`     |
| Mono      | `text-xs font-mono` | `font-medium` | `text-[var(--re-text-muted)]`  |

### Allowed Font Weights

Only use: `font-normal`, `font-medium`, `font-semibold`, `font-bold`

---

## Spacing

### Section Layout

| Property           | Value                          |
|--------------------|--------------------------------|
| Container max-width | `max-w-[1200px]`              |
| Container centering | `mx-auto px-4 sm:px-6`       |
| Section padding (vertical) | `py-16 sm:py-24`      |
| Section padding (compact)  | `py-12 sm:py-16`      |

### Card Layout

| Property           | Value           |
|--------------------|-----------------|
| Internal padding   | `p-5` or `p-6`  |
| Border radius      | `rounded-xl`    |
| Border             | `border border-[var(--re-surface-border)]` |
| Background         | `bg-[var(--re-surface-card)]` |

### Standard Gaps

| Context      | Value    |
|--------------|----------|
| Grid gap     | `gap-4` or `gap-6` |
| Stack gap    | `space-y-3` or `space-y-4` |
| Inline gap   | `gap-2` or `gap-3` |
| Section gap  | `gap-8` or `gap-10` |

---

## Components

### Buttons

```
Primary:   bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-lg text-sm font-semibold
           hover:bg-[var(--re-brand-dark)] hover:shadow-re-glow active:scale-[0.98]
           transition-all duration-200 min-h-[48px]

Secondary: border border-[var(--re-border-default)] text-[var(--re-text-primary)]
           px-7 py-3.5 rounded-lg text-sm font-medium
           hover:border-[var(--re-brand)] hover:text-[var(--re-brand)]
           transition-all duration-200 min-h-[48px]

Ghost:     text-[var(--re-brand)] text-sm font-medium
           hover:text-[var(--re-brand-dark)] transition-colors
```

### Cards

```
Default:   bg-[var(--re-surface-card)] border border-[var(--re-surface-border)]
           rounded-xl p-5

Elevated:  bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)]
           rounded-xl shadow-re-md

Hoverable: ... hover:border-[var(--re-brand)]/50 hover:shadow-re-glow
           hover:-translate-y-0.5 transition-all duration-200
```

### Badges / Pills

```
Brand:     font-mono text-[0.6rem] font-semibold text-[var(--re-brand)]
           bg-[var(--re-brand-muted)] px-2 py-0.5 rounded

Status:    text-[0.6rem] font-semibold px-1.5 py-0.5 rounded-full border
           Success: bg-re-success-muted text-re-success border-re-success/20
           Warning: bg-re-warning-muted text-re-warning border-re-warning/20
           Danger:  bg-re-danger-muted  text-re-danger  border-re-danger/20
           Info:    bg-re-info-muted    text-re-info    border-re-info/20
```

### Section Label (above headings)

```
font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3
```

---

## Border Radius

| Context      | Value          |
|--------------|----------------|
| Default      | `rounded-lg`   |
| Card         | `rounded-xl`   |
| Button       | `rounded-lg`   |
| Badge/Pill   | `rounded` or `rounded-full` |
| Input        | `rounded-md`   |
| Large panel  | `rounded-2xl`  |

---

## Shadows

| Token               | Tailwind Class       | Use For                   |
|----------------------|----------------------|---------------------------|
| `--re-shadow-sm`     | `shadow-re-sm`       | Subtle elevation          |
| `--re-shadow-md`     | `shadow-re-md`       | Cards, dropdowns          |
| `--re-shadow-lg`     | `shadow-re-lg`       | Modals, popovers          |
| `--re-shadow-glow`   | `shadow-re-glow`     | Hover glow (brand)        |
| `--re-shadow-glow-strong` | `shadow-re-glow-strong` | CTA emphasis       |

---

## Migration Cheatsheet

Replace these raw Tailwind colors with semantic tokens:

| Instead of...           | Use...                  |
|-------------------------|-------------------------|
| `text-emerald-500`      | `text-re-brand`         |
| `bg-emerald-500/10`     | `bg-re-brand-muted`     |
| `text-green-500`        | `text-re-success`       |
| `bg-green-500/10`       | `bg-re-success-muted`   |
| `text-amber-500`        | `text-re-warning`       |
| `bg-amber-500/10`       | `bg-re-warning-muted`   |
| `text-red-500/600`      | `text-re-danger`        |
| `bg-red-500/10`         | `bg-re-danger-muted`    |
| `text-blue-500`         | `text-re-info`          |
| `bg-blue-500/10`        | `bg-re-info-muted`      |
| `text-gray-500/600`     | `text-muted-foreground` |
| `bg-gray-100`           | `bg-muted`              |
| `bg-[#06090f]`          | `bg-re-surface-base`    |
| `bg-[#0c1017]`          | `bg-re-surface-card`    |
| `text-white`            | `text-[var(--re-text-primary)]` |
