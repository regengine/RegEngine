import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

/** Selector text of every rule in the sheet (crude but sufficient: no @media nesting in selectors). */
function selectors(): string[] {
    return [...CSS.matchAll(/([^{}]+)\{/g)]
        .map((m) => m[1].replace(/\s+/g, ' ').trim())
        .filter((s) => s && !s.startsWith('@') && !s.startsWith('/*'));
}

describe('globals.css invariants', () => {
    // Position-indexed selectors land on whichever section occupies the slot,
    // not on one that asked for the layout. The dashboard composes and reorders
    // its own sections, so these rules must never reach it: in #2768 they forced
    // `display: grid` onto component internals and scattered a card's heading,
    // badge and body into separate columns. Three rules were scoped then; two
    // more inside media queries were missed and set inert grid tracks on the
    // evidence chain until this test was written.
    it('never applies a position-indexed section rule in dashboard mode', () => {
        const positional = selectors().filter(
            (s) => /\bsection:(first-of-type|nth-of-type)\b/.test(s) && s.includes('[data-inflow-lab-app]'),
        );

        expect(positional.length).toBeGreaterThan(0); // guard against the regex silently going stale

        const unguarded = positional.filter((s) => {
            // Every comma-separated part that is position-indexed must carry the exclusion.
            return s
                .split(',')
                .map((part) => part.trim())
                .filter((part) => /\bsection:(first-of-type|nth-of-type)\b/.test(part))
                .some((part) => !part.includes(':not([data-inflow-lab-mode="dashboard"])'));
        });

        expect(unguarded).toEqual([]);
    });

    // Zeroing only `animation-duration` leaves a staggered reveal invisible for
    // the whole `animation-delay` before it pops in — `fill-mode: backwards`
    // holds the hidden first frame. Reduced motion must not read as "content
    // missing", so the delay has to be zeroed too.
    it('zeroes animation and transition delay under prefers-reduced-motion', () => {
        const block = CSS.match(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/);
        expect(block, 'reduced-motion block not found').not.toBeNull();

        const body = block![0];
        expect(body).toMatch(/animation-duration:\s*0[.\d]*m?s\s*!important/);
        expect(body).toMatch(/animation-delay:\s*0m?s\s*!important/);
        expect(body).toMatch(/transition-delay:\s*0m?s\s*!important/);
    });
});
