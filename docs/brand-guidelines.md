# RegEngine Brand Guidelines

> Regulatory compliance infrastructure for food safety teams.
> These guidelines define how RegEngine presents itself across product, marketing, and communications.

**Version:** 1.0
**Last updated:** April 2026
**Owner:** Christopher Sellers

---

## Table of Contents

- [Logo & Wordmark](#logo--wordmark)
- [Color System](#color-system)
- [Typography](#typography)
- [Voice & Tone](#voice--tone)
- [Product Terminology](#product-terminology)
- [UI Design Patterns](#ui-design-patterns)
- [Spacing & Layout](#spacing--layout)
- [Market Positioning](#market-positioning)

---

## Logo & Wordmark

The wordmark uses a camelCase split: **Reg** in the primary text color, **Engine** in emerald green (`var(--re-brand)`). The icon represents layered traceability -- stacked data planes flowing through the compliance stack.

The wordmark is rendered by the `RegEngineWordmark` component (`src/components/layout/regengine-wordmark.tsx`), which is the single source of truth for all wordmark rendering across the site.

### Usage Rules

**Do:**
- Use on clean backgrounds with sufficient contrast
- Maintain clear space equal to the icon height on all sides
- Use the full wordmark + icon in primary placements
- Always use the `RegEngineWordmark` component -- never render the brand name as plain text

**Don't:**
- Stretch, rotate, or recolor the logo
- Place on busy or low-contrast backgrounds
- Separate the icon from the wordmark in primary placements
- Use the icon alone without establishing brand context first
- Render the wordmark in a different font or without the emerald split

---

## Color System

All colors are defined as CSS custom properties (`--re-*`) in `globals.css` and consumed via Tailwind or inline styles. Never use hardcoded hex values in components -- always reference the token.

### Primary Palette -- Emerald

Emerald green is the core brand color. It signals trust, safety, and compliance readiness.

| Token         | Dark Mode   | Light Mode  | Usage                                          |
|---------------|-------------|-------------|-------------------------------------------------|
| `--re-brand`       | `#10b981` | `#047857` | Primary CTAs, interactive elements, key actions |
| `--re-brand-dark`  | `#059669` | `#065f46` | Hover states                                    |
| `--re-brand-light` | `#34d399` | `#10b981` | Accents, highlights                             |
| `--re-brand-muted` | `rgba(16,185,129,0.1)` | `rgba(4,120,87,0.08)` | Badge backgrounds, subtle highlights |

### Neutral Palette -- Slate

| Token                    | Dark Mode   | Light Mode  | Usage                              |
|--------------------------|-------------|-------------|------------------------------------|
| `--re-surface-base`      | `#06090f`  | `#ffffff`   | Page background                    |
| `--re-surface-card`      | `#0c1017`  | `#f8fafc`   | Card backgrounds                   |
| `--re-surface-elevated`  | `#111827`  | `#f1f5f9`   | Elevated surfaces, footer          |
| `--re-text-primary`      | `#f8fafc`  | `#0f172a`   | Headings, primary text             |
| `--re-text-secondary`    | `#c8d1dc`  | `#334155`   | Body copy                          |
| `--re-text-tertiary`     | `#94a3b8`  | `#64748b`   | Descriptions, placeholders         |
| `--re-text-muted`        | `#8b9bb5`  | `#94a3b8`   | Nav links, labels, captions        |
| `--re-text-disabled`     | `#6b7a8d`  | `#cbd5e1`   | Disabled text                      |
| `--re-border-default`    | `#1e293b`  | `#e2e8f0`   | Default borders                    |
| `--re-border-subtle`     | `#131a27`  | `#f1f5f9`   | Subtle separators                  |

### Semantic Colors

| State          | Dark Mode   | Light Mode  | Usage                                      |
|----------------|-------------|-------------|--------------------------------------------|
| `--re-danger`  | `#ef4444`  | `#dc2626`   | Non-compliance, critical findings, errors   |
| `--re-warning` | `#f59e0b`  | `#d97706`   | Approaching deadlines, at-risk obligations  |
| `--re-success` | `#10b981`  | `#15803d`   | Compliant status, passed checks             |
| `--re-info`    | `#3b82f6`  | `#1d4ed8`   | Informational states, links, neutral alerts |

**Compliance context:** In the regulatory domain, red and amber carry specific weight. Red means non-compliance or critical audit findings. Amber means approaching deadlines or at-risk status. Green doubles as brand color and compliance-passed indicator. Blue is reserved for informational states and links.

### Dark Mode

Dark mode is the default. All colors must work in both light and dark mode. Use CSS custom properties (`--re-*`) rather than hardcoded hex values in components. Semantic color backgrounds should use the `*-muted` token variants on dark surfaces.

---

## Typography

### Font Stack

| Context              | Font                          | CSS Variable              | Weight   | Notes                                    |
|----------------------|-------------------------------|---------------------------|----------|------------------------------------------|
| Display headlines    | Outfit                        | `--font-outfit` / `font-display` | 500-700  | Hero headlines, section headings         |
| Body text & UI       | Inter                         | `--font-inter` / `font-sans`    | 400-600  | Default sans-serif, line height 1.6-1.7  |
| Serif accents        | Fraunces                      | `--font-fraunces` / `font-serif` | 300-700  | Testimonial quotes, editorial flourishes |
| Wordmark             | Instrument Sans               | `--font-instrument-sans`         | 700      | Brand wordmark only                      |
| Code & data values   | JetBrains Mono                | `--font-jetbrains-mono` / `font-mono` | 400-500 | Lot IDs, hash chains, API responses, section labels |

### Type Scale

| Element            | Size             | Font      | Weight | Tracking   |
|--------------------|------------------|-----------|--------|------------|
| Hero headline      | `clamp(2rem, 5vw, 3.25rem)` | Outfit | 700 | tight |
| Section heading    | `clamp(1.5rem, 3.5vw, 2.25rem)` | Outfit | 700 | tight |
| Section label      | 12px (0.75rem)   | JetBrains Mono | 500 | widest, uppercase |
| Card heading       | 16-18px          | Inter     | 500    | normal     |
| Body               | 14-16px          | Inter     | 400    | normal     |
| Caption / metadata | 12-13px          | Inter     | 400    | normal     |
| Badge / pill text  | 12px             | JetBrains Mono | 500 | normal  |

### Rules

- Use sentence case everywhere -- never Title Case or ALL CAPS in UI text (exception: section labels in `font-mono` may use uppercase with wide tracking)
- Monospace font is mandatory for: lot IDs, SHA-256 hashes, API keys, timestamps, event IDs, section labels
- Never use more than two font weights on a single card or component
- Line length should not exceed 720px for marketing prose, 640px for dashboard text

---

## Voice & Tone

RegEngine speaks as a trusted technical partner -- not a vendor pitching features. The voice is confident, specific, and grounded in regulatory reality.

### Brand Attributes

- **Authoritative** -- We cite specific regulations and know the domain deeply
- **Precise** -- We use exact terms, not approximations
- **Urgent** -- Deadlines are real; we treat them as engineering problems
- **Trustworthy** -- Our audit trail is cryptographic; our language matches that standard
- **Builder-minded** -- This is a founder-built product with conviction

### Voice Principles

**Authoritative, not academic.**
We cite specific regulations (FSMA 204, 21 CFR Part 1, Subpart S) and know the difference between a CTE and a KDE. We don't hedge with "may" or "could" -- we state what the rule requires.

**Urgent, not alarmist.**
"You have 24 hours to respond" is a fact, not a scare tactic. We frame deadlines as engineering problems to solve, not reasons to panic.

**Technical, not jargon-heavy.**
We say "hash-chained audit trail" because that's what it is. We explain it once, then use the term confidently. We never dumb it down or dress it up.

**Founder-direct.**
Copy can reference the builder's perspective: "I built RegEngine because..." -- this is a solo-founder product with conviction. No corporate "we believe" abstractions.

### Examples

**Write like this:**
> "When the FDA or Walmart demands your traceability records, you have 24 hours to respond with a complete chain of custody. RegEngine gets you there in minutes."

**Not like this:**
> "Our cutting-edge platform leverages advanced AI and blockchain-inspired technology to revolutionize food safety compliance management solutions."

**Write like this:**
> "Every CTE is SHA-256 hashed and chain-linked. Tampering breaks the chain. Your auditor can verify it."

**Not like this:**
> "We use state-of-the-art cryptographic security to ensure your data is safe and secure at all times."

---

## Product Terminology

### Standard Terms -- Always Use

| Term               | Definition                                                                 |
|--------------------|---------------------------------------------------------------------------|
| CTE                | Critical Tracking Event (harvesting, cooling, packing, receiving, shipping, transformation) |
| KDE                | Key Data Element (lot code, ship-to, ship-from, quantity, unit of measure) |
| FTL                | FDA Food Traceability List                                                 |
| Lot tracing        | Forward/backward trace across supply chain -- not "product tracking"       |
| Audit trail        | Immutable, hash-chained event log -- not "log" or "history"               |
| Workspace          | A tenant's isolated environment                                            |
| Readiness score    | Compliance assessment output -- not "grade" or "rating"                   |
| Obligation         | A specific regulatory requirement mapped from source text                  |
| Recall drill       | Simulated recall exercise to test response time                           |
| Chain of custody   | Complete lot trace from origin to destination                              |

### Terms to Avoid

| Avoid              | Why                                                                        | Use Instead          |
|--------------------|---------------------------------------------------------------------------|----------------------|
| Blockchain         | We use hash chains, which are cryptographic but not blockchain             | Hash-chained / SHA-256 verified |
| AI-powered         | NLP is a feature, not the identity                                         | Name the specific capability |
| End-to-end         | Vague without specifying what "ends"                                       | "From harvest to distribution" or name the specific endpoints |
| Seamless           | Every integration has edges; be specific                                   | Describe what's automated |
| Solution           | Generic enterprise-speak                                                   | Platform / system / tool |
| Leverage           | Corporate jargon                                                           | Use / apply / build on |
| Revolutionary      | Overpromise                                                                | Be specific about the improvement |

---

## UI Design Patterns

### Component System

Built on **Radix UI** primitives + **Tailwind CSS** utility classes. Components follow **shadcn/ui** patterns with RegEngine's emerald color system applied. State management via **TanStack Query**, tables via **TanStack Table**, auth via **Supabase Auth**.

### Component Tokens

| Component          | Background               | Border                        | Radius | Padding      |
|--------------------|--------------------------|-------------------------------|--------|--------------|
| Card               | `--re-surface-card`      | 0.5px `--re-border-default`   | 8px    | 16-20px      |
| Primary button     | `--re-brand`             | none                          | 6px    | 8px 16px     |
| Secondary button   | transparent              | 0.5px `--re-border-default`   | 6px    | 8px 16px     |
| Input field        | `--re-surface-base`      | 0.5px `--re-border-default`   | 6px    | 8px 12px     |
| Status badge       | semantic `*-muted` token | none                          | 999px  | 2px 8px      |
| Modal              | `--re-surface-card`      | 0.5px `--re-border-default`   | 12px   | 24px         |

### Status Badge System

```
Compliant     -> --re-success-muted bg + success text
At Risk       -> --re-warning-muted bg + warning text
Non-Compliant -> --re-danger-muted bg + danger text
Pending       -> slate-muted bg + muted text
In Progress   -> --re-info-muted bg + info text
```

### Dashboard Conventions

- Compliance scores use radial progress indicators in emerald
- Obligation status uses a three-state system: compliant (green), at-risk (amber), non-compliant (red)
- Lot trace views use tree/graph layouts, not flat tables
- Timestamps always include timezone, formatted ISO 8601
- Hash values display first 8 + last 4 characters with ellipsis: `7a3f82b1...c4d9`
- All data tables support sort, filter, and export

---

## Spacing & Layout

### Grid System

| Token            | Value   | Usage                                         |
|------------------|---------|-----------------------------------------------|
| Base unit        | 4px     | All spacing derives from 4px increments       |
| Component gap    | 12-16px | Between sibling cards or form fields          |
| Card padding     | 16px    | Compact variant                               |
| Card padding     | 20px    | Standard variant                              |
| Card padding     | 24px    | Spacious variant                              |
| Section spacing  | 48-64px | Between major sections on marketing pages     |
| Content max-width| 1280px  | Dashboard layout                              |
| Prose max-width  | 720px   | Marketing and documentation text              |

### Spacing Scale

```
4px  -- tight internal gaps (icon-to-text)
8px  -- compact padding, small gaps
12px -- standard component gaps
16px -- card padding (compact), section internal spacing
20px -- card padding (standard)
24px -- card padding (spacious), major internal sections
32px -- between related content groups
48px -- between distinct sections
64px -- major page sections on marketing
```

---

## Market Positioning

### Target Customer

Mid-size food manufacturers and distributors ($5M-$250M revenue) currently tracking traceability in spreadsheets, email, or paper. Shipping to Walmart, Kroger, Costco, or similar retailers who enforce FSMA 204 compliance. Need to prove compliance but don't have a system yet.

### Anti-Personas (Not For)

- Enterprise companies already on SAP, TraceLink, or similar platforms
- Pre-revenue startups not yet shipping product
- Restaurants or food service (FSMA 204 applies to manufacturing/distribution)
- Companies already passing retailer audits with their current system

### Competitive Frame

RegEngine replaces the compliance spreadsheet -- not the ERP. Position against manual processes and consultant-dependent audits, not against enterprise platforms.

### Key Proof Points

- 5+ founding partners in food manufacturing and distribution
- 10,000+ CTEs processed
- Zero FDA findings among partners
- EPCIS 2.0 native
- SHA-256 verified chains
- SOC 2 Type I in progress (target Q3 2026)

### Headline Formulas

```
[Timeframe] + [specific outcome] + [without the old way]

"Get FDA-ready in minutes, not months."
"24-hour FDA response deadline. RegEngine gets you there in minutes."
"Retailer-ready in 30 days -- not 12 months."
```

---

## Implementation Reference

| Artifact | Location |
|----------|----------|
| Brand guidelines (this doc) | `docs/brand-guidelines.md` |
| CSS design tokens | `frontend/src/app/globals.css` |
| TypeScript design tokens | `frontend/src/design-system/tokens.ts` |
| Design system docs | `frontend/src/styles/DESIGN_SYSTEM.md` |
| Wordmark component | `frontend/src/components/layout/regengine-wordmark.tsx` |

Agent personas (especially `.agent/personas/ui.md`) should reference this document for all visual and voice decisions.

---

*Proprietary. All rights reserved. Built by Christopher Sellers.*
