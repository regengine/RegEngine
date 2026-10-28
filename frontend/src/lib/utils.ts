import { type ClassValue, clsx } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"
import { NOT_SET } from "./empty-values"

/**
 * The design system's type scale (tailwind.config.ts -> theme.extend.fontSize).
 *
 * tailwind-merge only knows Tailwind's stock size names, so it classifies every
 * one of these as a *text colour* and drops it the moment a real colour class
 * follows: `cn("text-ui", "text-re-text-secondary")` collapsed to just the
 * colour, and the element silently fell back to the inherited 16px body size.
 * Registering the scale in the font-size group is what makes `cn()` treat
 * size and colour as the two independent axes they are.
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
] as const

const twMerge = extendTailwindMerge({
    extend: {
        classGroups: {
            "font-size": [{ text: [...TYPE_SCALE] }],
        },
    },
})

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

export function formatDate(dateString: string | undefined): string {
    if (!dateString) return NOT_SET;
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

export interface ValidationResult {
    isValid: boolean;
    error?: string;
}

export function validateApiKey(key: string): ValidationResult {
    if (!key) return { isValid: false, error: 'API key is required' };
    if (!key.startsWith('rge_')) return { isValid: false, error: 'API key must start with "rge_"' };
    if (key.length < 10) return { isValid: false, error: 'API key is too short' };
    return { isValid: true };
}

export function validateAdminKey(key: string): ValidationResult {
    if (!key) return { isValid: false, error: 'Admin key is required' };
    if (key.length < 8) return { isValid: false, error: 'Admin key is too short' };
    return { isValid: true };
}

export function validateUrl(url: string): ValidationResult {
    if (!url) return { isValid: false, error: 'URL is required' };
    try {
        new URL(url);
        return { isValid: true };
    } catch {
        return { isValid: false, error: 'Invalid URL format' };
    }
}
