import type { CSSProperties } from 'react';
import { cn } from '@/lib/utils';

/**
 * Food marker for the public workbench surfaces. The hue comes from the
 * dataset and is applied through a custom property, so no colour is written
 * into page markup. Never the only signal: a dot always sits beside a name.
 */
export function HueDot({ hue, size = 'md', className }: { hue: string; size?: 'sm' | 'md'; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block shrink-0 rounded-full bg-[var(--food-hue)]',
        size === 'sm' ? 'h-[7px] w-[7px]' : 'h-2 w-2',
        className,
      )}
      style={{ '--food-hue': hue } as CSSProperties}
    />
  );
}

/** Small brand dot that pulses to mark a live surface. */
export function LiveDot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('re-pulse-dot inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-re-brand', className)}
    />
  );
}
