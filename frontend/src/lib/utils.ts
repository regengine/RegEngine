import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

export function formatDate(dateString: string | undefined): string {
    if (!dateString) return '—';
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
