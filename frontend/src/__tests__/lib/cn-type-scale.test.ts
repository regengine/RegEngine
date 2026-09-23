import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

/**
 * `cn()` runs class lists through tailwind-merge, which only knows Tailwind's
 * stock size names. Our type scale (theme.extend.fontSize) is custom, so
 * without an explicit font-size class-group extension tailwind-merge reads
 * `text-ui` as a *colour* and drops it as soon as a real colour class follows.
 * That failure is silent — the element just renders at the inherited size —
 * so it needs a test rather than a code comment.
 */
const TYPE_SCALE = [
    "display",
    "heading-lg",
    "title",
    "heading",
    "subheading",
    "body",
    "ui",
    "small",
    "label",
] as const;

describe("cn() and the design-system type scale", () => {
    it.each(TYPE_SCALE)("keeps text-%s when a colour class follows it", (step) => {
        expect(cn(`text-${step}`, "text-re-text-secondary")).toBe(
            `text-${step} text-re-text-secondary`,
        );
    });

    it("still de-duplicates one scale step against another", () => {
        expect(cn("text-ui", "text-small")).toBe("text-small");
        expect(cn("text-heading", "text-display")).toBe("text-display");
    });

    it("treats stock Tailwind sizes and scale steps as the same axis", () => {
        expect(cn("text-sm", "text-ui")).toBe("text-ui");
        expect(cn("text-ui", "text-sm")).toBe("text-sm");
    });

    it("still de-duplicates colours against each other", () => {
        expect(cn("text-re-text-muted", "text-re-text-primary")).toBe("text-re-text-primary");
        expect(cn("bg-re-surface-card", "bg-re-surface-base")).toBe("bg-re-surface-base");
        expect(cn("border-re-border", "border-re-border-strong")).toBe("border-re-border-strong");
    });

    it("does not swallow text utilities that are neither size nor colour", () => {
        expect(cn("text-ui", "text-center")).toBe("text-ui text-center");
        expect(cn("text-ui", "text-balance")).toBe("text-ui text-balance");
        expect(cn("text-left", "text-right")).toBe("text-right");
    });

    it("scopes the size per responsive variant", () => {
        expect(cn("text-ui", "md:text-small", "text-re-text-muted")).toBe(
            "text-ui md:text-small text-re-text-muted",
        );
    });
});
